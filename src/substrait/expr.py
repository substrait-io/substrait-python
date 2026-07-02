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

import substrait.type_pb2 as stp

from substrait.builders import type as _t
from substrait.builders.extended_expression import (
    UnboundExtendedExpression,
    cast,
    column,
    literal,
    scalar_function,
)
from substrait.type_inference import infer_extended_expression_schema

# Standard Substrait function-extension URNs used by the operators below.
FUNCTIONS_COMPARISON = "extension:io.substrait:functions_comparison"
FUNCTIONS_ARITHMETIC = "extension:io.substrait:functions_arithmetic"
FUNCTIONS_BOOLEAN = "extension:io.substrait:functions_boolean"
FUNCTIONS_STRING = "extension:io.substrait:functions_string"
FUNCTIONS_AGGREGATE_GENERIC = "extension:io.substrait:functions_aggregate_generic"


def _decimal_type(value: _Decimal) -> stp.Type:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):  # NaN / Infinity have symbolic exponents
        raise TypeError("cannot infer a decimal literal type from a non-finite Decimal")
    scale = -exponent if exponent < 0 else 0
    precision = max(len(value.as_tuple().digits), scale, 1)
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


def _match_numeric_type(peer_type: stp.Type, value: Any) -> stp.Type:
    """Pick a literal type for ``value`` that matches a numeric ``peer_type``.

    Substrait does not implicitly coerce mixed numeric operands, so
    ``col("price_fp64") * 2`` needs the ``2`` typed as ``fp64`` rather than the
    default ``i64`` for the ``multiply`` overload to resolve. A ``float`` value
    always stays floating point to avoid a lossy narrowing.
    """
    kind = peer_type.WhichOneof("kind")
    if isinstance(value, float):
        return _t.fp32() if kind == "fp32" else _t.fp64()
    builder = _NUMERIC_BUILDERS.get(kind)
    return builder() if builder else _t.i64()


def _numeric_binary(
    self_expr: "Expr", other: Any, urn: str, fn: str, *, swap: bool = False
) -> "Expr":
    """Build a binary comparison/arithmetic expression with literal coercion.

    A bare Python number is typed to match the *other* (column) operand at
    resolve time, so mixed-width numeric comparisons and arithmetic resolve
    against the standard extension overloads. ``swap`` handles reflected
    operators (e.g. ``100 - col("a")``), keeping operand order intact.
    """
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
            peer = infer_extended_expression_schema(left_val).types[0]
        elif right_is_expr:
            peer = infer_extended_expression_schema(right_val).types[0]

        def as_bound(value, is_expr):
            if is_expr:
                return value
            if not isinstance(value, bool) and isinstance(value, (int, float)) and peer:
                lit_type = _match_numeric_type(peer, value)
                return literal(value, lit_type)(base_schema, registry)
            return Expr._coerce(value)._unbound(base_schema, registry)

        left_bound = as_bound(left_val, left_is_expr)
        right_bound = as_bound(right_val, right_is_expr)
        return scalar_function(urn, fn, expressions=[left_bound, right_bound])(
            base_schema, registry
        )

    return Expr(resolve)


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
    def __lt__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_COMPARISON, "lt")

    def __le__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_COMPARISON, "lte")

    def __gt__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_COMPARISON, "gt")

    def __ge__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_COMPARISON, "gte")

    def __eq__(self, other: Any) -> "Expr":  # type: ignore[override]
        return _numeric_binary(self, other, FUNCTIONS_COMPARISON, "equal")

    def __ne__(self, other: Any) -> "Expr":  # type: ignore[override]
        return _numeric_binary(self, other, FUNCTIONS_COMPARISON, "not_equal")

    # Operator-overloaded ``__eq__`` means an Expr is not a normal value; like
    # pandas/Polars expressions it is intentionally not hashable.
    __hash__ = None  # type: ignore[assignment]

    # -- arithmetic -------------------------------------------------------
    def __add__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_ARITHMETIC, "add")

    def __sub__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_ARITHMETIC, "subtract")

    def __mul__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_ARITHMETIC, "multiply")

    def __truediv__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_ARITHMETIC, "divide")

    def __radd__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_ARITHMETIC, "add", swap=True)

    def __rsub__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_ARITHMETIC, "subtract", swap=True)

    def __rmul__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_ARITHMETIC, "multiply", swap=True)

    def __rtruediv__(self, other: Any) -> "Expr":
        return _numeric_binary(self, other, FUNCTIONS_ARITHMETIC, "divide", swap=True)

    def __neg__(self) -> "Expr":
        return Expr(
            scalar_function(FUNCTIONS_ARITHMETIC, "negate", expressions=[self._unbound])
        )

    # -- boolean logic ----------------------------------------------------
    def __and__(self, other: Any) -> "Expr":
        return self._scalar(FUNCTIONS_BOOLEAN, "and", other)

    def __or__(self, other: Any) -> "Expr":
        return self._scalar(FUNCTIONS_BOOLEAN, "or", other)

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
        inner = self._unbound

        def resolve(base_schema, registry):
            bound = inner(base_schema, registry)
            bound.referred_expr[0].output_names[0] = name
            return bound

        return Expr(resolve)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "Expr(<unbound>)"


def col(name: Union[str, int]) -> Expr:
    """Reference an input column by name or index."""
    return Expr(column(name))


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
