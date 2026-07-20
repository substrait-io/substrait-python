"""The Substrait-native DataFrame.

This module is the **native** fluent frame -- the primary, engine-agnostic way
to build a Substrait plan in Python (analogous to how ``daft.DataFrame`` is
Daft's own native frame). It is a thin, chainable wrapper over the
``substrait.builders.plan`` functions: it carries an ``ExtensionRegistry`` so it
does not have to be threaded through every call, and it takes
:class:`~substrait.dataframe.expr.Expr` objects (or bare column names / Python
scalars) rather than raw ``scalar_function`` invocations::

    import substrait.dataframe as sub

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

from itertools import combinations
from typing import Any, Callable, Iterable, Optional, Union

import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stplan
import substrait.type_pb2 as stp

from substrait.builders import plan as _plan
from substrait.builders import type as _type
from substrait.builders.extended_expression import LateralInput, fresh_rel_anchors
from substrait.dataframe.expr import Expr, Measure, col, lit, sort_direction
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema
from substrait.utils import to_id_based_outer_references

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

# Lateral joins evaluate the right input per left row, so only INNER and
# left-oriented join types are valid (RIGHT-oriented and OUTER have no meaning).
_LATERAL_JOIN_TYPES = {
    how: _JOIN_TYPES[how]
    for how in (
        "inner",
        "left",
        "left_semi",
        "left_anti",
        "left_single",
        "left_mark",
    )
}

# Write create-modes: what to do when the target table already exists.
_CREATE_MODES = {
    "error": stalg.WriteRel.CREATE_MODE_ERROR_IF_EXISTS,
    "append": stalg.WriteRel.CREATE_MODE_APPEND_IF_EXISTS,
    "replace": stalg.WriteRel.CREATE_MODE_REPLACE_IF_EXISTS,
    "ignore": stalg.WriteRel.CREATE_MODE_IGNORE_IF_EXISTS,
}

# Write operations for the write sink.
_WRITE_OPS = {
    "ctas": stalg.WriteRel.WRITE_OP_CTAS,
    "insert": stalg.WriteRel.WRITE_OP_INSERT,
    "delete": stalg.WriteRel.WRITE_OP_DELETE,
    "update": stalg.WriteRel.WRITE_OP_UPDATE,
}

# How often execution context variables (current_timestamp, ...) are evaluated.
_VARIABLE_EVAL_MODES = {
    "per_plan": stplan.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_PLAN,
    "per_record": stplan.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_RECORD,
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


def _normalize_grouping_sets(
    keys: "tuple[Union[str, Expr], ...]", grouping_sets: Iterable[Iterable[Any]]
) -> "list[list[int]]":
    """Map each grouping set (of key names or positions) to index lists into ``keys``."""
    name_to_index = {k: i for i, k in enumerate(keys) if isinstance(k, str)}
    result = []
    for gs in grouping_sets:
        refs = []
        for item in gs:
            if isinstance(item, bool):  # bool is an int subclass; reject explicitly
                raise ValueError(f"invalid grouping set item {item!r}")
            elif isinstance(item, int):
                if not 0 <= item < len(keys):
                    raise ValueError(f"grouping set index {item} out of range")
                refs.append(item)
            elif isinstance(item, str) and item in name_to_index:
                refs.append(name_to_index[item])
            else:
                raise ValueError(f"grouping set item {item!r} is not a group_by key")
        result.append(refs)
    return result


def _split_measure(m: Union[Expr, Measure]):
    """Return ``(unbound_measure, unbound_filter_or_None)`` for an agg input."""
    if isinstance(m, Measure):
        return _unbound(m.expr), _unbound(m.predicate)
    return _unbound(m), None


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


class LateralLeft:
    """Handle to a lateral join's left input, passed to the ``right`` builder of
    :meth:`DataFrame.lateral_join`.

    Its columns are correlated references to the current left row (an id-based
    ``OuterReference``), so the right frame can be built as a function of the
    left without counting nesting levels.
    """

    def __init__(self, handle: LateralInput):
        self._handle = handle

    def col(self, name: Union[str, int]) -> Expr:
        """A correlated reference to the left row's column ``name`` (or index)."""
        return Expr(self._handle.column(name))

    def __getitem__(self, name: Union[str, int]) -> Expr:
        return self.col(name)


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
            from substrait.dataframe.functions import functions_for

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
            names = list(infer_plan_schema(bound, registry=registry).names)
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
            names = list(infer_plan_schema(bound, registry=registry).names)
            unknown = drop_set - set(names)
            if unknown:
                raise ValueError(f"drop got unknown columns: {sorted(unknown)}")
            expressions = [col(n).unbound for n in names if n not in drop_set]
            if not expressions:
                raise ValueError("drop would remove every column")
            return _plan.select(bound, expressions=expressions)(registry)

        return self._next(resolve)

    def unpivot(
        self,
        on: Union[str, Iterable[str]],
        index: Union[str, Iterable[str]] = (),
        *,
        variable_name: str = "variable",
        value_name: str = "value",
    ) -> "DataFrame":
        """Unpivot ``on`` columns into ``variable``/``value`` rows (an ExpandRel).

        ``index`` columns are repeated on every output row. The ``on`` columns
        must share a type. Polars-style naming.
        """
        on = [on] if isinstance(on, str) else list(on)
        index = [index] if isinstance(index, str) else list(index)
        if not on:
            raise ValueError("unpivot needs at least one column in `on`")

        fields = [("consistent", col(c).unbound) for c in index]
        fields.append(("switching", [lit(name, _type.string()).unbound for name in on]))
        fields.append(("switching", [col(name).unbound for name in on]))
        kept = [*index, variable_name, value_name]
        # ExpandRel appends an i32 duplicate-index column; drop it for clean output.
        names = [*kept, "__expand_index__"]
        expanded = self._next(_plan.expand(self._plan, fields, names))
        return expanded.select(*kept)

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
            (_unbound(c), sort_direction(desc[i], nulls[i]))
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

    def top_n(
        self,
        n: int,
        by: Union[str, Expr, Iterable[Union[str, Expr]]],
        *,
        descending: Union[bool, "list[bool]"] = False,
        nulls_last: Union[bool, "list[bool]"] = True,
        offset: int = 0,
        with_ties: bool = False,
    ) -> "DataFrame":
        """The top ``n`` rows ordered by ``by`` (a fused sort + fetch, TopNRel).

        ``descending``/``nulls_last`` follow :meth:`sort`; ``with_ties`` keeps
        rows tied with the n-th.
        """
        keys = [by] if isinstance(by, (str, Expr)) else list(by)
        count = len(keys)
        desc = _per_column(descending, count, "descending")
        nulls = _per_column(nulls_last, count, "nulls_last")
        sorts = [
            (_unbound(c), sort_direction(desc[i], nulls[i])) for i, c in enumerate(keys)
        ]
        return self._next(
            _plan.top_n(
                self._plan,
                sorts,
                count=lit(n, _type.i64()).unbound,
                offset=lit(offset, _type.i64()).unbound if offset else None,
                with_ties=with_ties,
            )
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

    def lateral_join(
        self,
        right: "Callable[[LateralLeft], DataFrame]",
        how: str = "inner",
        *,
        on: Union[Expr, Any, None] = None,
        post_filter: Union[Expr, Any, None] = None,
    ) -> "DataFrame":
        """Lateral join: evaluate the right frame once per row of this frame.

        ``right`` is a function of a :class:`LateralLeft` handle to this frame;
        use ``left.col(...)`` inside it to correlate on the current left row::

            left.lateral_join(lambda lat: inner.filter(sub.col("k") == lat.col("k")))

        Capturing the handle avoids counting nesting levels -- an inner lateral
        join can reference an outer one via its own handle.

        ``on`` is an optional match condition over the combined left+right
        schema. Only ``inner`` and left-oriented join types are valid for
        lateral joins: ``inner``, ``left``, ``left_semi``, ``left_anti``,
        ``left_single``, ``left_mark``. ``post_filter`` is an optional predicate
        applied to the join output.
        """
        try:
            join_type = _LATERAL_JOIN_TYPES[how]
        except KeyError:
            raise ValueError(
                f"unknown lateral join type {how!r}; expected one of "
                f"{sorted(_LATERAL_JOIN_TYPES)}"
            ) from None

        def build_right(handle: LateralInput):
            return right(LateralLeft(handle))._plan

        return self._next(
            _plan.lateral_join(
                self._plan,
                build_right,
                type=join_type,
                expression=_unbound(on) if on is not None else None,
                post_join_filter=(
                    _unbound(post_filter) if post_filter is not None else None
                ),
            )
        )

    def nested_loop_join(
        self, other: "DataFrame", on: Union[Expr, Any], how: str = "inner"
    ) -> "DataFrame":
        """Physical nested-loop join: evaluate ``on`` over the Cartesian product.

        ``how`` accepts the same values as :meth:`join`.
        """
        if how not in _JOIN_TYPES:
            raise ValueError(
                f"unknown join type {how!r}; expected one of {sorted(_JOIN_TYPES)}"
            )
        join_type = getattr(stalg.NestedLoopJoinRel, "JOIN_TYPE_" + how.upper())
        return self._next(
            _plan.nested_loop_join(
                self._plan, other._plan, expression=_unbound(on), type=join_type
            )
        )

    def _equi_join(
        self,
        builder,
        rel_cls,
        other,
        left_on,
        right_on,
        how,
        post_filter,
        residual,
    ):
        if how not in _JOIN_TYPES:
            raise ValueError(
                f"unknown join type {how!r}; expected one of {sorted(_JOIN_TYPES)}"
            )
        join_type = getattr(rel_cls, "JOIN_TYPE_" + how.upper())
        left_keys = [left_on] if isinstance(left_on, (str, int)) else list(left_on)
        if right_on is None:
            right_keys = left_keys
        else:
            right_keys = (
                [right_on] if isinstance(right_on, (str, int)) else list(right_on)
            )
        return self._next(
            builder(
                self._plan,
                other._plan,
                left_keys,
                right_keys,
                join_type,
                post_join_filter=(
                    _unbound(post_filter) if post_filter is not None else None
                ),
                residual_expression=(
                    _unbound(residual) if residual is not None else None
                ),
            )
        )

    def hash_join(
        self,
        other: "DataFrame",
        left_on: Union[str, int, Iterable[Union[str, int]]],
        right_on: Union[str, int, Iterable[Union[str, int]], None] = None,
        how: str = "inner",
        *,
        post_filter: Union[Expr, Any, None] = None,
        residual: Union[Expr, Any, None] = None,
    ) -> "DataFrame":
        """Physical hash equi-join on key columns.

        ``left_on``/``right_on`` are column names/indices; ``right_on`` defaults
        to ``left_on``. ``how`` accepts the same values as :meth:`join`.
        ``post_filter`` is an optional predicate applied to the join output;
        ``residual`` is an optional non-equi condition evaluated alongside the
        key equalities. Both bind against the concatenated left+right schema.
        """
        return self._equi_join(
            _plan.hash_join,
            stalg.HashJoinRel,
            other,
            left_on,
            right_on,
            how,
            post_filter,
            residual,
        )

    def merge_join(
        self,
        other: "DataFrame",
        left_on: Union[str, int, Iterable[Union[str, int]]],
        right_on: Union[str, int, Iterable[Union[str, int]], None] = None,
        how: str = "inner",
        *,
        post_filter: Union[Expr, Any, None] = None,
        residual: Union[Expr, Any, None] = None,
    ) -> "DataFrame":
        """Physical sort-merge equi-join on key columns (inputs assumed sorted).

        ``post_filter`` and ``residual`` behave as in :meth:`hash_join`.
        """
        return self._equi_join(
            _plan.merge_join,
            stalg.MergeJoinRel,
            other,
            left_on,
            right_on,
            how,
            post_filter,
            residual,
        )

    def repartition(self, n: int = 0) -> "DataFrame":
        """Redistribute rows round-robin into ``n`` partitions (an ExchangeRel)."""
        return self._next(_plan.exchange(self._plan, partition_count=n))

    def broadcast(self) -> "DataFrame":
        """Broadcast every row to all partitions (an ExchangeRel)."""
        return self._next(_plan.exchange(self._plan, broadcast=True))

    def extension(self, detail: Any) -> "DataFrame":
        """Apply a custom single-input relation (ExtensionSingleRel).

        ``detail`` is an
        :class:`~substrait.dataframe.extension_relations.ExtensionSingleDetail` (its
        ``derive_schema`` defines the output) or a raw ``google.protobuf.Any``
        (the input schema is then assumed to pass through). Register the detail
        class via ``ExtensionRegistry.register_extension_relation`` for schema
        inference to follow it.
        """
        return self._next(_plan.extension_single(self._plan, detail))

    def extension_multi(
        self, others: Iterable["DataFrame"], detail: Any
    ) -> "DataFrame":
        """A custom multi-input relation (ExtensionMultiRel) over this frame and
        ``others``; ``detail`` is an
        :class:`~substrait.dataframe.extension_relations.ExtensionMultiDetail`."""
        inputs = [self._plan, *(o._plan for o in others)]
        return self._next(_plan.extension_multi(inputs, detail))

    def hint(
        self,
        *,
        row_count: Optional[float] = None,
        record_size: Optional[float] = None,
        alias: Optional[str] = None,
        output_names: Optional[Iterable[str]] = None,
    ) -> "DataFrame":
        """Attach non-semantic hints to the current relation (``RelCommon.Hint``).

        ``row_count`` / ``record_size`` are optimizer statistics; ``alias`` names
        the relation; ``output_names`` annotates its output column names. All are
        optional and purely advisory (they don't change results).
        """
        inner = self._plan

        def resolve(registry: ExtensionRegistry):
            bound = inner(registry)
            rel = bound.relations[-1].root.input
            rel_inner = getattr(rel, rel.WhichOneof("rel_type"))
            # A few relations (a ReferenceRel from .cache(), an UpdateRel) carry no
            # RelCommon and so cannot hold a hint -- fail with a clear message
            # rather than an opaque AttributeError on `.common`.
            if "common" not in rel_inner.DESCRIPTOR.fields_by_name:
                raise TypeError(
                    f"cannot attach a hint to a {rel_inner.DESCRIPTOR.name} "
                    "(e.g. a cached/reference relation); apply .hint(...) before "
                    ".cache()"
                )
            common = rel_inner.common
            if row_count is not None:
                common.hint.stats.row_count = row_count
            if record_size is not None:
                common.hint.stats.record_size = record_size
            if alias is not None:
                common.hint.alias = alias
            if output_names is not None:
                del common.hint.output_names[:]
                common.hint.output_names.extend(output_names)
            return bound

        return self._next(resolve)

    def cache(self) -> "DataFrame":
        """Mark this DataFrame as a reusable common subplan (a CTE).

        The returned frame is emitted as a shared subtree (a leading ``rel`` entry
        in the plan) and referenced via a ``ReferenceRel`` wherever it is used.
        When the same cached frame feeds two branches that later meet at a
        multi-input relation (e.g. ``base.filter(...).union(base.filter(...))``),
        the shared subtree is emitted **once** and referenced from both branches
        instead of being inlined twice.

        Because the subtree carries no ``RelCommon``, apply :meth:`hint` (and any
        node-level annotation) *before* ``cache()``, not after.
        """
        return self._next(_plan.reference(self._plan))

    def with_execution_behavior(self, variable_eval_mode: str) -> "DataFrame":
        """Set how often execution context variables are evaluated (plan-level).

        ``variable_eval_mode`` is ``"per_plan"`` (evaluate once for the whole
        plan) or ``"per_record"`` (evaluate once per record), controlling
        variables such as :func:`substrait.dataframe.current_timestamp`. The
        setting is carried across subsequent operations, so it may be applied at
        any point in the chain.
        """
        try:
            eval_mode = _VARIABLE_EVAL_MODES[variable_eval_mode]
        except KeyError:
            raise ValueError(
                f"unknown execution behavior mode {variable_eval_mode!r}; "
                f"expected one of {sorted(_VARIABLE_EVAL_MODES)}"
            ) from None
        return self._next(_plan.with_execution_behavior(self._plan, eval_mode))

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

    def group_by(
        self,
        *keys: Union[str, Expr],
        grouping_sets: Optional[Iterable[Iterable[Any]]] = None,
    ) -> "GroupBy":
        """Begin an aggregation; follow with ``.agg(...)``.

        ``grouping_sets`` optionally supplies explicit GROUPING SETS as lists of
        key names or positions into ``keys`` (e.g. ``[["a", "b"], ["a"], []]``);
        see also ``rollup`` / ``cube``.
        """
        sets = (
            _normalize_grouping_sets(keys, grouping_sets)
            if grouping_sets is not None
            else None
        )
        return GroupBy(self, keys, sets)

    def rollup(self, *keys: Union[str, Expr]) -> "GroupBy":
        """Aggregate over the ROLLUP of ``keys``: the grouping sets
        ``(k0..kn), (k0..kn-1), ..., (k0), ()``."""
        sets = [list(range(i)) for i in range(len(keys), -1, -1)]
        return GroupBy(self, keys, sets)

    def cube(self, *keys: Union[str, Expr]) -> "GroupBy":
        """Aggregate over the CUBE of ``keys``: every subset of the keys."""
        n = len(keys)
        sets = [
            list(combo) for r in range(n, -1, -1) for combo in combinations(range(n), r)
        ]
        return GroupBy(self, keys, sets)

    def aggregate(
        self,
        group_by: Union[str, Expr, Iterable[Union[str, Expr]]] = (),
        *measures: Union[Expr, Measure],
    ) -> "DataFrame":
        """One-shot aggregation. See also the fluent ``group_by().agg()``."""
        if isinstance(group_by, (str, Expr)):
            group_by = [group_by]
        return GroupBy(self, tuple(group_by), None).agg(*measures)

    def write_named_table(
        self, name: Union[str, Iterable[str]], *, mode: str = "error", op: str = "ctas"
    ) -> "DataFrame":
        """Write these rows to a named table (a ``WriteRel`` sink).

        ``op`` is the write operation: ``ctas`` (create-table-as-select,
        default) or ``insert``. ``mode`` selects the behavior when the table
        already exists: ``error`` (default), ``append``, ``replace`` or
        ``ignore``. The result is a terminal DataFrame; call ``to_plan()``.
        """
        try:
            create_mode = _CREATE_MODES[mode]
        except KeyError:
            raise ValueError(
                f"unknown write mode {mode!r}; expected one of {sorted(_CREATE_MODES)}"
            ) from None
        try:
            write_op = _WRITE_OPS[op]
        except KeyError:
            raise ValueError(
                f"unknown write op {op!r}; expected one of {sorted(_WRITE_OPS)}"
            ) from None
        return self._next(
            _plan.write_named_table(
                name, self._plan, create_mode=create_mode, op=write_op
            )
        )

    def _finalize(self, registry: Optional[ExtensionRegistry]) -> stplan.Plan:
        """Build the plan and normalize it for output. The DataFrame layer emits
        correlated (outer) references in the id-based form (``rel_reference``): a
        lateral join's builder assigns them directly, and any offset-based
        ``steps_out`` a correlated subquery produced is rewritten here. Building
        under ``fresh_rel_anchors`` numbers lateral-join anchors from 1 per
        materialization, so building the same frame twice yields identical plans."""
        with fresh_rel_anchors():
            plan = self._plan(registry)
        return to_id_based_outer_references(plan)

    def to_plan(self) -> stplan.Plan:
        """Materialize to a ``substrait.proto.Plan``."""
        return self._finalize(self._registry)

    # Kept for parity with the substrait.narwhals (Narwhals) wrapper's API.
    def to_substrait(self, registry: Optional[ExtensionRegistry] = None) -> stplan.Plan:
        return self._finalize(registry or self._registry)


class GroupBy:
    """Intermediate returned by ``DataFrame.group_by``; call ``.agg(...)``."""

    def __init__(
        self,
        df: DataFrame,
        keys: Iterable[Union[str, Expr]],
        grouping_sets: Optional["list[list[int]]"] = None,
    ):
        self._df = df
        self._keys = list(keys)
        self._grouping_sets = grouping_sets

    def agg(self, *measures: Union[Expr, Measure]) -> DataFrame:
        unbound, filters = (
            zip(*(_split_measure(m) for m in measures)) if measures else ((), ())
        )
        return self._df._next(
            _plan.aggregate(
                self._df._plan,
                grouping_expressions=[_unbound(k) for k in self._keys],
                measures=list(unbound),
                grouping_sets=self._grouping_sets,
                filters=list(filters) if any(f is not None for f in filters) else None,
            )
        )


def extension_leaf(
    detail: Any, registry: Optional[ExtensionRegistry] = None
) -> DataFrame:
    """Start a DataFrame from a custom leaf relation (ExtensionLeafRel).

    ``detail`` is an
    :class:`~substrait.dataframe.extension_relations.ExtensionLeafDetail`; its
    ``derive_schema`` defines the source's output columns.
    """
    return DataFrame(_plan.extension_leaf(detail), registry)


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


def from_records(
    data: Iterable[Any],
    schema: Any,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """Start a DataFrame from inline rows (a ``VirtualTable`` / VALUES clause).

    ``data`` is an iterable of rows, each either a ``{column: value}`` dict or a
    positional sequence aligned to ``schema``. Values are typed per the schema
    column (``None`` becomes a typed null).
    """
    ns = _to_named_struct(schema)
    types = list(ns.struct.types)
    rows = []
    for record in data:
        if isinstance(record, dict):
            values = [record.get(n) for n in ns.names]
        else:
            values = list(record)
            if len(values) != len(ns.names):
                raise ValueError(
                    f"row has {len(values)} values but schema has {len(ns.names)} columns"
                )
        rows.append([lit(v, types[i]).unbound for i, v in enumerate(values)])
    return DataFrame(_plan.virtual_table(rows, ns), registry)


def _read_local_files(
    paths: Union[str, Iterable[str]],
    schema: Any,
    registry: Optional[ExtensionRegistry],
    **file_format: Any,
) -> DataFrame:
    ns = _to_named_struct(schema)
    path_list = [paths] if isinstance(paths, str) else list(paths)
    file_or_files = stalg.ReadRel.LocalFiles.FileOrFiles
    items = [file_or_files(uri_file=p, **file_format) for p in path_list]
    return DataFrame(_plan.local_files(ns, items), registry)


def read_parquet(
    paths: Union[str, Iterable[str]],
    schema: Any,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """Read one or more Parquet files into a DataFrame."""
    opts = stalg.ReadRel.LocalFiles.FileOrFiles.ParquetReadOptions()
    return _read_local_files(paths, schema, registry, parquet=opts)


def read_orc(
    paths: Union[str, Iterable[str]],
    schema: Any,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """Read one or more ORC files into a DataFrame."""
    opts = stalg.ReadRel.LocalFiles.FileOrFiles.OrcReadOptions()
    return _read_local_files(paths, schema, registry, orc=opts)


def read_arrow(
    paths: Union[str, Iterable[str]],
    schema: Any,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """Read one or more Arrow IPC files into a DataFrame."""
    opts = stalg.ReadRel.LocalFiles.FileOrFiles.ArrowReadOptions()
    return _read_local_files(paths, schema, registry, arrow=opts)


def read_csv(
    paths: Union[str, Iterable[str]],
    schema: Any,
    *,
    delimiter: str = ",",
    header_lines_to_skip: int = 1,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """Read one or more delimiter-separated text files (CSV/TSV) into a DataFrame."""
    opts = stalg.ReadRel.LocalFiles.FileOrFiles.DelimiterSeparatedTextReadOptions(
        field_delimiter=delimiter, header_lines_to_skip=header_lines_to_skip
    )
    return _read_local_files(paths, schema, registry, text=opts)


def read_extension_table(
    schema: Any,
    detail: Any,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """Start a DataFrame from a custom source; ``detail`` is a ``google.protobuf.Any``."""
    return DataFrame(_plan.extension_table(_to_named_struct(schema), detail), registry)


def create_table(
    name: Union[str, Iterable[str]],
    schema: Any,
    *,
    replace: bool = False,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """A ``CREATE TABLE`` DDL statement (``CREATE OR REPLACE`` when ``replace``)."""
    op = (
        stalg.DdlRel.DDL_OP_CREATE_OR_REPLACE if replace else stalg.DdlRel.DDL_OP_CREATE
    )
    return DataFrame(
        _plan.ddl(
            name,
            stalg.DdlRel.DDL_OBJECT_TABLE,
            op,
            table_schema=_to_named_struct(schema),
        ),
        registry,
    )


def create_view(
    name: Union[str, Iterable[str]],
    query: DataFrame,
    *,
    replace: bool = False,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """A ``CREATE VIEW`` DDL statement backed by ``query`` (a DataFrame)."""
    op = (
        stalg.DdlRel.DDL_OP_CREATE_OR_REPLACE if replace else stalg.DdlRel.DDL_OP_CREATE
    )
    return DataFrame(
        _plan.ddl(name, stalg.DdlRel.DDL_OBJECT_VIEW, op, view_definition=query._plan),
        registry or query._registry,
    )


def drop_table(
    name: Union[str, Iterable[str]],
    *,
    if_exists: bool = False,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """A ``DROP TABLE`` DDL statement (``DROP TABLE IF EXISTS`` when ``if_exists``)."""
    op = stalg.DdlRel.DDL_OP_DROP_IF_EXIST if if_exists else stalg.DdlRel.DDL_OP_DROP
    return DataFrame(_plan.ddl(name, stalg.DdlRel.DDL_OBJECT_TABLE, op), registry)


def drop_view(
    name: Union[str, Iterable[str]],
    *,
    if_exists: bool = False,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """A ``DROP VIEW`` DDL statement (``DROP VIEW IF EXISTS`` when ``if_exists``)."""
    op = stalg.DdlRel.DDL_OP_DROP_IF_EXIST if if_exists else stalg.DdlRel.DDL_OP_DROP
    return DataFrame(_plan.ddl(name, stalg.DdlRel.DDL_OBJECT_VIEW, op), registry)


def update_table(
    name: Union[str, Iterable[str]],
    schema: Any,
    assignments: dict,
    *,
    where: Union[Expr, Any, None] = None,
    registry: Optional[ExtensionRegistry] = None,
) -> DataFrame:
    """An ``UPDATE`` statement: ``assignments`` maps a column (name or index) to a
    new-value expression, applied where ``where`` holds (all rows if omitted)."""
    ns = _to_named_struct(schema)
    names_list = list(ns.names)
    transformations = []
    for target, expr in assignments.items():
        index = target if isinstance(target, int) else names_list.index(target)
        transformations.append((index, _unbound(expr)))
    condition = _unbound(where) if where is not None else None
    return DataFrame(_plan.update(name, ns, transformations, condition), registry)
