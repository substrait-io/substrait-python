import calendar
import itertools
import uuid as uuid_module
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Callable, Iterable, Union

import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.extensions.extensions_pb2 as ste
import substrait.type_pb2 as stp

from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_extended_expression_schema
from substrait.utils import (
    merge_extension_declarations,
    merge_extension_urns,
    type_num_names,
)

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


def resolve_expression(
    expression: ExtendedExpressionOrUnbound,
    base_schema: stp.NamedStruct,
    registry: ExtensionRegistry,
) -> stee.ExtendedExpression:
    return (
        expression
        if isinstance(expression, stee.ExtendedExpression)
        else expression(base_schema, registry)
    )


_EPOCH_DATE = date(1970, 1, 1)


def _scale_subseconds(microseconds: int, precision: int) -> int:
    """Convert a microsecond count to ``precision`` sub-second units."""
    if precision >= 6:
        return microseconds * 10 ** (precision - 6)
    return microseconds // 10 ** (6 - precision)


def _encode_decimal(value: Any, scale: int) -> bytes:
    """Encode a decimal as the 16-byte little-endian two's-complement unscaled value."""
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    unscaled = int((dec * (Decimal(10) ** scale)).to_integral_value(ROUND_HALF_EVEN))
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
        return Literal(
            struct=Literal.Struct(
                fields=[_make_literal(v, t) for v, t in zip(value, type.struct.types)]
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

    return resolve


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

    return resolve


def scalar_function(
    urn: str,
    function: str,
    expressions: Iterable[ExtendedExpressionOrUnbound],
    alias: Union[Iterable[str], str, None] = None,
):
    """Builds a resolver for ExtendedExpression containing a ScalarFunction expression"""

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expressions = [
            resolve_expression(e, base_schema, registry) for e in expressions
        ]

        expression_schemas = [
            infer_extended_expression_schema(b) for b in bound_expressions
        ]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(urn, function, signature)

        if not func:
            raise Exception(f"Unknown function {function} for {signature}")

        func_extension_urns = [
            ste.SimpleExtensionURN(
                extension_urn_anchor=registry.lookup_urn(urn), urn=urn
            )
        ]

        func_extensions = [
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_urn_reference=registry.lookup_urn(urn),
                    function_anchor=func[0].anchor,
                    name=str(func[0]),
                )
            )
        ]

        extension_urns = merge_extension_urns(
            func_extension_urns, *[b.extension_urns for b in bound_expressions]
        )

        extensions = merge_extension_declarations(
            func_extensions, *[b.extensions for b in bound_expressions]
        )

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        scalar_function=stalg.Expression.ScalarFunction(
                            function_reference=func[0].anchor,
                            arguments=[
                                stalg.FunctionArgument(
                                    value=e.referred_expr[0].expression
                                )
                                for e in bound_expressions
                            ],
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
            extension_urns=extension_urns,
            extensions=extensions,
        )

    return resolve


def aggregate_function(
    urn: str,
    function: str,
    expressions: Iterable[ExtendedExpressionOrUnbound],
    alias: Union[Iterable[str], str, None] = None,
):
    """Builds a resolver for ExtendedExpression containing a AggregateFunction measure"""

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            resolve_expression(e, base_schema, registry) for e in expressions
        ]

        expression_schemas = [
            infer_extended_expression_schema(b) for b in bound_expressions
        ]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(urn, function, signature)

        if not func:
            raise Exception(f"Unknown function {function} for {signature}")

        func_extension_urns = [
            ste.SimpleExtensionURN(
                extension_urn_anchor=registry.lookup_urn(urn), urn=urn
            )
        ]

        func_extensions = [
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_urn_reference=registry.lookup_urn(urn),
                    function_anchor=func[0].anchor,
                    name=str(func[0]),
                )
            )
        ]

        extension_urns = merge_extension_urns(
            func_extension_urns, *[b.extension_urns for b in bound_expressions]
        )

        extensions = merge_extension_declarations(
            func_extensions, *[b.extensions for b in bound_expressions]
        )

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    measure=stalg.AggregateFunction(
                        function_reference=func[0].anchor,
                        arguments=[
                            stalg.FunctionArgument(value=e.referred_expr[0].expression)
                            for e in bound_expressions
                        ],
                        output_type=func[1],
                    ),
                    output_names=_alias_or_inferred(
                        alias,
                        "IfThen",
                        [e.referred_expr[0].output_names[0] for e in bound_expressions],
                    ),
                )
            ],
            base_schema=base_schema,
            extension_urns=extension_urns,
            extensions=extensions,
        )

    return resolve


# TODO bounds, sorts
def window_function(
    urn: str,
    function: str,
    expressions: Iterable[ExtendedExpressionOrUnbound],
    partitions: Iterable[ExtendedExpressionOrUnbound] = [],
    alias: Union[Iterable[str], str, None] = None,
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
            infer_extended_expression_schema(b) for b in bound_expressions
        ]

        signature = [typ for es in expression_schemas for typ in es.types]

        func = registry.lookup_function(urn, function, signature)

        if not func:
            raise Exception(f"Unknown function {function} for {signature}")

        func_extension_urns = [
            ste.SimpleExtensionURN(
                extension_urn_anchor=registry.lookup_urn(urn), urn=urn
            )
        ]

        func_extensions = [
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_urn_reference=registry.lookup_urn(urn),
                    function_anchor=func[0].anchor,
                    name=str(func[0]),
                )
            )
        ]

        extension_urns = merge_extension_urns(
            func_extension_urns,
            *[b.extension_urns for b in bound_expressions],
            *[b.extension_urns for b in bound_partitions],
        )

        extensions = merge_extension_declarations(
            func_extensions,
            *[b.extensions for b in bound_expressions],
            *[b.extensions for b in bound_partitions],
        )

        return stee.ExtendedExpression(
            referred_expr=[
                stee.ExpressionReference(
                    expression=stalg.Expression(
                        window_function=stalg.Expression.WindowFunction(
                            function_reference=func[0].anchor,
                            arguments=[
                                stalg.FunctionArgument(
                                    value=e.referred_expr[0].expression
                                )
                                for e in bound_expressions
                            ],
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
            extension_urns=extension_urns,
            extensions=extensions,
        )

    return resolve


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

        extension_urns = merge_extension_urns(
            *[b[0].extension_urns for b in bound_ifs],
            *[b[1].extension_urns for b in bound_ifs],
            bound_else.extension_urns,
        )

        extensions = merge_extension_declarations(
            *[b[0].extensions for b in bound_ifs],
            *[b[1].extensions for b in bound_ifs],
            bound_else.extensions,
        )

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
            extension_urns=extension_urns,
            extensions=extensions,
        )

    return resolve


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

        extension_urns = merge_extension_urns(
            bound_match.extension_urns,
            *[b.extension_urns for _, b in bound_ifs],
            bound_else.extension_urns,
        )

        extensions = merge_extension_declarations(
            bound_match.extensions,
            *[b.extensions for _, b in bound_ifs],
            bound_else.extensions,
        )

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
            extension_urns=extension_urns,
            extensions=extensions,
        )

    return resolve


def singular_or_list(
    value: ExtendedExpressionOrUnbound, options: Iterable[ExtendedExpressionOrUnbound]
):
    """Builds a resolver for ExtendedExpression containing a SingularOrList expression"""

    def resolve(
        base_schema: stp.NamedStruct, registry: ExtensionRegistry
    ) -> stee.ExtendedExpression:
        bound_value = resolve_expression(value, base_schema, registry)
        bound_options = [resolve_expression(o, base_schema, registry) for o in options]

        extension_urns = merge_extension_urns(
            bound_value.extension_urns, *[b.extension_urns for b in bound_options]
        )

        extensions = merge_extension_declarations(
            bound_value.extensions, *[b.extensions for b in bound_options]
        )

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
            extension_urns=extension_urns,
            extensions=extensions,
        )

    return resolve


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

        extension_urns = merge_extension_urns(
            *[b.extension_urns for b in bound_value],
            *[e.extension_urns for b in bound_options for e in b],
        )

        extensions = merge_extension_declarations(
            *[b.extensions for b in bound_value],
            *[e.extensions for b in bound_options for e in b],
        )

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
            extension_urns=extension_urns,
            extensions=extensions,
        )

    return resolve


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
            extension_urns=bound_input.extension_urns,
            extensions=bound_input.extensions,
        )

    return resolve
