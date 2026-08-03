"""Ergonomic expression wrapper.

``Expr`` wraps the existing "unbound" expression callables produced by
``substrait.builders.extended_expression`` and adds Python operator overloading
so that expressions can be written the way users of pandas / Polars / PySpark /
Ibis expect::

    col("age") > 25
    (col("x") + col("y")) * 2
    col("a").is_null() & col("b")

Each operator maps to a fixed standard function-extension URN + signature name
and defers to the existing ``scalar_function`` builder, which already resolves
the concrete overload lazily against an ``ExtensionRegistry``. Nothing here
reimplements resolution or type inference -- it is a thin, additive facade.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import time as _time
from decimal import Decimal as _Decimal
from typing import Any, Union

import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.type_pb2 as stp

from substrait.builders import type as _t
from substrait.builders.extended_expression import (
    UnboundExtendedExpression,
    cast,
    column,
    if_then,
    literal,
    resolve_expression,
    scalar_function,
    singular_or_list,
    switch,
)
from substrait.builders.extended_expression import (
    alias as _alias,
)
from substrait.builders.extended_expression import (
    dynamic_parameter as _dynamic_parameter,
)
from substrait.builders.extended_expression import (
    execution_context_variable as _execution_context_variable,
)
from substrait.builders.extended_expression import (
    in_predicate as _in_predicate,
)
from substrait.builders.extended_expression import (
    outer_reference as _outer_reference,
)
from substrait.builders.extended_expression import (
    scalar_subquery as _scalar_subquery,
)
from substrait.builders.extended_expression import (
    set_comparison as _set_comparison,
)
from substrait.builders.extended_expression import (
    set_predicate as _set_predicate,
)
from substrait.type_inference import infer_extended_expression_schema

# Standard Substrait function-extension URNs used by the operators below.
FUNCTIONS_COMPARISON = "extension:io.substrait:functions_comparison"
FUNCTIONS_ARITHMETIC = "extension:io.substrait:functions_arithmetic"
FUNCTIONS_ARITHMETIC_DECIMAL = "extension:io.substrait:functions_arithmetic_decimal"
FUNCTIONS_BOOLEAN = "extension:io.substrait:functions_boolean"
FUNCTIONS_STRING = "extension:io.substrait:functions_string"
FUNCTIONS_AGGREGATE_GENERIC = "extension:io.substrait:functions_aggregate_generic"
FUNCTIONS_LIST = "extension:io.substrait:functions_list"

# Arithmetic operators try the base extension first, then its decimal variant, so
# decimal operands resolve against ``functions_arithmetic_decimal`` (there is no
# such fallback for comparisons -- ``functions_comparison`` is generic ``any1``).
_ARITHMETIC_URNS = [FUNCTIONS_ARITHMETIC, FUNCTIONS_ARITHMETIC_DECIMAL]


# Substrait bounds a decimal's precision to 38 (a 128-bit unscaled value).
_MAX_DECIMAL_PRECISION = 38


def _decimal_type(value: _Decimal) -> stp.Type:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):  # NaN / Infinity have symbolic exponents
        raise TypeError("cannot infer a decimal literal type from a non-finite Decimal")
    scale = -exponent if exponent < 0 else 0
    # Precision counts the digits of the *unscaled* integer. For a positive
    # exponent (e.g. Decimal("1E3") -> unscaled 1000) the trailing zeros are not
    # in as_tuple().digits, so add them back; otherwise the declared precision is
    # too small for the encoded value.
    digits = len(value.as_tuple().digits) + max(exponent, 0)
    precision = max(digits, scale, 1)
    if precision > _MAX_DECIMAL_PRECISION:
        raise ValueError(
            f"decimal literal {value!r} needs precision {precision}, exceeding "
            f"Substrait's maximum decimal precision of {_MAX_DECIMAL_PRECISION}; "
            f"the value has too many significant digits for a decimal"
        )
    return _t.decimal(scale, precision)


def infer_literal_type(value: Any) -> stp.Type:
    """Best-effort mapping from a Python scalar to a Substrait type.

    Used to auto-wrap bare Python values on the right-hand side of an operator,
    e.g. the ``25`` in ``col("age") > 25``. ``bool`` is checked before ``int``
    (``isinstance(True, int)`` is ``True``) and ``datetime`` before ``date``
    (``datetime`` subclasses ``date``).
    """
    if isinstance(value, bool):
        return _t.boolean()
    if isinstance(value, int):
        return _t.i64()
    if isinstance(value, float):
        return _t.fp64()
    if isinstance(value, _Decimal):
        return _decimal_type(value)
    if isinstance(value, str):
        return _t.string()
    if isinstance(value, (bytes, bytearray)):
        return _t.binary()
    if isinstance(value, _datetime):
        # microsecond precision; tz-aware values map to the *_tz variant.
        return (
            _t.precision_timestamp_tz(6)
            if value.tzinfo is not None
            else _t.precision_timestamp(6)
        )
    if isinstance(value, _date):
        return _t.date()
    if isinstance(value, _time):
        return _t.precision_time(6)
    if isinstance(value, _uuid.UUID):
        return _t.uuid()
    raise TypeError(
        f"Cannot infer a Substrait literal type for {value!r} "
        f"({type(value).__name__}); wrap it with lit(value, <type>) instead."
    )


_NUMERIC_BUILDERS = {
    "i8": _t.i8,
    "i16": _t.i16,
    "i32": _t.i32,
    "i64": _t.i64,
    "fp32": _t.fp32,
    "fp64": _t.fp64,
}


def _exact_unscaled(value: _Decimal, scale: int) -> Union[int, None]:
    """The unscaled integer of ``value`` at ``scale``, or ``None`` if representing
    it at ``scale`` would drop nonzero digits (i.e. the value needs a finer scale).

    Pure-integer arithmetic on ``as_tuple()`` so it is exact regardless of the
    ``decimal`` context precision.
    """
    sign, digits, exponent = value.as_tuple()
    coeff = 0
    for d in digits:
        coeff = coeff * 10 + d
    shift = exponent + scale
    if shift < 0:  # value carries more fractional digits than `scale` allows
        factor = 10 ** (-shift)
        if coeff % factor:
            return None
        coeff //= factor
    else:
        coeff *= 10**shift
    return -coeff if sign else coeff


def _match_numeric_type(
    peer_type: stp.Type, value: Any, *, decimal_literal: str = "natural"
) -> stp.Type:
    """Pick a literal type for ``value`` that matches a numeric ``peer_type``.

    Substrait does not implicitly coerce mixed numeric operands, so
    ``col("price_fp64") * 2`` needs the ``2`` typed as ``fp64`` rather than the
    default ``i64`` for the ``multiply`` overload to resolve. A ``float`` value
    always stays floating point to avoid a lossy narrowing.

    For a ``decimal`` peer the coercion depends on the operation, selected by
    ``decimal_literal``:

    - ``"peer"`` (comparisons) -- the ``functions_comparison`` overloads use
      ``any1, any1`` and so require *identical* operand types, so the literal must
      take the column's exact ``decimal(precision, scale)``. That is only sound
      when the value is *exactly* representable there; if it would need a finer
      scale or overflow the precision this raises rather than silently rounding or
      truncating the comparison, so the user coerces explicitly with
      ``lit(value, <decimal type>)`` or by casting the column.
    - ``"natural"`` (arithmetic) -- ``functions_arithmetic_decimal`` accepts
      ``decimal<P1,S1>, decimal<P2,S2>`` and derives the result type, so the
      literal keeps its own natural decimal type (lossless).

    A ``float`` against a decimal peer still stays floating point (so it raises
    rather than being silently turned into a decimal); pass a ``Decimal``.
    """
    kind = peer_type.WhichOneof("kind")
    if isinstance(value, float):
        return _t.fp32() if kind == "fp32" else _t.fp64()
    if kind == "decimal":
        if decimal_literal == "peer":
            scale = peer_type.decimal.scale
            precision = peer_type.decimal.precision
            dec = value if isinstance(value, _Decimal) else _Decimal(value)
            if not dec.is_finite():
                raise TypeError("cannot compare against a non-finite Decimal literal")
            column = f"decimal(precision={precision}, scale={scale})"
            unscaled = _exact_unscaled(dec, scale)
            if unscaled is None:
                raise ValueError(
                    f"decimal literal {value!r} has a finer scale than the {column} "
                    f"column it is compared to; comparing them would round it. Wrap "
                    f"it with lit(value, <decimal type>) or cast the column."
                )
            if abs(unscaled) >= 10**precision:
                raise ValueError(
                    f"decimal literal {value!r} does not fit the {column} column it "
                    f"is compared to. Wrap it with lit(value, <decimal type>) or cast "
                    f"the column."
                )
            return _t.decimal(scale, precision)
        return _decimal_type(value if isinstance(value, _Decimal) else _Decimal(value))
    builder = _NUMERIC_BUILDERS.get(kind)
    return builder() if builder else _t.i64()


def _resolve_over_urns(
    builder, urns, name, bound, base_schema, registry, *, alias=None, options=None
):
    """Resolve ``name`` over ``urns`` (in order) against the bound operands' types.

    Builds with the first URN whose overload matches the operands' signature and
    raises a uniform error if none do. Shared by the operator path
    (:func:`_numeric_binary`) and the ``f.*`` namespace's multi-URN helper
    (``substrait.dataframe.functions._multi_urn_helper``) so both resolve
    identically and their error text cannot drift apart. The registry finds the
    winning extension across every candidate URN in one call; ``entry.urn``
    recovers it so ``builder`` can rebuild against the concrete overload.
    """
    signature = [
        typ
        for b in bound
        for typ in infer_extended_expression_schema(b, registry=registry).types
    ]
    match = registry.find_function(name, signature, urns)
    if match is not None:
        winning_urn = match[0].urn
        return builder(
            winning_urn, name, expressions=bound, alias=alias, options=options
        )(base_schema, registry)
    kinds = [t.WhichOneof("kind") for t in signature]
    raise Exception(
        f"No matching overload for '{name}' across {urns} with signature {kinds}"
    )


def _numeric_binary(
    self_expr: "Expr",
    other: Any,
    urns: Union[str, list],
    fn: str,
    *,
    swap: bool = False,
    decimal_literal: str = "natural",
) -> "Expr":
    """Build a binary comparison/arithmetic expression with literal coercion.

    A bare Python number is typed to match the *other* (column) operand at
    resolve time, so mixed-width numeric comparisons and arithmetic resolve
    against the standard extension overloads. ``swap`` handles reflected
    operators (e.g. ``100 - col("a")``), keeping operand order intact.

    ``urns`` may be a single URN or a list tried in order: arithmetic passes
    ``[functions_arithmetic, functions_arithmetic_decimal]`` so decimal operands
    fall through to the decimal extension when the base one has no overload,
    mirroring the ``f.*`` namespace's multi-URN resolution. ``decimal_literal``
    (``"natural"`` / ``"peer"``) is forwarded to :func:`_match_numeric_type` to
    pick how a decimal literal is coerced against a decimal peer.
    """
    urns = [urns] if isinstance(urns, str) else list(urns)
    left_operand = other if swap else self_expr
    right_operand = self_expr if swap else other

    def resolve(base_schema, registry):
        def bind(operand):
            if isinstance(operand, Expr):
                return operand._unbound(base_schema, registry), True
            return operand, False

        left_val, left_is_expr = bind(left_operand)
        right_val, right_is_expr = bind(right_operand)

        peer = None
        if left_is_expr:
            peer = infer_extended_expression_schema(left_val, registry=registry).types[
                0
            ]
        elif right_is_expr:
            peer = infer_extended_expression_schema(right_val, registry=registry).types[
                0
            ]

        def as_bound(value, is_expr):
            if is_expr:
                return value
            if peer is not None and not isinstance(value, bool):
                # int/float coerce to match any numeric peer; a Decimal only when
                # the peer is itself decimal (else keep its natural decimal type).
                peer_is_decimal = peer.WhichOneof("kind") == "decimal"
                if isinstance(value, (int, float)) or (
                    isinstance(value, _Decimal) and peer_is_decimal
                ):
                    lit_type = _match_numeric_type(
                        peer, value, decimal_literal=decimal_literal
                    )
                    return literal(value, lit_type)(base_schema, registry)
            return Expr._coerce(value)._unbound(base_schema, registry)

        left_bound = as_bound(left_val, left_is_expr)
        right_bound = as_bound(right_val, right_is_expr)
        return _resolve_over_urns(
            scalar_function, urns, fn, [left_bound, right_bound], base_schema, registry
        )

    return Expr(resolve)


_COMPARISON_OPS = {
    "lt": stalg.Expression.Subquery.SetComparison.COMPARISON_OP_LT,
    "lte": stalg.Expression.Subquery.SetComparison.COMPARISON_OP_LE,
    "gt": stalg.Expression.Subquery.SetComparison.COMPARISON_OP_GT,
    "gte": stalg.Expression.Subquery.SetComparison.COMPARISON_OP_GE,
    "equal": stalg.Expression.Subquery.SetComparison.COMPARISON_OP_EQ,
    "not_equal": stalg.Expression.Subquery.SetComparison.COMPARISON_OP_NE,
}


class _SubqueryReduction:
    """A subquery wrapped by :func:`any_` / :func:`all_`, consumed by a
    comparison operator to build a ``left <op> ANY/ALL (subquery)`` expression."""

    __slots__ = ("reduction_op", "plan")

    def __init__(self, reduction_op, plan):
        self.reduction_op = reduction_op
        self.plan = plan


def _plan_of(query: Any):
    """Extract the underlying (unbound) plan from a DataFrame-like subquery arg."""
    plan = getattr(query, "_plan", None)
    if plan is None:
        raise TypeError("a subquery expects a DataFrame")
    return plan


# Sort direction keyed by (descending, nulls_last); the canonical mapping for the
# DataFrame/Expr layer, shared with ``substrait.dataframe.frame``.
_SORT_DIRECTIONS = {
    (False, False): stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST,
    (False, True): stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST,
    (True, False): stalg.SortField.SORT_DIRECTION_DESC_NULLS_FIRST,
    (True, True): stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST,
}


def sort_direction(descending: bool, nulls_last: bool):
    """The ``SortField.SortDirection`` for a ``(descending, nulls_last)`` pair."""
    return _SORT_DIRECTIONS[(bool(descending), bool(nulls_last))]


def _window_bound(value):
    """Map an int/None frame endpoint to a WindowFunction.Bound.

    ``None`` -> unbounded, ``0`` -> current row, negative -> N preceding,
    positive -> N following.
    """
    Bound = stalg.Expression.WindowFunction.Bound
    if value is None:
        return Bound(unbounded=Bound.Unbounded())
    if value == 0:
        return Bound(current_row=Bound.CurrentRow())
    if value < 0:
        return Bound(preceding=Bound.Preceding(offset=-value))
    return Bound(following=Bound.Following(offset=value))


class Expr:
    """A composable, unbound Substrait expression."""

    __slots__ = ("_unbound",)

    def __init__(self, unbound: UnboundExtendedExpression):
        self._unbound = unbound

    @property
    def unbound(self) -> UnboundExtendedExpression:
        """The underlying builder callable, for interop with the builder layer."""
        return self._unbound

    @staticmethod
    def _coerce(value: Union["Expr", Any]) -> "Expr":
        if isinstance(value, Expr):
            return value
        return Expr(literal(value, infer_literal_type(value)))

    def _scalar(self, urn: str, fn: str, *others: Any) -> "Expr":
        args = [self._unbound] + [Expr._coerce(o)._unbound for o in others]
        return Expr(scalar_function(urn, fn, expressions=args))

    # -- comparison -------------------------------------------------------
    def _compare(self, other: Any, fn: str) -> "Expr":
        # `col <op> any_(df)/all_(df)` builds a SetComparison subquery instead.
        if isinstance(other, _SubqueryReduction):
            return Expr(
                _set_comparison(
                    self._unbound, other.plan, other.reduction_op, _COMPARISON_OPS[fn]
                )
            )
        return _numeric_binary(
            self, other, FUNCTIONS_COMPARISON, fn, decimal_literal="peer"
        )

    def __lt__(self, other: Any) -> "Expr":
        return self._compare(other, "lt")

    def __le__(self, other: Any) -> "Expr":
        return self._compare(other, "lte")

    def __gt__(self, other: Any) -> "Expr":
        return self._compare(other, "gt")

    def __ge__(self, other: Any) -> "Expr":
        return self._compare(other, "gte")

    def __eq__(self, other: Any) -> "Expr":  # type: ignore[override]
        return self._compare(other, "equal")

    def __ne__(self, other: Any) -> "Expr":  # type: ignore[override]
        return self._compare(other, "not_equal")

    # Operator-overloaded ``__eq__`` means an Expr is not a normal value; like
    # pandas/Polars expressions it is intentionally not hashable.
    __hash__ = None  # type: ignore[assignment]

    # -- arithmetic -------------------------------------------------------
    def __add__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "add")

    def __sub__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "subtract")

    def __mul__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "multiply")

    def __truediv__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "divide")

    def __radd__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "add", swap=True)

    def __rsub__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "subtract", swap=True)

    def __rmul__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "multiply", swap=True)

    def __rtruediv__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "divide", swap=True)

    def __mod__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "modulus")

    def __rmod__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "modulus", swap=True)

    def __pow__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "power")

    def __rpow__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, _ARITHMETIC_URNS, "power", swap=True)

    def __neg__(self) -> "Expr":
        return Expr(
            scalar_function(FUNCTIONS_ARITHMETIC, "negate", expressions=[self._unbound])
        )

    # -- boolean logic ----------------------------------------------------
    def __and__(self, other: Any) -> "Expr":
        return self._scalar(FUNCTIONS_BOOLEAN, "and", other)

    def __or__(self, other: Any) -> "Expr":
        return self._scalar(FUNCTIONS_BOOLEAN, "or", other)

    def __xor__(self, other: Any) -> "Expr":
        return self._scalar(FUNCTIONS_BOOLEAN, "xor", other)

    def __invert__(self) -> "Expr":
        return Expr(
            scalar_function(FUNCTIONS_BOOLEAN, "not", expressions=[self._unbound])
        )

    # -- helpers ----------------------------------------------------------
    def is_null(self) -> "Expr":
        return Expr(
            scalar_function(
                FUNCTIONS_COMPARISON, "is_null", expressions=[self._unbound]
            )
        )

    def is_not_null(self) -> "Expr":
        return Expr(
            scalar_function(
                FUNCTIONS_COMPARISON, "is_not_null", expressions=[self._unbound]
            )
        )

    def is_nan(self) -> "Expr":
        return Expr(
            scalar_function(FUNCTIONS_COMPARISON, "is_nan", expressions=[self._unbound])
        )

    def is_distinct_from(self, other: Any) -> "Expr":
        """Null-safe inequality (``NULL`` distinct from a value / from ``NULL``)."""
        return self._scalar(FUNCTIONS_COMPARISON, "is_distinct_from", other)

    def is_not_distinct_from(self, other: Any) -> "Expr":
        """Null-safe equality (``NULL`` equals ``NULL``)."""
        return self._scalar(FUNCTIONS_COMPARISON, "is_not_distinct_from", other)

    def between(self, low: Any, high: Any) -> "Expr":
        """Inclusive range test, ``low <= self <= high``.

        Like the ``f.*`` helpers, the bounds are not coerced to this column's
        numeric type; pass matching literals or ``lit(..., type)`` when needed.
        """
        return self._scalar(FUNCTIONS_COMPARISON, "between", low, high)

    def is_in(self, options: Any) -> "Expr":
        """True when this expression equals any value in ``options`` (SQL ``IN``).

        ``options`` is a collection of values or expressions, e.g.
        ``col("status").is_in(["active", "pending"])``.
        """
        if isinstance(options, (str, bytes)):
            raise TypeError("is_in expects a collection of values, not a string")
        bound = [Expr._coerce(o)._unbound for o in options]
        return Expr(singular_or_list(self._unbound, bound))

    def in_subquery(self, subquery: Any, alias: Union[str, None] = None) -> "Expr":
        """True when this expression is among a subquery's rows (``x IN (SELECT ...)``).

        ``subquery`` is a DataFrame producing a single output column.
        """
        return Expr(_in_predicate([self._unbound], _plan_of(subquery), alias=alias))

    # -- nested access ----------------------------------------------------
    def _append_segment(self, make_segment) -> "Expr":
        """Append a nested ReferenceSegment child to the deepest segment."""
        inner = self._unbound

        def resolve(base_schema, registry):
            bound = inner(base_schema, registry)
            expr = bound.referred_expr[0].expression
            if expr.WhichOneof(
                "rex_type"
            ) != "selection" or not expr.selection.HasField("direct_reference"):
                raise TypeError("nested access requires a direct field reference")
            segment = expr.selection.direct_reference
            while True:
                holder = getattr(segment, segment.WhichOneof("reference_type"))
                if holder.HasField("child"):
                    segment = holder.child
                else:
                    holder.child.CopyFrom(make_segment(base_schema, registry))
                    break
            return bound

        return Expr(resolve)

    def struct_field(self, index: int) -> "Expr":
        """Access a nested struct field by position."""
        return self._append_segment(
            lambda _s, _r: stalg.Expression.ReferenceSegment(
                struct_field=stalg.Expression.ReferenceSegment.StructField(field=index)
            )
        )

    def list_element(self, offset: int) -> "Expr":
        """Access a list element by offset (also ``expr[offset]``)."""
        return self._append_segment(
            lambda _s, _r: stalg.Expression.ReferenceSegment(
                list_element=stalg.Expression.ReferenceSegment.ListElement(
                    offset=offset
                )
            )
        )

    def __getitem__(self, offset: int) -> "Expr":
        if not isinstance(offset, int) or isinstance(offset, bool):
            raise TypeError(
                "indexing selects a list element by integer offset; "
                "use struct_field(i) or map_key(k) for structs/maps"
            )
        return self.list_element(offset)

    def map_key(self, key: Any) -> "Expr":
        """Access a map value by key."""

        def make(base_schema, registry):
            key_lit = (
                Expr._coerce(key)
                ._unbound(base_schema, registry)
                .referred_expr[0]
                .expression.literal
            )
            return stalg.Expression.ReferenceSegment(
                map_key=stalg.Expression.ReferenceSegment.MapKey(map_key=key_lit)
            )

        return self._append_segment(make)

    # -- higher-order list functions --------------------------------------
    def _higher_order(self, function: str, callback) -> "Expr":
        """Apply a list higher-order function whose lambda ``callback`` receives
        an :class:`Expr` bound to the current list element."""
        list_unbound = self._unbound

        def resolve(base_schema, registry):
            bound_list = list_unbound(base_schema, registry)
            element_type = (
                infer_extended_expression_schema(bound_list, registry=registry)
                .types[0]
                .list.type
            )
            param_struct = stp.Type.Struct(
                types=[element_type], nullability=stp.Type.NULLABILITY_REQUIRED
            )
            param_ns = stp.NamedStruct(names=["element"], struct=param_struct)
            param_ref = stalg.Expression(
                selection=stalg.Expression.FieldReference(
                    lambda_parameter_reference=(
                        stalg.Expression.FieldReference.LambdaParameterReference(
                            steps_out=0
                        )
                    ),
                    direct_reference=stalg.Expression.ReferenceSegment(
                        struct_field=stalg.Expression.ReferenceSegment.StructField(
                            field=0
                        )
                    ),
                )
            )
            element = Expr(
                lambda _bs, _r: stee.ExtendedExpression(
                    referred_expr=[
                        stee.ExpressionReference(
                            expression=param_ref, output_names=["element"]
                        )
                    ],
                    base_schema=param_ns,
                )
            )
            body = Expr._coerce(callback(element))._unbound(param_ns, registry)
            lambda_expr = stalg.Expression(
                **{
                    "lambda": stalg.Expression.Lambda(
                        parameters=param_struct,
                        body=body.referred_expr[0].expression,
                    )
                }
            )
            lambda_ee = stee.ExtendedExpression(
                referred_expr=[
                    stee.ExpressionReference(
                        expression=lambda_expr, output_names=["lambda"]
                    )
                ],
                base_schema=base_schema,
            )
            return scalar_function(
                FUNCTIONS_LIST, function, expressions=[bound_list, lambda_ee]
            )(base_schema, registry)

        return Expr(resolve)

    def list_transform(self, fn) -> "Expr":
        """Map a function over each element of this list column (``transform``).

        ``fn`` receives an ``Expr`` for the current element, e.g.
        ``col("xs").list_transform(lambda x: x + 1)``.
        """
        return self._higher_order("transform", fn)

    def list_filter(self, fn) -> "Expr":
        """Keep list elements for which ``fn(element)`` is true (``filter``)."""
        return self._higher_order("filter", fn)

    def switch(self, cases: dict, default: Any) -> "Expr":
        """Value-match CASE against literal keys::

            col("code").switch({1: "one", 2: "two"}, default="other")

        Keys must be Python scalars (they become literals); each value may be an
        ``Expr`` or a scalar.
        """
        ifs = [
            (Expr._coerce(k)._unbound, Expr._coerce(v)._unbound)
            for k, v in cases.items()
        ]
        return Expr(switch(self._unbound, ifs, Expr._coerce(default)._unbound))

    def distinct(self) -> "Expr":
        """Make this aggregate operate on distinct inputs (``COUNT(DISTINCT x)``).

        Only meaningful on an aggregate measure (e.g. ``f.count(col("x")).distinct()``).
        """
        inner = self._unbound

        def resolve(base_schema, registry):
            bound = inner(base_schema, registry)
            ref = bound.referred_expr[0]
            if ref.WhichOneof("expr_type") != "measure":
                raise TypeError("distinct() applies only to aggregate measures")
            ref.measure.invocation = (
                stalg.AggregateFunction.AGGREGATION_INVOCATION_DISTINCT
            )
            return bound

        return Expr(resolve)

    def order_by(
        self, *keys: Any, descending: bool = False, nulls_last: bool = True
    ) -> "Expr":
        """Order the inputs to this aggregate (``string_agg(x ORDER BY ...)``).

        ``keys`` are column names or expressions; ``descending``/``nulls_last``
        apply to all of them. Only meaningful on an aggregate measure.
        """
        direction = sort_direction(descending, nulls_last)
        inner = self._unbound

        def resolve(base_schema, registry):
            bound = inner(base_schema, registry)
            ref = bound.referred_expr[0]
            if ref.WhichOneof("expr_type") != "measure":
                raise TypeError("order_by() applies only to aggregate measures")
            for k in keys:
                unbound_key = k.unbound if isinstance(k, Expr) else column(k)
                bound_key = resolve_expression(unbound_key, base_schema, registry)
                ref.measure.sorts.append(
                    stalg.SortField(
                        expr=bound_key.referred_expr[0].expression, direction=direction
                    )
                )
            return bound

        return Expr(resolve)

    def over(
        self,
        partition_by: Any = (),
        order_by: Any = (),
        *,
        descending: bool = False,
        nulls_last: bool = True,
        rows: Union[tuple, None] = None,
        range: Union[tuple, None] = None,
    ) -> "Expr":
        """Turn a window function into a windowed expression (SQL ``OVER (...)``).

        ``partition_by`` / ``order_by`` are a column name/expression or a list of
        them; ``descending``/``nulls_last`` apply to the ordering. A frame may be
        given as ``rows=(start, end)`` or ``range=(start, end)`` where each
        endpoint is an int offset (negative = preceding, ``0`` = current row,
        positive = following) or ``None`` = unbounded.
        """
        if rows is not None and range is not None:
            raise ValueError("specify at most one of rows= or range=")
        partitions = (
            [partition_by]
            if isinstance(partition_by, (str, Expr))
            else list(partition_by)
        )
        order_keys = [order_by] if isinstance(order_by, (str, Expr)) else list(order_by)
        direction = sort_direction(descending, nulls_last)
        inner = self._unbound

        def resolve(base_schema, registry):
            bound = inner(base_schema, registry)
            expr = bound.referred_expr[0].expression
            if expr.WhichOneof("rex_type") != "window_function":
                raise TypeError("over() applies only to window functions")
            wf = expr.window_function
            for p in partitions:
                key = p.unbound if isinstance(p, Expr) else column(p)
                bound_p = resolve_expression(key, base_schema, registry)
                wf.partitions.append(bound_p.referred_expr[0].expression)
            for k in order_keys:
                key = k.unbound if isinstance(k, Expr) else column(k)
                bound_k = resolve_expression(key, base_schema, registry)
                wf.sorts.append(
                    stalg.SortField(
                        expr=bound_k.referred_expr[0].expression, direction=direction
                    )
                )
            frame = rows if rows is not None else range
            if frame is not None:
                wf.bounds_type = (
                    stalg.Expression.WindowFunction.BOUNDS_TYPE_ROWS
                    if rows is not None
                    else stalg.Expression.WindowFunction.BOUNDS_TYPE_RANGE
                )
                lower, upper = frame
                wf.lower_bound.CopyFrom(_window_bound(lower))
                wf.upper_bound.CopyFrom(_window_bound(upper))
            return bound

        return Expr(resolve)

    def filter(self, predicate: Any) -> "Measure":
        """Restrict this aggregate to rows where ``predicate`` holds
        (SQL ``agg(x) FILTER (WHERE predicate)``).

        Returns a :class:`Measure`, only meaningful inside ``group_by().agg(...)``::

            f.sum(col("amount")).filter(col("status") == "paid")
        """
        return Measure(self, Expr._coerce(predicate))

    def cast(self, type: Any) -> "Expr":
        """Cast this expression to ``type`` (a proto.Type or a type builder).

        The explicit escape hatch when automatic literal coercion is not enough,
        e.g. between two columns of different numeric types::

            col("small_i32").cast(sub.i64) + col("big_i64")
        """
        if callable(type):  # allow a bare builder / DataType, e.g. sub.i64
            type = type()
        return Expr(cast(self._unbound, type))

    def alias(self, name: str) -> "Expr":
        """Return a copy of this expression with its output name set to ``name``."""
        return Expr(_alias(self._unbound, name))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "Expr(<unbound>)"


class Measure:
    """An aggregate expression paired with a ``FILTER (WHERE ...)`` predicate.

    Produced by :meth:`Expr.filter` and consumed by
    ``DataFrame.group_by(...).agg(...)``; not a standalone expression.
    """

    __slots__ = ("expr", "predicate")

    def __init__(self, expr: Expr, predicate: Expr):
        self.expr = expr
        self.predicate = predicate

    def alias(self, name: str) -> "Measure":
        return Measure(self.expr.alias(name), self.predicate)

    def distinct(self) -> "Measure":
        return Measure(self.expr.distinct(), self.predicate)

    def order_by(self, *keys: Any, **kwargs: Any) -> "Measure":
        return Measure(self.expr.order_by(*keys, **kwargs), self.predicate)


class When:
    """Intermediate for building a CASE expression; see :func:`when`."""

    __slots__ = ("_clauses", "_pending")

    def __init__(self, clauses: list, pending: Union[Expr, None]):
        self._clauses = clauses  # list[(cond Expr, value Expr)] completed
        self._pending = pending  # a condition Expr awaiting .then(), or None

    def when(self, condition: Any) -> "When":
        if self._pending is not None:
            raise ValueError("call .then(...) before starting another .when(...)")
        return When(self._clauses, Expr._coerce(condition))

    def then(self, value: Any) -> "When":
        if self._pending is None:
            raise ValueError(".then(...) must follow a .when(...)")
        return When(self._clauses + [(self._pending, Expr._coerce(value))], None)

    def otherwise(self, default: Any) -> Expr:
        if self._pending is not None:
            raise ValueError("call .then(...) before .otherwise(...)")
        if not self._clauses:
            raise ValueError("a CASE needs at least one when(...).then(...)")
        ifs = [(c._unbound, v._unbound) for c, v in self._clauses]
        return Expr(if_then(ifs, Expr._coerce(default)._unbound))


def when(condition: Any) -> When:
    """Begin a CASE expression, PySpark/Polars-style::

        when(col("x") > 0).then("pos").when(col("x") < 0).then("neg").otherwise("zero")

    Chain ``.then(value)`` after each ``.when(condition)`` and finish with
    ``.otherwise(default)``, which returns the :class:`Expr`.
    """
    return When([], Expr._coerce(condition))


def coalesce(*exprs: Any) -> Expr:
    """First non-null among ``exprs`` (SQL ``COALESCE``)."""
    if not exprs:
        raise ValueError("coalesce needs at least one expression")
    args = [Expr._coerce(e)._unbound for e in exprs]
    return Expr(scalar_function(FUNCTIONS_COMPARISON, "coalesce", expressions=args))


def parameter(index: int, type: Any, alias: Union[str, None] = None) -> Expr:
    """A dynamic (runtime-bound) parameter of the given ``type``.

    ``index`` is the 0-based position bound via the plan's parameter bindings;
    ``type`` may be a ``proto.Type`` or a bare type builder (e.g. ``sub.i64``).
    """
    if callable(type):
        type = type()
    return Expr(_dynamic_parameter(index, type, alias))


def current_timestamp(precision: int = 6, alias: Union[str, None] = None) -> Expr:
    """The query's execution timestamp (``precision_timestamp_tz``)."""
    return Expr(
        _execution_context_variable(
            "current_timestamp",
            stp.Type.PrecisionTimestampTZ(
                precision=precision, nullability=stp.Type.NULLABILITY_REQUIRED
            ),
            alias,
        )
    )


def current_date(alias: Union[str, None] = None) -> Expr:
    """The query's execution date."""
    return Expr(
        _execution_context_variable(
            "current_date",
            stp.Type.Date(nullability=stp.Type.NULLABILITY_REQUIRED),
            alias,
        )
    )


def current_timezone(alias: Union[str, None] = None) -> Expr:
    """The query's execution timezone (a ``string``)."""
    return Expr(
        _execution_context_variable(
            "current_timezone",
            stp.Type.String(nullability=stp.Type.NULLABILITY_REQUIRED),
            alias,
        )
    )


def scalar_subquery(subquery: Any, alias: Union[str, None] = None) -> Expr:
    """The single value of a one-row/one-column subquery (a DataFrame)."""
    return Expr(_scalar_subquery(_plan_of(subquery), alias=alias))


def exists(subquery: Any, alias: Union[str, None] = None) -> Expr:
    """``EXISTS (subquery)`` -- true when the subquery returns any row."""
    op = stalg.Expression.Subquery.SetPredicate.PREDICATE_OP_EXISTS
    return Expr(_set_predicate(_plan_of(subquery), op, alias=alias))


def unique(subquery: Any, alias: Union[str, None] = None) -> Expr:
    """``UNIQUE (subquery)`` -- true when the subquery has no duplicate rows."""
    op = stalg.Expression.Subquery.SetPredicate.PREDICATE_OP_UNIQUE
    return Expr(_set_predicate(_plan_of(subquery), op, alias=alias))


def any_(subquery: Any) -> _SubqueryReduction:
    """Use in a comparison: ``col("x") > any_(df)`` (SQL ``> ANY (subquery)``)."""
    op = stalg.Expression.Subquery.SetComparison.REDUCTION_OP_ANY
    return _SubqueryReduction(op, _plan_of(subquery))


def all_(subquery: Any) -> _SubqueryReduction:
    """Use in a comparison: ``col("x") > all_(df)`` (SQL ``> ALL (subquery)``)."""
    op = stalg.Expression.Subquery.SetComparison.REDUCTION_OP_ALL
    return _SubqueryReduction(op, _plan_of(subquery))


def col(name: Union[str, int]) -> Expr:
    """Reference an input column by name or index."""
    return Expr(column(name))


def outer(name: Union[str, int], steps_out: int = 1) -> Expr:
    """Reference a column from an enclosing query (a correlated reference).

    Only valid inside a subquery, e.g. a correlated ``exists``::

        outer_df.filter(sub.exists(inner_df.filter(sub.col("k") == sub.outer("k"))))

    ``steps_out`` counts query-nesting levels outward (1 = the immediately
    enclosing query), matching Substrait's requirement that ``steps_out`` be
    >= 1.
    """
    return Expr(_outer_reference(name, steps_out))


def lit(value: Any, type: Union[stp.Type, None] = None) -> Expr:
    """A literal expression. The Substrait type is inferred when omitted.

    Pass ``value=None`` to build a typed null; a ``type`` is required in that
    case since there is nothing to infer from.
    """
    if type is None:
        if value is None:
            raise TypeError("lit(None) needs an explicit type, e.g. lit(None, sub.i64)")
        type = infer_literal_type(value)
    elif callable(type):  # allow passing a bare type builder, e.g. sub.i64
        type = type()
    return Expr(literal(value, type))
