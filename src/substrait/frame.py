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
from substrait.type_inference import infer_plan_schema

# All 13 JoinRel.JoinType variants (SET_OP_UNSPECIFIED excluded). "single"
# returns at most one right match per left row (runtime error on multiple);
# "mark" appends a nullable-boolean column flagging whether a partner exists.
_JOIN_TYPES = {
    "inner": stalg.JoinRel.JOIN_TYPE_INNER,
    "outer": stalg.JoinRel.JOIN_TYPE_OUTER,
    "left": stalg.JoinRel.JOIN_TYPE_LEFT,
    "right": stalg.JoinRel.JOIN_TYPE_RIGHT,
    "left_semi": stalg.JoinRel.JOIN_TYPE_LEFT_SEMI,
    "right_semi": stalg.JoinRel.JOIN_TYPE_RIGHT_SEMI,
    "left_anti": stalg.JoinRel.JOIN_TYPE_LEFT_ANTI,
    "right_anti": stalg.JoinRel.JOIN_TYPE_RIGHT_ANTI,
    "left_single": stalg.JoinRel.JOIN_TYPE_LEFT_SINGLE,
    "right_single": stalg.JoinRel.JOIN_TYPE_RIGHT_SINGLE,
    "left_mark": stalg.JoinRel.JOIN_TYPE_LEFT_MARK,
    "right_mark": stalg.JoinRel.JOIN_TYPE_RIGHT_MARK,
}

# Write create-modes: what to do when the target table already exists.
_CREATE_MODES = {
    "error": stalg.WriteRel.CREATE_MODE_ERROR_IF_EXISTS,
    "append": stalg.WriteRel.CREATE_MODE_APPEND_IF_EXISTS,
    "replace": stalg.WriteRel.CREATE_MODE_REPLACE_IF_EXISTS,
    "ignore": stalg.WriteRel.CREATE_MODE_IGNORE_IF_EXISTS,
}

# Sort direction keyed by (descending, nulls_last).
_SORT_DIRECTIONS = {
    (False, False): stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST,
    (False, True): stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST,
    (True, False): stalg.SortField.SORT_DIRECTION_DESC_NULLS_FIRST,
    (True, True): stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST,
}


def _per_column(value: Any, n: int, name: str) -> "list[bool]":
    """Broadcast a bool, or validate a per-column list of bools, to length ``n``."""
    if isinstance(value, (list, tuple)):
        if len(value) != n:
            raise ValueError(
                f"{name} has {len(value)} entries but {n} sort columns were given"
            )
        return [bool(v) for v in value]
    return [bool(value)] * n


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

    def rename(self, mapping: dict) -> "DataFrame":
        """Rename columns via a ``{old: new}`` mapping; others pass through.

        Implemented as a projection selecting every column, aliasing the renamed
        ones. Resolves the input schema, so unknown source columns raise.
        """
        inner = self._plan

        def resolve(registry: ExtensionRegistry):
            bound = inner(registry)
            names = list(infer_plan_schema(bound).names)
            unknown = set(mapping) - set(names)
            if unknown:
                raise ValueError(f"rename got unknown columns: {sorted(unknown)}")
            expressions = [
                (col(n).alias(mapping[n]) if n in mapping else col(n)).unbound
                for n in names
            ]
            return _plan.select(bound, expressions=expressions)(registry)

        return self._next(resolve)

    def drop(self, *columns: str) -> "DataFrame":
        """Drop the named columns, keeping the rest in their original order."""
        drop_set = set(columns)
        inner = self._plan

        def resolve(registry: ExtensionRegistry):
            bound = inner(registry)
            names = list(infer_plan_schema(bound).names)
            unknown = drop_set - set(names)
            if unknown:
                raise ValueError(f"drop got unknown columns: {sorted(unknown)}")
            expressions = [col(n).unbound for n in names if n not in drop_set]
            if not expressions:
                raise ValueError("drop would remove every column")
            return _plan.select(bound, expressions=expressions)(registry)

        return self._next(resolve)

    def sort(
        self,
        *columns: Union[str, Expr],
        descending: Union[bool, "list[bool]"] = False,
        nulls_last: Union[bool, "list[bool]"] = True,
    ) -> "DataFrame":
        """Order rows by one or more columns.

        ``descending`` and ``nulls_last`` are each either a single bool applied
        to every column, or a per-column list matching ``columns``. Together
        they select the four asc/desc x nulls-first/last ``SortDirection``
        values; ``nulls_last`` defaults to ``True``.
        """
        n = len(columns)
        desc = _per_column(descending, n, "descending")
        nulls = _per_column(nulls_last, n, "nulls_last")
        expressions = [
            (_unbound(c), _SORT_DIRECTIONS[(desc[i], nulls[i])])
            for i, c in enumerate(columns)
        ]
        return self._next(_plan.sort(self._plan, expressions=expressions))

    def limit(self, n: int, offset: int = 0) -> "DataFrame":
        return self._next(
            _plan.fetch(
                self._plan,
                offset=lit(offset, _type.i64()).unbound,
                count=lit(n, _type.i64()).unbound,
            )
        )

    def head(self, n: int = 5) -> "DataFrame":
        """The first ``n`` rows (alias for ``limit(n)``)."""
        return self.limit(n)

    def offset(self, n: int) -> "DataFrame":
        """Skip the first ``n`` rows, keeping all the rest."""
        return self._next(
            _plan.fetch(self._plan, offset=lit(n, _type.i64()).unbound, count=None)
        )

    def join(
        self,
        other: "DataFrame",
        on: Union[Expr, Any],
        how: str = "inner",
        *,
        post_filter: Union[Expr, Any, None] = None,
    ) -> "DataFrame":
        """Join with another DataFrame.

        ``on`` is an expression evaluated against the concatenation of the left
        and right schemas (columns are referenced by name across both inputs).
        ``how`` is one of ``inner``, ``outer``, ``left``, ``right``,
        ``left_semi``, ``right_semi``, ``left_anti``, ``right_anti``,
        ``left_single``, ``right_single``, ``left_mark`` or ``right_mark``.
        ``post_filter`` is an optional predicate applied to the join output.

        Overlapping column names from the two inputs are kept as-is (Substrait
        references columns positionally). Disambiguate them explicitly with
        ``rename``/``drop`` on either input before joining, or on the result.
        """
        try:
            join_type = _JOIN_TYPES[how]
        except KeyError:
            raise ValueError(
                f"unknown join type {how!r}; expected one of {sorted(_JOIN_TYPES)}"
            ) from None
        return self._next(
            _plan.join(
                self._plan,
                other._plan,
                expression=_unbound(on),
                type=join_type,
                post_join_filter=(
                    _unbound(post_filter) if post_filter is not None else None
                ),
            )
        )

    def cross_join(self, other: "DataFrame") -> "DataFrame":
        """Cartesian product with ``other`` (every left row paired with every
        right row)."""
        return self._next(_plan.cross(self._plan, other._plan))

    def union(self, *others: "DataFrame", distinct: bool = False) -> "DataFrame":
        """Concatenate rows of this DataFrame with ``others``.

        Defaults to keeping duplicates (``UNION ALL``); pass ``distinct=True``
        for set ``UNION``. All inputs must share this DataFrame's schema.
        """
        op = (
            stalg.SetRel.SET_OP_UNION_DISTINCT
            if distinct
            else stalg.SetRel.SET_OP_UNION_ALL
        )
        return self._set(others, op)

    def intersect(self, *others: "DataFrame", distinct: bool = True) -> "DataFrame":
        """Rows present in this DataFrame and in every ``other`` (SQL
        ``INTERSECT``). Pass ``distinct=False`` for ``INTERSECT ALL``."""
        op = (
            stalg.SetRel.SET_OP_INTERSECTION_MULTISET
            if distinct
            else stalg.SetRel.SET_OP_INTERSECTION_MULTISET_ALL
        )
        return self._set(others, op)

    def except_(self, *others: "DataFrame", distinct: bool = True) -> "DataFrame":
        """Rows in this DataFrame excluding any found in ``others`` (SQL
        ``EXCEPT``). Pass ``distinct=False`` for ``EXCEPT ALL``."""
        op = (
            stalg.SetRel.SET_OP_MINUS_PRIMARY
            if distinct
            else stalg.SetRel.SET_OP_MINUS_PRIMARY_ALL
        )
        return self._set(others, op)

    def _set(
        self, others: "tuple[DataFrame, ...]", op: "stalg.SetRel.SetOp"
    ) -> "DataFrame":
        if not others:
            raise ValueError("a set operation needs at least one other DataFrame")
        inputs = [self._plan, *(o._plan for o in others)]
        return self._next(_plan.set(inputs, op))

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

    def write_named_table(
        self, name: Union[str, Iterable[str]], *, mode: str = "error"
    ) -> "DataFrame":
        """Write these rows to a named table (a ``WriteRel`` sink, CTAS).

        ``mode`` selects the behavior when the table already exists: ``error``
        (default), ``append``, ``replace`` or ``ignore``. The result is a
        terminal DataFrame; call ``to_plan()`` to materialize.
        """
        try:
            create_mode = _CREATE_MODES[mode]
        except KeyError:
            raise ValueError(
                f"unknown write mode {mode!r}; expected one of {sorted(_CREATE_MODES)}"
            ) from None
        return self._next(
            _plan.write_named_table(name, self._plan, create_mode=create_mode)
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
