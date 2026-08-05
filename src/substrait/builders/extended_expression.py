import calendar
import contextlib
import contextvars
import itertools
import uuid as uuid_module
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable, Union

import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.type_pb2 as stp

from substrait.extension_registry import (
    ExtensionRegistry,
    build_scoped,
    current_collector,
    function_reference,
)
from substrait.type_inference import infer_extended_expression_schema, outer_schemas
from substrait.utils import (
    inline_reference_rels,
    plan_subtrees,
    remap_function_references,
    type_num_names,
)

# Monotonic source of unique RelCommon.rel_anchor values within a single build.
# Not reset between builds by default; reset at each top-level materialization
# (see fresh_rel_anchors) so a plan built the same way twice numbers alike.
_rel_anchor_counter: contextvars.ContextVar = contextvars.ContextVar(
    "_rel_anchor_counter", default=0
)


def next_rel_anchor() -> int:
    """Allocate a fresh RelCommon.rel_anchor, unique within the current build."""
    n = _rel_anchor_counter.get() + 1
    _rel_anchor_counter.set(n)
    return n


@contextlib.contextmanager
def fresh_rel_anchors():
    """Number rel_anchors from 1 within this block, restoring the prior counter
    afterwards. Wrap a top-level materialization so repeated builds of the same
    plan assign identical anchors."""
    token = _rel_anchor_counter.set(0)
    try:
        yield
    finally:
        _rel_anchor_counter.reset(token)


UnboundExtendedExpression = Callable[
    [stp.NamedStruct, ExtensionRegistry], stee.ExtendedExpression
]
ExtendedExpressionOrUnbound = Union[stee.ExtendedExpression, UnboundExtendedExpression]


def _alias_or_inferred(
    alias: Union[Iterable[str], str, None],
    op: str,
    args: Iterable[str],
):
    if alias:
        return [alias] if isinstance(alias, str) else alias
    else:
        return [f"{op}({','.join(args)})"]


def _function_options(options):
    """Build FunctionOption messages from a ``{name: preference}`` mapping.

    A preference may be a single string or an ordered list of acceptable values.
    """
    if not options:
        return []
    result = []
    for name, preference in options.items():
        prefs = [preference] if isinstance(preference, str) else list(preference)
        result.append(stalg.FunctionOption(name=name, preference=prefs))
    return result


def resolve_expression(
    expression: ExtendedExpressionOrUnbound,
    base_schema: stp.NamedStruct,
    registry: ExtensionRegistry,
) -> stee.ExtendedExpression:
    """Resolve ``expression``, folding its extensions into the build in progress.

    An already-bound ExtendedExpression numbered its function references against
    whichever build produced it, so the collector re-derives them from the durable
    ``(urn, name)`` identities and the expression is rewritten to match -- the
    expression-level counterpart of ``builders.plan._bind``. Unchanged when the
    numbering already agrees, as it does for anything this build resolved.
    """
    if not isinstance(expression, stee.ExtendedExpression):
        return expression(base_schema, registry)
    collector = current_collector()
    if collector is None:
        return expression
    return remap_function_references(expression, collector.adopt(expression))


def alias(
    expression: ExtendedExpressionOrUnbound,
    name: str,
) -> UnboundExtendedExpression:
    """Rename the first output column of ``expression`` to ``name``.

    Returns a resolver that binds ``expression`` and rewrites its top-level output
    name. Shared by the DataFrame/Expr ``.alias`` and the Narwhals expression
    wrapper so the single-column rename lives in one place.
    """

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expression = resolve_expression(expression, base_schema, registry)
        # The rename lands on a copy, never on ``bound_expression``:
        # ``resolve_expression`` hands back the caller's own message whenever the
        # remap is empty (the common case), so renaming in place would rewrite an
        # output name in an ExtendedExpression the caller still holds. Copying
        # wholesale means dropping the copied declarations too -- the collector, not
        # this expression, owns the anchor space until the outermost resolver writes
        # it (see ``builders.plan._bind``), and left in place an enclosing builder
        # would adopt the stale numbering a second time and re-apply a remap the
        # expression already carries.
        result = stee.ExtendedExpression()
        result.CopyFrom(bound_expression)
        result.ClearField("extension_urns")
        result.ClearField("extensions")
        result.referred_expr[0].output_names[0] = name
        return result

    return build_scoped(resolve)


_EPOCH_DATE = date(1970, 1, 1)


def _scale_subseconds(microseconds: int, precision: int) -> int:
    """Convert a microsecond count to ``precision`` sub-second units."""
    if precision >= 6:
        return microseconds * 10 ** (precision - 6)
    return microseconds // 10 ** (6 - precision)


def _encode_decimal(value: Any, scale: int) -> bytes:
    """Encode a decimal as the 16-byte little-endian two's-complement unscaled value.

    Scaling uses pure-integer arithmetic on ``as_tuple()`` rather than ``Decimal``
    multiplication, so it is exact regardless of the active ``decimal`` context
    precision (which would otherwise silently round a value with more than
    ``ctx.prec`` significant digits). A value carrying more fractional digits than
    ``scale`` is rounded half-even.
    """
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    sign, digits, exponent = dec.as_tuple()
    if not isinstance(exponent, int):  # NaN / Infinity have symbolic exponents
        raise ValueError(f"cannot encode a non-finite decimal literal: {value!r}")
    coeff = 0
    for d in digits:
        coeff = coeff * 10 + d
    shift = exponent + scale
    if shift >= 0:
        unscaled = coeff * 10**shift
    else:  # drop -shift low-order digits, rounding half-even
        factor = 10 ** (-shift)
        unscaled, remainder = divmod(coeff, factor)
        twice = 2 * remainder
        if twice > factor or (twice == factor and unscaled % 2):
            unscaled += 1
    if sign:
        unscaled = -unscaled
    return unscaled.to_bytes(16, byteorder="little", signed=True)


def _encode_uuid(value: Any) -> bytes:
    if isinstance(value, uuid_module.UUID):
        return value.bytes
    if isinstance(value, str):
        return uuid_module.UUID(value).bytes
    if isinstance(value, (bytes, bytearray)):
        if len(value) != 16:
            raise ValueError("uuid literal must be exactly 16 bytes")
        return bytes(value)
    raise TypeError(f"cannot build a uuid literal from {type(value).__name__}")


def _timestamp_units(value: Any, precision: int) -> int:
    """Sub-second units since the Unix epoch for an int or datetime value."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        micros = calendar.timegm(value.timetuple()) * 1_000_000 + value.microsecond
        return _scale_subseconds(micros, precision)
    return value


def _time_units(value: Any, precision: int) -> int:
    """Sub-second units since midnight for an int or datetime.time value."""
    if isinstance(value, time):
        micros = (
            value.hour * 3600 + value.minute * 60 + value.second
        ) * 1_000_000 + value.microsecond
        return _scale_subseconds(micros, precision)
    return value


def _interval_day_to_second(value: Any, precision: int):
    """Build an IntervalDayToSecond from a timedelta or a (days, seconds[, subseconds]) tuple."""
    if isinstance(value, timedelta):
        days, seconds, subseconds = (
            value.days,
            value.seconds,
            _scale_subseconds(value.microseconds, precision),
        )
    else:
        days, seconds, *rest = value
        subseconds = rest[0] if rest else 0
    return stalg.Expression.Literal.IntervalDayToSecond(
        days=days, seconds=seconds, subseconds=subseconds, precision=precision
    )


def _interval_year_to_month(value: Any):
    """Build an IntervalYearToMonth from an int (years) or a (years, months) tuple."""
    if isinstance(value, (tuple, list)):
        years, months = value
    else:
        years, months = value, 0
    return stalg.Expression.Literal.IntervalYearToMonth(years=years, months=months)


def _make_literal(value: Any, type: stp.Type) -> stalg.Expression.Literal:
    """Recursively build an ``Expression.Literal`` for ``value`` of ``type``.

    A ``value`` of ``None`` produces a typed null literal of ``type``. Nested
    types (struct/list/map) recurse into their element types. Supported value
    representations for the less-obvious kinds:

    - decimal: ``decimal.Decimal`` / ``int`` / ``float`` / ``str``
    - uuid: ``uuid.UUID`` / 16 ``bytes`` / hex ``str``
    - precision_timestamp[_tz]: ``int`` sub-second units, or ``datetime``
    - precision_time: ``int`` sub-second units, or ``datetime.time``
    - interval_year: ``int`` years or ``(years, months)``
    - interval_day: ``datetime.timedelta`` or ``(days, seconds[, subseconds])``
    - interval_compound: ``((years, months), (days, seconds[, subseconds]))``
    - struct: sequence of field values; list: sequence; map: ``dict`` or pairs
    """
    Literal = stalg.Expression.Literal

    if value is None:
        return Literal(null=type, nullable=True)

    kind = type.WhichOneof("kind")
    nullable = getattr(type, kind).nullability == stp.Type.NULLABILITY_NULLABLE

    if kind == "bool":
        return Literal(boolean=value, nullable=nullable)
    elif kind == "i8":
        return Literal(i8=value, nullable=nullable)
    elif kind == "i16":
        return Literal(i16=value, nullable=nullable)
    elif kind == "i32":
        return Literal(i32=value, nullable=nullable)
    elif kind == "i64":
        return Literal(i64=value, nullable=nullable)
    elif kind == "fp32":
        return Literal(fp32=value, nullable=nullable)
    elif kind == "fp64":
        return Literal(fp64=value, nullable=nullable)
    elif kind == "string":
        return Literal(string=value, nullable=nullable)
    elif kind == "binary":
        return Literal(binary=value, nullable=nullable)
    elif kind == "date":
        date_value = (value - _EPOCH_DATE).days if isinstance(value, date) else value
        return Literal(date=date_value, nullable=nullable)
    elif kind == "interval_year":
        return Literal(
            interval_year_to_month=_interval_year_to_month(value), nullable=nullable
        )
    elif kind == "interval_day":
        return Literal(
            interval_day_to_second=_interval_day_to_second(
                value, type.interval_day.precision
            ),
            nullable=nullable,
        )
    elif kind == "interval_compound":
        precision = type.interval_compound.precision
        ym, ds = value
        return Literal(
            interval_compound=stalg.Expression.Literal.IntervalCompound(
                interval_year_to_month=_interval_year_to_month(ym),
                interval_day_to_second=_interval_day_to_second(ds, precision),
            ),
            nullable=nullable,
        )
    elif kind == "fixed_char":
        return Literal(fixed_char=value, nullable=nullable)
    elif kind == "varchar":
        return Literal(
            var_char=Literal.VarChar(value=value, length=type.varchar.length),
            nullable=nullable,
        )
    elif kind == "fixed_binary":
        return Literal(fixed_binary=value, nullable=nullable)
    elif kind == "decimal":
        return Literal(
            decimal=Literal.Decimal(
                value=_encode_decimal(value, type.decimal.scale),
                precision=type.decimal.precision,
                scale=type.decimal.scale,
            ),
            nullable=nullable,
        )
    elif kind == "precision_time":
        precision = type.precision_time.precision
        return Literal(
            precision_time=Literal.PrecisionTime(
                precision=precision, value=_time_units(value, precision)
            ),
            nullable=nullable,
        )
    elif kind == "precision_timestamp":
        precision = type.precision_timestamp.precision
        return Literal(
            precision_timestamp=Literal.PrecisionTimestamp(
                precision=precision, value=_timestamp_units(value, precision)
            ),
            nullable=nullable,
        )
    elif kind == "precision_timestamp_tz":
        precision = type.precision_timestamp_tz.precision
        return Literal(
            precision_timestamp_tz=Literal.PrecisionTimestamp(
                precision=precision, value=_timestamp_units(value, precision)
            ),
            nullable=nullable,
        )
    elif kind == "uuid":
        return Literal(uuid=_encode_uuid(value), nullable=nullable)
    elif kind == "struct":
        values = list(value)
        field_types = list(type.struct.types)
        if len(values) != len(field_types):
            raise ValueError(
                f"struct literal has {len(values)} value(s) but its type declares "
                f"{len(field_types)} field(s)"
            )
        return Literal(
            struct=Literal.Struct(
                fields=[_make_literal(v, t) for v, t in zip(values, field_types)]
            ),
            nullable=nullable,
        )
    elif kind == "list":
        values = list(value)
        if not values:
            return Literal(empty_list=type.list, nullable=nullable)
        return Literal(
            list=Literal.List(
                values=[_make_literal(v, type.list.type) for v in values]
            ),
            nullable=nullable,
        )
    elif kind == "map":
        items = list(value.items() if isinstance(value, dict) else value)
        if not items:
            return Literal(empty_map=type.map, nullable=nullable)
        return Literal(
            map=Literal.Map(
                key_values=[
                    Literal.Map.KeyValue(
                        key=_make_literal(k, type.map.key),
                        value=_make_literal(v, type.map.value),
                    )
                    for k, v in items
                ]
            ),
            nullable=nullable,
        )
    else:
        raise Exception(f"Unknown literal type - {type}")


def literal(
    value: Any, type: stp.Type, alias: Union[Iterable[str], str, None] = None
) -> UnboundExtendedExpression:
    """Builds a resolver for ExtendedExpression containing a literal expression.

    ``value`` of ``None`` yields a typed null literal. See :func:`_make_literal`
    for the accepted value representations of each type kind.
    """

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(literal=_make_literal(value, type)),
                    output_names=_alias_or_inferred(alias, "Literal", [str(value)]),
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


def outer_reference(field: Union[str, int], steps_out: int = 1):
    """A field reference to an enclosing query's column (a correlated reference).

    Only valid inside a subquery; ``steps_out`` counts query-nesting levels
    outward (1 = the immediately enclosing query), matching Substrait's
    requirement that ``steps_out`` be >= 1. ``field`` is resolved against that
    enclosing query's schema.
    """

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        if steps_out < 1:
            raise ValueError(
                "steps_out must be >= 1 (1 = the immediately enclosing query)"
            )
        stack = outer_schemas.get()
        if steps_out > len(stack):
            raise Exception("outer() is only valid inside a correlated subquery")
        outer_ns = stack[len(stack) - steps_out]
        # Resolve the column against the enclosing schema, then re-root it as an
        # outer reference (keeping the resolved struct-field segment).
        resolved = column(field)(outer_ns, registry).referred_expr[0]
        segment = resolved.expression.selection.direct_reference
        expr = stalg.Expression(
            selection=stalg.Expression.FieldReference(
                outer_reference=stalg.Expression.FieldReference.OuterReference(
                    steps_out=steps_out
                ),
                direct_reference=segment,
            )
        )
        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=expr, output_names=resolved.output_names
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


class LateralInput:
    """A handle to a lateral join's left input, passed to the ``right`` builder
    by :func:`~substrait.builders.plan.lateral_join`.

    Its :meth:`column` references resolve against the left row via an id-based
    ``OuterReference`` (``rel_reference`` naming the join's
    ``RelCommon.rel_anchor``), so the right (dependent) input can correlate on
    the current left row by capturing the handle -- no nesting-depth bookkeeping.
    """

    def __init__(self, rel_anchor: int, schema: stp.NamedStruct):
        self._rel_anchor = rel_anchor
        self._schema = schema

    def column(self, field: Union[str, int]):
        """A correlated reference to the left row's ``field`` (name or index)."""
        rel_anchor = self._rel_anchor
        schema = self._schema

        def resolve(
            base_schema: stp.NamedStruct, registry: ExtensionRegistry
        ) -> stee.ExtendedExpression:
            # Resolve the column against the left schema, then re-root it as an
            # id-based outer reference (keeping the resolved struct-field segment).
            resolved = column(field)(schema, registry).referred_expr[0]
            segment = resolved.expression.selection.direct_reference
            expr = stalg.Expression(
                selection=stalg.Expression.FieldReference(
                    outer_reference=stalg.Expression.FieldReference.OuterReference(
                        rel_reference=rel_anchor
                    ),
                    direct_reference=segment,
                )
            )
            return stee.ExtendedExpression(
                referred_expr=[
                    stee.ExpressionReference(
                        expression=expr, output_names=resolved.output_names
                    )
                ],
                base_schema=base_schema,
            )

        return build_scoped(resolve)


def column(field: Union[str, int], alias: Union[Iterable[str], str, None] = None):
    """Builds a resolver for ExtendedExpression containing a FieldReference expression

    Accepts either an index or a field name of a desired field.
    """
    alias = [alias] if alias and isinstance(alias, str) else alias

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        lengths = [type_num_names(t) for t in base_schema.struct.types]
        flat_indices = [0] + list(itertools.accumulate(lengths))[:-1]

        if isinstance(field, str):
            column_index = list(base_schema.names).index(field)
            field_index = flat_indices.index(column_index)
        else:
            field_index = field

        names_start = flat_indices[field_index]
        names_end = (
            flat_indices[field_index + 1]
            if len(flat_indices) > field_index + 1
            else None
        )

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        selection=stalg.Expression.FieldReference(
                            root_reference=stalg.Expression.FieldReference.RootReference(),
                            direct_reference=stalg.Expression.ReferenceSegment(
                                struct_field=stalg.Expression.ReferenceSegment.StructField(
                                    field=field_index
                                )
                            ),
                        )
                    ),
                    output_names=list(base_schema.names)[names_start:names_end]
                    if not alias
                    else alias,
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


def scalar_function(
    urn: str,
    function: str,
    expressions: Iterable[ExtendedExpressionOrUnbound],
    alias: Union[Iterable[str], str, None] = None,
    options: Union[dict, None] = None,
):
    """Builds a resolver for ExtendedExpression containing a ScalarFunction expression.

    ``options`` is an optional ``{name: preference}`` mapping of behavioral
    function options (e.g. ``{"overflow": "ERROR"}``).
    """

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expressions = [
            resolve_expression(e, base_schema, registry) for e in expressions
        ]

        expression_schemas = [
            infer_extended_expression_schema(b, registry=registry)
            for b in bound_expressions
        ]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(urn, function, signature)

        if not func:
            raise Exception(f"Unknown function {function} for {signature}")

        func_ref = function_reference(urn, str(func[0]))

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        scalar_function=stalg.Expression.ScalarFunction(
                            function_reference=func_ref,
                            arguments=[
                                stalg.FunctionArgument(
                                    value=e.referred_expr[0].expression
                                )
                                for e in bound_expressions
                            ],
                            options=_function_options(options),
                            output_type=func[1],
                        )
                    ),
                    output_names=_alias_or_inferred(
                        alias,
                        function,
                        [e.referred_expr[0].output_names[0] for e in bound_expressions],
                    ),
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


def aggregate_function(
    urn: str,
    function: str,
    expressions: Iterable[ExtendedExpressionOrUnbound],
    alias: Union[Iterable[str], str, None] = None,
    invocation: Union[
        "stalg.AggregateFunction.AggregationInvocation.ValueType", None
    ] = None,
    sorts: Iterable[
        tuple[ExtendedExpressionOrUnbound, "stalg.SortField.SortDirection.ValueType"]
    ] = (),
    options: Union[dict, None] = None,
):
    """Builds a resolver for ExtendedExpression containing a AggregateFunction measure.

    ``invocation`` selects ALL vs DISTINCT (``COUNT(DISTINCT ...)``); ``sorts`` is
    a list of ``(expression, SortDirection)`` pairs for order-sensitive aggregates.
    """

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            resolve_expression(e, base_schema, registry) for e in expressions
        ]
        bound_sorts = [
            (resolve_expression(e, base_schema, registry), direction)
            for e, direction in sorts
        ]

        expression_schemas = [
            infer_extended_expression_schema(b, registry=registry)
            for b in bound_expressions
        ]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(urn, function, signature)

        if not func:
            raise Exception(f"Unknown function {function} for {signature}")

        func_ref = function_reference(urn, str(func[0]))

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    measure=stalg.AggregateFunction(
                        function_reference=func_ref,
                        arguments=[
                            stalg.FunctionArgument(value=e.referred_expr[0].expression)
                            for e in bound_expressions
                        ],
                        options=_function_options(options),
                        output_type=func[1],
                        invocation=invocation
                        if invocation is not None
                        else stalg.AggregateFunction.AGGREGATION_INVOCATION_UNSPECIFIED,
                        sorts=[
                            stalg.SortField(
                                expr=s.referred_expr[0].expression, direction=direction
                            )
                            for s, direction in bound_sorts
                        ],
                    ),
                    output_names=_alias_or_inferred(
                        alias,
                        "IfThen",
                        [e.referred_expr[0].output_names[0] for e in bound_expressions],
                    ),
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


# TODO bounds, sorts
def window_function(
    urn: str,
    function: str,
    expressions: Iterable[ExtendedExpressionOrUnbound],
    partitions: Iterable[ExtendedExpressionOrUnbound] = [],
    alias: Union[Iterable[str], str, None] = None,
    options: Union[dict, None] = None,
):
    """Builds a resolver for ExtendedExpression containing a WindowFunction expression"""

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            resolve_expression(e, base_schema, registry) for e in expressions
        ]

        bound_partitions = [
            resolve_expression(e, base_schema, registry) for e in partitions
        ]

        expression_schemas = [
            infer_extended_expression_schema(b, registry=registry)
            for b in bound_expressions
        ]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(urn, function, signature)

        if not func:
            raise Exception(f"Unknown function {function} for {signature}")

        func_ref = function_reference(urn, str(func[0]))

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        window_function=stalg.Expression.WindowFunction(
                            function_reference=func_ref,
                            arguments=[
                                stalg.FunctionArgument(
                                    value=e.referred_expr[0].expression
                                )
                                for e in bound_expressions
                            ],
                            options=_function_options(options),
                            output_type=func[1],
                            partitions=[
                                e.referred_expr[0].expression for e in bound_partitions
                            ],
                        )
                    ),
                    output_names=_alias_or_inferred(
                        alias,
                        function,
                        [e.referred_expr[0].output_names[0] for e in bound_expressions],
                    ),
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


def if_then(
    ifs: Iterable[tuple[ExtendedExpressionOrUnbound, ExtendedExpressionOrUnbound]],
    _else: ExtendedExpressionOrUnbound,
    alias: Union[Iterable[str], str, None] = None,
):
    """Builds a resolver for ExtendedExpression containing an IfThen expression"""

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_ifs = [
            (
                resolve_expression(if_clause[0], base_schema, registry),
                resolve_expression(if_clause[1], base_schema, registry),
            )
            for if_clause in ifs
        ]

        bound_else = resolve_expression(_else, base_schema, registry)

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        if_then=stalg.Expression.IfThen(
                            **{
                                "ifs": [
                                    stalg.Expression.IfThen.IfClause(
                                        **{
                                            "if": if_clause[0]
                                            .referred_expr[0]
                                            .expression,
                                            "then": if_clause[1]
                                            .referred_expr[0]
                                            .expression,
                                        }
                                    )
                                    for if_clause in bound_ifs
                                ],
                                "else": bound_else.referred_expr[0].expression,
                            }
                        )
                    ),
                    output_names=_alias_or_inferred(
                        alias,
                        "IfThen",
                        [
                            a
                            for e in bound_ifs
                            for a in [
                                e[0].referred_expr[0].output_names[0],
                                e[1].referred_expr[0].output_names[0],
                            ]
                        ]
                        + [bound_else.referred_expr[0].output_names[0]],
                    ),
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


def switch(
    match: ExtendedExpressionOrUnbound,
    ifs: Iterable[tuple[ExtendedExpressionOrUnbound, ExtendedExpressionOrUnbound]],
    _else: ExtendedExpressionOrUnbound,
):
    """Builds a resolver for ExtendedExpression containing a switch expression"""

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_match = resolve_expression(match, base_schema, registry)
        bound_ifs = [
            (
                resolve_expression(a, base_schema, registry),
                resolve_expression(b, base_schema, registry),
            )
            for a, b in ifs
        ]
        bound_else = resolve_expression(_else, base_schema, registry)

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        switch_expression=stalg.Expression.SwitchExpression(
                            match=bound_match.referred_expr[0].expression,
                            ifs=[
                                stalg.Expression.SwitchExpression.IfValue(
                                    **{
                                        "if": i.referred_expr[0].expression.literal,
                                        "then": t.referred_expr[0].expression,
                                    }
                                )
                                for i, t in bound_ifs
                            ],
                            **{"else": bound_else.referred_expr[0].expression},
                        )
                    ),
                    output_names=["switch"],  # TODO construct name from inputs
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


def singular_or_list(
    value: ExtendedExpressionOrUnbound, options: Iterable[ExtendedExpressionOrUnbound]
):
    """Builds a resolver for ExtendedExpression containing a SingularOrList expression"""

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_value = resolve_expression(value, base_schema, registry)
        bound_options = [resolve_expression(o, base_schema, registry) for o in options]

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        singular_or_list=stalg.Expression.SingularOrList(
                            value=bound_value.referred_expr[0].expression,
                            options=[
                                o.referred_expr[0].expression for o in bound_options
                            ],
                        )
                    ),
                    output_names=[
                        "singular_or_list"
                    ],  # TODO construct name from inputs
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


def multi_or_list(
    value: Iterable[ExtendedExpressionOrUnbound],
    options: Iterable[Iterable[ExtendedExpressionOrUnbound]],
):
    """Builds a resolver for ExtendedExpression containing a MultiOrList expression"""

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_value = [resolve_expression(e, base_schema, registry) for e in value]
        bound_options = [
            [resolve_expression(e, base_schema, registry) for e in o] for o in options
        ]

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        multi_or_list=stalg.Expression.MultiOrList(
                            value=[e.referred_expr[0].expression for e in bound_value],
                            options=[
                                stalg.Expression.MultiOrList.Record(
                                    fields=[
                                        e.referred_expr[0].expression for e in option
                                    ]
                                )
                                for option in bound_options
                            ],
                        )
                    ),
                    output_names=["multi_or_list"],  # TODO construct name from inputs
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


def cast(
    input: ExtendedExpressionOrUnbound,
    type: stp.Type,
    alias: Union[Iterable[str], str, None] = None,
):
    """Builds a resolver for ExtendedExpression containing a cast expression"""

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_input = resolve_expression(input, base_schema, registry)

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        cast=stalg.Expression.Cast(
                            input=bound_input.referred_expr[0].expression,
                            type=type,
                            failure_behavior=stalg.Expression.Cast.FAILURE_BEHAVIOR_RETURN_NULL,
                        )
                    ),
                    output_names=_alias_or_inferred(
                        alias, "cast", [bound_input.referred_expr[0].output_names[0]]
                    ),
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


# -- subqueries -----------------------------------------------------------
# These embed an inner query's Rel. ``query`` is a Plan or an UnboundPlan
# (a ``registry -> Plan`` callable) -- e.g. a DataFrame's underlying plan.


def _subquery(subquery, base_schema, output_name):
    return stee.ExtendedExpression(
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(subquery=subquery),
                output_names=[output_name],
            )
        ],
        base_schema=base_schema,
    )


def _inner_rel(query, registry: ExtensionRegistry, base_schema) -> stalg.Rel:
    """Resolve a subquery's ``query`` and lift the self-contained Rel to embed.

    The plan itself is not returned: everything of it that survives the subquery
    boundary is either folded into the build's collector or inlined into the Rel
    below, so a caller holding on to it could only reintroduce the numbering this
    already reconciled.
    """
    # Push the enclosing schema so field references inside the subquery that use
    # an OuterReference (i.e. correlated columns) resolve against it.
    stack = outer_schemas.get()
    token = outer_schemas.set((*stack, base_schema))
    try:
        plan = query(registry) if callable(query) else query
    finally:
        outer_schemas.reset(token)
    # Fold the inner plan's extensions into this build before lifting its Rel: only
    # the Rel travels into the Expression.Subquery, so the declarations its function
    # references name stay behind with the plan. A plan built elsewhere therefore
    # arrives numbered against a table that is about to be discarded -- its
    # references dangle, or, worse, silently name one of *this* build's declarations
    # where the numbering happens to overlap. The collector re-derives them from the
    # durable ``(urn, name)`` identities, the expression-level counterpart of
    # ``builders.plan._bind``; unchanged for a plan this build resolved, which
    # allocated through the same collector.
    collector = current_collector()
    if collector is not None:
        plan = remap_function_references(plan, collector.adopt(plan))
    rel = plan.relations[-1].root.input
    # An Expression.Subquery embeds only a bare Rel, but a ReferenceRel is
    # plan-global -- it cannot resolve once lifted out of its plan. So if the
    # subquery's plan carries shared subtrees (e.g. it uses a cached frame),
    # inline them into the subquery Rel, making it self-contained. A cached frame
    # used inside a subquery is thus inlined there rather than shared across the
    # subquery boundary.
    subtrees = plan_subtrees(plan)
    if subtrees:
        rel = inline_reference_rels(rel, subtrees)
    return rel


def scalar_subquery(query, alias: Union[str, None] = None):
    """A scalar (one-row, one-column) subquery expression."""

    def resolve(base_schema, registry):
        rel = _inner_rel(query, registry, base_schema)
        subquery = stalg.Expression.Subquery(
            scalar=stalg.Expression.Subquery.Scalar(input=rel)
        )
        return _subquery(subquery, base_schema, alias or "subquery")

    return build_scoped(resolve)


def set_predicate(query, op, alias: Union[str, None] = None):
    """An EXISTS / UNIQUE subquery predicate."""

    def resolve(base_schema, registry):
        rel = _inner_rel(query, registry, base_schema)
        subquery = stalg.Expression.Subquery(
            set_predicate=stalg.Expression.Subquery.SetPredicate(
                predicate_op=op, tuples=rel
            )
        )
        return _subquery(subquery, base_schema, alias or "exists")

    return build_scoped(resolve)


def in_predicate(needles, query, alias: Union[str, None] = None):
    """A ``needles IN (subquery)`` predicate."""

    def resolve(base_schema, registry):
        rel = _inner_rel(query, registry, base_schema)
        bound = [resolve_expression(n, base_schema, registry) for n in needles]
        subquery = stalg.Expression.Subquery(
            in_predicate=stalg.Expression.Subquery.InPredicate(
                needles=[b.referred_expr[0].expression for b in bound], haystack=rel
            )
        )
        return _subquery(subquery, base_schema, alias or "in_subquery")

    return build_scoped(resolve)


def set_comparison(left, query, reduction_op, comparison_op, alias=None):
    """A ``left <op> ANY/ALL (subquery)`` predicate."""

    def resolve(base_schema, registry):
        rel = _inner_rel(query, registry, base_schema)
        bound_left = resolve_expression(left, base_schema, registry)
        subquery = stalg.Expression.Subquery(
            set_comparison=stalg.Expression.Subquery.SetComparison(
                reduction_op=reduction_op,
                comparison_op=comparison_op,
                left=bound_left.referred_expr[0].expression,
                right=rel,
            )
        )
        return _subquery(subquery, base_schema, alias or "set_comparison")

    return build_scoped(resolve)


def execution_context_variable(variable: str, type_value, alias=None):
    """A leaf expression for a runtime context value.

    ``variable`` is one of ``current_timestamp`` / ``current_timezone`` /
    ``current_date``; ``type_value`` is the matching ``Type.*`` message the
    oneof carries (it also declares the variable's type).
    """

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        ecv = stalg.Expression.ExecutionContextVariable(**{variable: type_value})
        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(execution_context_variable=ecv),
                    output_names=[alias or variable],
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)


def dynamic_parameter(parameter_reference: int, type: stp.Type, alias=None):
    """A DynamicParameter placeholder bound at runtime (prepared-statement style).

    Carries its own ``type`` and a 0-based ``parameter_reference`` into the
    plan's ``parameter_bindings``.
    """

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        expr = stalg.Expression(
            dynamic_parameter=stalg.DynamicParameter(
                parameter_reference=parameter_reference, type=type
            )
        )
        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=expr, output_names=[alias or f"?{parameter_reference}"]
                )
            ],
            base_schema=base_schema,
        )

    return build_scoped(resolve)
