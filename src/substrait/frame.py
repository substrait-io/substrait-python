"""The Substrait-native DataFrame.

This module is the **native** fluent frame -- the primary, engine-agnostic way
to build a Substrait plan in Python (analogous to how ``daft.DataFrame`` is
Daft's own native frame). It is a thin, chainable wrapper over the
``substrait.builders.plan`` functions: it carries an ``ExtensionRegistry`` so it
does not have to be threaded through every call, and it takes
:class:`~substrait.expr.Expr` objects (or bare column names / Python scalars)
rather than raw ``scalar_function`` invocations::

    import substrait.api as sub

    plan = (
        sub.read_named_table("people", {"id": sub.i64, "age": sub.i64})
        .filter(sub.col("age") > 25)
        .select("id")
        .to_plan()
    )

Verb naming follows Polars: ``select`` replaces the projection, ``with_columns``
appends.

Relationship to :mod:`substrait.narwhals`: that module is the **Narwhals
integration layer** -- a compliant wrapper that lets ``narwhals`` drive plan
construction (``nw.from_native(...)``). It adapts Narwhals calls down onto this
native frame; the two layers compose rather than compete.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Union

import substrait.algebra_pb2 as stalg
import substrait.type_pb2 as stp

from substrait.builders import plan as _plan
from substrait.builders import type as _type
from substrait.expr import Expr, col, lit
from substrait.extension_registry import ExtensionRegistry

_JOIN_TYPES = {
    "inner": stalg.JoinRel.JOIN_TYPE_INNER,
    "left": stalg.JoinRel.JOIN_TYPE_LEFT,
    "right": stalg.JoinRel.JOIN_TYPE_RIGHT,
    "outer": stalg.JoinRel.JOIN_TYPE_OUTER,
    "left_semi": stalg.JoinRel.JOIN_TYPE_LEFT_SEMI,
    "left_anti": stalg.JoinRel.JOIN_TYPE_LEFT_ANTI,
}

_default_registry: Optional[ExtensionRegistry] = None


def default_registry() -> ExtensionRegistry:
    """A lazily-created registry preloaded with the standard extensions."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ExtensionRegistry(load_default_extensions=True)
    return _default_registry


def _to_named_struct(schema: Any) -> stp.NamedStruct:
    if isinstance(schema, stp.NamedStruct):
        return schema
    if isinstance(schema, dict):
        names = list(schema.keys())
        types = [t() if callable(t) else t for t in schema.values()]
        return _type.named_struct(
            names=names, struct=_type.struct(types=types, nullable=False)
        )
    raise TypeError(
        "schema must be a NamedStruct or a {name: type} dict, "
        f"got {type(schema).__name__}"
    )


def _unbound(value: Any):
    """Accept an Expr, a bare column name, or an existing unbound callable."""
    if isinstance(value, Expr):
        return value.unbound
    if isinstance(value, str):
        return col(value).unbound
    return value  # assume already an unbound expression callable


class DataFrame:
    """The Substrait-native fluent DataFrame.

    Build plans directly (``df.filter(...).select(...).to_plan()``). For the
    Narwhals-driven equivalent, see :class:`substrait.narwhals.DataFrame`, which
    wraps this frame to satisfy the Narwhals backend protocol.
    """

    def __init__(self, plan, registry: Optional[ExtensionRegistry] = None):
        self._plan = plan
        self._registry = registry or default_registry()

    def _next(self, plan) -> "DataFrame":
        return DataFrame(plan, self._registry)

    @property
    def f(self):
        """Function namespace bound to this DataFrame's registry.

        Use this instead of the global ``sub.f`` when the DataFrame was built
        with a registry carrying custom extensions, so those functions are
        reachable by name (e.g. ``df.f.my_double(df_col)``).
        """
        cached = getattr(self, "_functions_ns", None)
        if cached is None:
            from substrait.functions import functions_for

            cached = functions_for(self._registry)
            self._functions_ns = cached
        return cached

    def filter(self, predicate: Union[Expr, Any]) -> "DataFrame":
        return self._next(_plan.filter(self._plan, expression=_unbound(predicate)))

    def select(self, *columns: Union[str, Expr]) -> "DataFrame":
        return self._next(
            _plan.select(self._plan, expressions=[_unbound(c) for c in columns])
        )

    def with_columns(
        self, *exprs: Union[str, Expr], **named: Union[Expr, Any]
    ) -> "DataFrame":
        expressions = [_unbound(e) for e in exprs]
        expressions += [Expr._coerce(v).alias(k).unbound for k, v in named.items()]
        return self._next(_plan.project(self._plan, expressions=expressions))

    def sort(self, *columns: Union[str, Expr], descending: bool = False) -> "DataFrame":
        direction = (
            stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST
            if descending
            else stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST
        )
        expressions = [(_unbound(c), direction) for c in columns]
        return self._next(_plan.sort(self._plan, expressions=expressions))

    def limit(self, n: int, offset: int = 0) -> "DataFrame":
        return self._next(
            _plan.fetch(
                self._plan,
                offset=lit(offset, _type.i64()).unbound,
                count=lit(n, _type.i64()).unbound,
            )
        )

    def join(
        self,
        other: "DataFrame",
        on: Union[Expr, Any],
        how: str = "inner",
    ) -> "DataFrame":
        """Join with another DataFrame.

        ``on`` is an expression evaluated against the concatenation of the left
        and right schemas (columns are referenced by name across both inputs).
        ``how`` is one of ``inner``, ``left``, ``right``, ``outer``,
        ``left_semi`` or ``left_anti``.
        """
        try:
            join_type = _JOIN_TYPES[how]
        except KeyError:
            raise ValueError(
                f"unknown join type {how!r}; expected one of {sorted(_JOIN_TYPES)}"
            ) from None
        return self._next(
            _plan.join(self._plan, other._plan, expression=_unbound(on), type=join_type)
        )

    def group_by(self, *keys: Union[str, Expr]) -> "GroupBy":
        """Begin an aggregation; follow with ``.agg(...)``."""
        return GroupBy(self, keys)

    def aggregate(
        self,
        group_by: Union[str, Expr, Iterable[Union[str, Expr]]] = (),
        *measures: Expr,
    ) -> "DataFrame":
        """One-shot aggregation. See also the fluent ``group_by().agg()``."""
        if isinstance(group_by, (str, Expr)):
            group_by = [group_by]
        return self._next(
            _plan.aggregate(
                self._plan,
                grouping_expressions=[_unbound(g) for g in group_by],
                measures=[_unbound(m) for m in measures],
            )
        )

    def to_plan(self):
        """Materialize to a ``substrait.proto.Plan``."""
        return self._plan(self._registry)

    # Kept for parity with the substrait.narwhals (Narwhals) wrapper's API.
    def to_substrait(self, registry: Optional[ExtensionRegistry] = None):
        return self._plan(registry or self._registry)


class GroupBy:
    """Intermediate returned by ``DataFrame.group_by``; call ``.agg(...)``."""

    def __init__(self, df: DataFrame, keys: Iterable[Union[str, Expr]]):
        self._df = df
        self._keys = list(keys)

    def agg(self, *measures: Expr) -> DataFrame:
        return self._df._next(
            _plan.aggregate(
                self._df._plan,
                grouping_expressions=[_unbound(k) for k in self._keys],
                measures=[_unbound(m) for m in measures],
            )
        )


def read_named_table(
    name: Union[str, Iterable[str]],
    schema: Any,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """Start a DataFrame from a named table and its schema.

    ``schema`` may be a ``NamedStruct`` or a ``{column_name: type}`` dict, where
    each type is a type builder (``sub.i64``) or a ``proto.Type``.
    """
    names = [name] if isinstance(name, str) else list(name)
    return DataFrame(_plan.read_named_table(names, _to_named_struct(schema)), registry)
