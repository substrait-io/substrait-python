"""
Plan builders take either Plan or UnboundPlan objects as input rather than plain Rels.
This is to make sure that additional information like extension types of functions are not lost.
All builders return UnboundPlan objects that can be materialized to a Plan using an ExtensionRegistry.
See `examples/builder_example.py` for usage.
"""

import re
from typing import Callable, Iterable, Optional, Union

import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt
from substrait.extensions.extensions_pb2 import AdvancedExtension

from substrait.builders.extended_expression import (
    ExtendedExpressionOrUnbound,
    LateralInput,
    next_rel_anchor,
    resolve_expression,
)
from substrait.extension_registry import (
    ExtensionRegistry,
    build_scoped,
    current_collector,
)
from substrait.type_inference import (
    _join_output_struct,
    _join_struct_from_schemas,
    _outer_anchor_binding,
    infer_plan_schema,
    join_output_names,
)
from substrait.utils import (
    plan_subtrees,
    rebase_reference_ordinals,
    remap_function_references,
)
from substrait.version import substrait_version

UnboundPlan = Callable[[ExtensionRegistry], stp.Plan]

PlanOrUnbound = Union[stp.Plan, UnboundPlan]


def _create_default_version():
    p = re.compile(r"(\d+)\.(\d+)\.(\d+)")
    m = p.match(substrait_version)
    global default_version
    default_version = stp.Version(
        major_number=int(m.group(1)),
        minor_number=int(m.group(2)),
        patch_number=int(m.group(3)),
    )


_create_default_version()


def _bind(plan: PlanOrUnbound, registry: ExtensionRegistry) -> stp.Plan:
    """Resolve ``plan`` and fold its extensions into the build in progress.

    A plan built elsewhere -- or by an earlier, separate build -- numbered its
    function references independently, so the collector re-derives them from the
    durable ``(urn, name)`` identities and the plan's relations are rewritten to
    match. Returns the plan untouched when the numbering already agrees, which is
    always the case for one resolved by the current build (it allocated through the
    same collector, and carries no declarations of its own until the outermost
    resolver writes them).

    Every builder binds its inputs through here, so this is the single point at
    which a foreign plan's anchor space is reconciled with ours.
    """
    bound = plan if isinstance(plan, stp.Plan) else plan(registry)
    collector = current_collector()
    if collector is None:
        return bound
    return remap_function_references(bound, collector.adopt(bound))


def _merge_plan_metadata(*objs):
    """Collect the plan-level metadata a builder carries over from its inputs.

    ``objs`` is a mix of input Plans and bound ExtendedExpressions. The plan-level
    execution behavior is carried over from the first input Plan that declares one
    (expressions have no such field). Because every relational builder routes
    its inputs through here, an execution behavior set anywhere upstream is
    preserved on the freshly-constructed output Plan -- so it is order
    independent across a pipeline rather than only surviving as the last step.

    Extension URNs and declarations are *not* merged here: they belong to the
    build's ``ExtensionCollector``, which writes them onto the outermost plan once
    (see ``build_scoped``), rather than being re-merged at every level.
    """
    metadata = {}
    for b in objs:
        if isinstance(b, stp.Plan) and b.HasField("execution_behavior"):
            metadata["execution_behavior"] = b.execution_behavior
            break
    return metadata


def _is_identity(remap: dict) -> bool:
    return all(old == new for old, new in remap.items())


def _merge_input_subtrees(bound_inputs):
    """Combine the leading shared subtrees carried in-band by resolved input plans.

    Returns ``(subtree_planrels, rebased_root_inputs)``: the deduplicated combined
    subtrees as leading ``PlanRel(rel=...)`` entries, and, per input, its root's
    input Rel with ReferenceRel ordinals rebased into the combined list.

    Structurally-identical subtrees (byte-equal serialized ``Rel``) collapse to a
    single ordinal, so a cached frame reused across branches that later meet at a
    multi-input relation is emitted once and referenced many times. Inputs that
    carry no subtrees pass their root input through untouched, keeping output for
    the (overwhelmingly common) no-subtree case byte-identical.
    """
    combined: "list[stalg.Rel]" = []
    key_to_ordinal: dict = {}  # serialized subtree bytes -> ordinal in `combined`
    rebased_root_inputs = []
    for plan in bound_inputs:
        remap: dict = {}
        for old_ordinal, subtree in enumerate(plan_subtrees(plan)):
            # Rebase the subtree's own references (to earlier subtrees in this same
            # input) before deduping, so structurally-equal subtrees compare equal.
            rebased = (
                subtree
                if _is_identity(remap)
                else rebase_reference_ordinals(subtree, remap)
            )
            key = rebased.SerializeToString(deterministic=True)
            new_ordinal = key_to_ordinal.get(key)
            if new_ordinal is None:
                new_ordinal = len(combined)
                key_to_ordinal[key] = new_ordinal
                combined.append(rebased)
            remap[old_ordinal] = new_ordinal
        root_input = plan.relations[-1].root.input
        rebased_root_inputs.append(
            root_input
            if _is_identity(remap)
            else rebase_reference_ordinals(root_input, remap)
        )
    subtree_planrels = [stp.PlanRel(rel=r) for r in combined]
    return subtree_planrels, rebased_root_inputs


def _plan_from(
    bound_inputs, make_rel, names, metadata_sources, *, include_version=True
):
    """Assemble a relational builder's output Plan.

    Merges the shared subtrees carried by ``bound_inputs`` (deduping and rebasing
    ordinals), builds the output ``Rel`` by calling ``make_rel`` with the list of
    rebased input rels (one per bound input, in order), and prepends the combined
    subtrees as leading ``rel`` entries ahead of the query root. Plan-level metadata
    is carried over from ``metadata_sources`` (input plans and bound expressions);
    extension declarations are not, as the build's ``ExtensionCollector`` owns those.
    This is the single place the CTE subtree propagation and Plan assembly live, so
    every relational builder is one call.
    """
    subtree_planrels, input_rels = _merge_input_subtrees(bound_inputs)
    root = stp.PlanRel(
        root=stalg.RelRoot(input=make_rel(input_rels), names=list(names))
    )
    kwargs = {
        "relations": [*subtree_planrels, root],
        **_merge_plan_metadata(*metadata_sources),
    }
    if include_version:
        kwargs["version"] = default_version
    return stp.Plan(**kwargs)


def with_execution_behavior(
    plan: PlanOrUnbound,
    variable_eval_mode: "stp.ExecutionBehavior.VariableEvaluationMode.ValueType",
) -> UnboundPlan:
    """Return a copy of ``plan`` with its plan-level execution behavior set.

    ``variable_eval_mode`` controls how often execution context variables (such
    as those from ``extended_expression.execution_context_variable``) are
    evaluated: once per plan (``VARIABLE_EVALUATION_MODE_PER_PLAN``) or once per
    record (``VARIABLE_EVALUATION_MODE_PER_RECORD``). The setting is carried over
    by subsequent builders (see ``_merge_plan_metadata``), so it may be applied
    at any point in a pipeline rather than only as the final step.
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = _bind(plan, registry)

        result = stp.Plan()
        result.CopyFrom(bound_plan)
        # This is the one builder that copies its input wholesale rather than
        # assembling a fresh Plan, so it is the one that has to drop the copied
        # declarations: `_bind` has already renumbered the relations, and the
        # collector -- not this plan -- owns the anchor space until the outermost
        # resolver writes it (see `_bind`). Left in place, an enclosing builder
        # would adopt the stale numbering a second time and re-apply a remap the
        # relations already carry, silently pointing them at other declarations.
        # Dropping `extensions` wholesale is only sound because everything it can
        # hold is recoverable from the collector, which today means function
        # declarations alone: `ExtensionCollector.adopt` raises NotImplementedError
        # on any other kind, so whoever teaches it to collect type / type-variation
        # declarations must extend `write_into` in the same change or they will be
        # silently dropped here.
        result.ClearField("extension_urns")
        result.ClearField("extensions")
        result.execution_behavior.variable_eval_mode = variable_eval_mode
        return result

    return build_scoped(resolve)


def read_named_table(
    names: Union[str, Iterable[str]],
    named_struct: stt.NamedStruct,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    if named_struct.struct.nullability is stt.Type.NULLABILITY_NULLABLE:
        raise Exception("NamedStruct must not contain a nullable struct")
    elif named_struct.struct.nullability is stt.Type.NULLABILITY_UNSPECIFIED:
        named_struct.struct.nullability = stt.Type.NULLABILITY_REQUIRED

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        _names = [names] if isinstance(names, str) else names

        rel = stalg.Rel(
            read=stalg.ReadRel(
                common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                base_schema=named_struct,
                named_table=stalg.ReadRel.NamedTable(names=_names),
                advanced_extension=extension,
            )
        )

        return stp.Plan(
            version=default_version,
            relations=[
                stp.PlanRel(root=stalg.RelRoot(input=rel, names=named_struct.names))
            ],
        )

    return build_scoped(resolve)


def _require_schema(named_struct: stt.NamedStruct) -> stt.NamedStruct:
    """A read's base schema must be a required (non-nullable) struct."""
    if named_struct.struct.nullability is stt.Type.NULLABILITY_NULLABLE:
        raise Exception("NamedStruct must not contain a nullable struct")
    if named_struct.struct.nullability is stt.Type.NULLABILITY_UNSPECIFIED:
        named_struct.struct.nullability = stt.Type.NULLABILITY_REQUIRED
    return named_struct


def _read_plan(named_struct: stt.NamedStruct, read_rel: stalg.ReadRel) -> stp.Plan:
    return stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(read=read_rel), names=named_struct.names
                )
            )
        ],
    )


def virtual_table(
    rows: Iterable[Iterable[ExtendedExpressionOrUnbound]],
    named_struct: stt.NamedStruct,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """A ReadRel over inline rows (the VALUES clause).

    ``rows`` is an iterable of rows, each an iterable of expressions (typically
    literals) aligned to ``named_struct``.
    """
    _require_schema(named_struct)

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        structs = [
            stalg.Expression.Nested.Struct(
                fields=[
                    resolve_expression(e, named_struct, registry)
                    .referred_expr[0]
                    .expression
                    for e in row
                ]
            )
            for row in rows
        ]
        read_rel = stalg.ReadRel(
            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
            base_schema=named_struct,
            virtual_table=stalg.ReadRel.VirtualTable(expressions=structs),
            advanced_extension=extension,
        )
        return _read_plan(named_struct, read_rel)

    return build_scoped(resolve)


def local_files(
    named_struct: stt.NamedStruct,
    items: Iterable[stalg.ReadRel.LocalFiles.FileOrFiles],
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """A ReadRel over local/remote files; ``items`` are pre-built FileOrFiles."""
    _require_schema(named_struct)

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        read_rel = stalg.ReadRel(
            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
            base_schema=named_struct,
            local_files=stalg.ReadRel.LocalFiles(items=list(items)),
            advanced_extension=extension,
        )
        return _read_plan(named_struct, read_rel)

    return build_scoped(resolve)


def extension_table(
    named_struct: stt.NamedStruct,
    detail,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """A ReadRel over a custom source; ``detail`` is a ``google.protobuf.Any``."""
    _require_schema(named_struct)

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        read_rel = stalg.ReadRel(
            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
            base_schema=named_struct,
            extension_table=stalg.ReadRel.ExtensionTable(detail=detail),
            advanced_extension=extension,
        )
        return _read_plan(named_struct, read_rel)

    return build_scoped(resolve)


def project(
    plan: PlanOrUnbound,
    expressions: Iterable[ExtendedExpressionOrUnbound],
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """
    Builds an UnboundPlan with ProjectRel as the root node. Expressions are appended to the parent relation fields to produce an output.
    Semantically similar to a withColumn transformation.

    :param plan: Parent plan
    :type plan: PlanOrUnbound
    :param expressions: Expressions to project
    :type expressions: Iterable[ExtendedExpressionOrUnbound]
    :param extension: Optional user-defined extension
    :type extension: Optional[AdvancedExtension]
    :return: UnboundPlan with ProjectRel as the root node
    :rtype: UnboundPlan
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        _plan = _bind(plan, registry)
        ns = infer_plan_schema(_plan, registry=registry)
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            resolve_expression(e, ns, registry) for e in expressions
        ]

        names = list(_plan.relations[-1].root.names) + [
            e.output_names[0] for ee in bound_expressions for e in ee.referred_expr
        ]

        return _plan_from(
            [_plan],
            lambda inp: stalg.Rel(
                project=stalg.ProjectRel(
                    input=inp[0],
                    expressions=[
                        e.expression
                        for ee in bound_expressions
                        for e in ee.referred_expr
                    ],
                    advanced_extension=extension,
                )
            ),
            names,
            (_plan, *bound_expressions),
        )

    return build_scoped(resolve)


def select(
    plan: PlanOrUnbound,
    expressions: Iterable[ExtendedExpressionOrUnbound],
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """
    Builds an UnboundPlan with ProjectRel as the root node. Expressions make up the fields of an output relation.
    Semantically similar to a select transformation.

    :param plan: Parent plan
    :type plan: PlanOrUnbound
    :param expressions: Expressions to project
    :type expressions: Iterable[ExtendedExpressionOrUnbound]
    :param extension: Optional user-defined extension
    :type extension: Optional[AdvancedExtension]
    :return: UnboundPlan with ProjectRel as the root node
    :rtype: UnboundPlan
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        _plan = _bind(plan, registry)
        ns = infer_plan_schema(_plan, registry=registry)
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            resolve_expression(e, ns, registry) for e in expressions
        ]

        start_index = len(_plan.relations[-1].root.names)

        names = [
            e.output_names[0] for ee in bound_expressions for e in ee.referred_expr
        ]

        return _plan_from(
            [_plan],
            lambda inp: stalg.Rel(
                project=stalg.ProjectRel(
                    common=stalg.RelCommon(
                        emit=stalg.RelCommon.Emit(
                            output_mapping=[i + start_index for i in range(len(names))]
                        )
                    ),
                    input=inp[0],
                    expressions=[
                        e.expression
                        for ee in bound_expressions
                        for e in ee.referred_expr
                    ],
                    advanced_extension=extension,
                )
            ),
            names,
            (_plan, *bound_expressions),
        )

    return build_scoped(resolve)


def filter(
    plan: PlanOrUnbound,
    expression: ExtendedExpressionOrUnbound,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = _bind(plan, registry)
        ns = infer_plan_schema(bound_plan, registry=registry)
        bound_expression: stee.ExtendedExpression = resolve_expression(
            expression, ns, registry
        )

        return _plan_from(
            [bound_plan],
            lambda inp: stalg.Rel(
                filter=stalg.FilterRel(
                    input=inp[0],
                    condition=bound_expression.referred_expr[0].expression,
                    advanced_extension=extension,
                )
            ),
            ns.names,
            (bound_plan, bound_expression),
        )

    return build_scoped(resolve)


def sort(
    plan: PlanOrUnbound,
    expressions: Iterable[
        Union[
            ExtendedExpressionOrUnbound,
            tuple[ExtendedExpressionOrUnbound, stalg.SortField.SortDirection.ValueType],
        ]
    ],
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = _bind(plan, registry)
        ns = infer_plan_schema(bound_plan, registry=registry)

        bound_expressions = [
            (e, stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST)
            if not isinstance(e, tuple)
            else e
            for e in expressions
        ]
        bound_expressions = [
            (resolve_expression(e[0], ns, registry), e[1]) for e in bound_expressions
        ]

        return _plan_from(
            [bound_plan],
            lambda inp: stalg.Rel(
                sort=stalg.SortRel(
                    input=inp[0],
                    sorts=[
                        stalg.SortField(
                            expr=e[0].referred_expr[0].expression,
                            direction=e[1],
                        )
                        for e in bound_expressions
                    ],
                    advanced_extension=extension,
                ),
            ),
            ns.names,
            (bound_plan, *[e[0] for e in bound_expressions]),
        )

    return build_scoped(resolve)


def set(inputs: Iterable[PlanOrUnbound], op: stalg.SetRel.SetOp) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_inputs = [_bind(i, registry) for i in inputs]
        return _plan_from(
            bound_inputs,
            lambda inp: stalg.Rel(set=stalg.SetRel(inputs=inp, op=op)),
            bound_inputs[0].relations[-1].root.names,
            tuple(bound_inputs),
        )

    return build_scoped(resolve)


def reference(plan: PlanOrUnbound) -> UnboundPlan:
    """Promote a plan to a shared subtree (a CTE) and reference it.

    Returns a plan whose query root is a ``ReferenceRel`` pointing at ``plan``'s
    root, which is carried along as a leading shared subtree (a ``PlanRel(rel=...)``
    entry). Any subtrees ``plan`` already carries are preserved ahead of it, so
    their ordinals stay valid; the promoted root takes the next ordinal.

    Every downstream use of the returned plan carries the subtree upward; when two
    branches that share the subtree later meet at a multi-input builder, the copies
    collapse to one (see :func:`_merge_input_subtrees`). This is the building block
    for :meth:`substrait.dataframe.DataFrame.cache`.
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound = _bind(plan, registry)
        nested = [stp.PlanRel(rel=s) for s in plan_subtrees(bound)]
        ordinal = len(nested)  # the promoted root sits after the plan's own subtrees
        promoted = stp.PlanRel(rel=bound.relations[-1].root.input)
        names = list(bound.relations[-1].root.names)
        ref = stalg.Rel(reference=stalg.ReferenceRel(subtree_ordinal=ordinal))
        return stp.Plan(
            version=default_version,
            relations=[
                *nested,
                promoted,
                stp.PlanRel(root=stalg.RelRoot(input=ref, names=names)),
            ],
            **_merge_plan_metadata(bound),
        )

    return build_scoped(resolve)


def fetch(
    plan: PlanOrUnbound,
    offset: ExtendedExpressionOrUnbound,
    count: Optional[ExtendedExpressionOrUnbound],
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = _bind(plan, registry)
        ns = infer_plan_schema(bound_plan, registry=registry)

        bound_offset = resolve_expression(offset, ns, registry) if offset else None
        # count=None means "all remaining rows" (FetchRel leaves count_expr unset).
        bound_count = (
            resolve_expression(count, ns, registry) if count is not None else None
        )

        return _plan_from(
            [bound_plan],
            lambda inp: stalg.Rel(
                fetch=stalg.FetchRel(
                    input=inp[0],
                    offset_expr=bound_offset.referred_expr[0].expression
                    if bound_offset
                    else None,
                    count_expr=bound_count.referred_expr[0].expression
                    if bound_count
                    else None,
                    advanced_extension=extension,
                )
            ),
            bound_plan.relations[-1].root.names,
            (bound_plan, bound_offset, bound_count),
        )

    return build_scoped(resolve)


def join(
    left: PlanOrUnbound,
    right: PlanOrUnbound,
    expression: ExtendedExpressionOrUnbound,
    type: stalg.JoinRel.JoinType,
    *,
    post_join_filter: Optional[ExtendedExpressionOrUnbound] = None,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_left = _bind(left, registry)
        bound_right = _bind(right, registry)
        left_ns = infer_plan_schema(bound_left, registry=registry)
        right_ns = infer_plan_schema(bound_right, registry=registry)

        # The join condition binds against the combined left+right schema.
        ns = stt.NamedStruct(
            struct=stt.Type.Struct(
                types=list(left_ns.struct.types) + list(right_ns.struct.types),
                nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
            ),
            names=list(left_ns.names) + list(right_ns.names),
        )
        bound_expression: stee.ExtendedExpression = resolve_expression(
            expression, ns, registry
        )

        # The output names must match the columns the join type actually emits
        # (semi/anti drop a side, mark appends a boolean).
        type_name = stalg.JoinRel.JoinType.Name(type)
        out_names = join_output_names(type_name, left_ns.names, right_ns.names)

        # post_join_filter is applied to each output record after
        # join-type-specific output formation (semantically a FilterRel above the
        # join), so it resolves against the output schema -- which for semi/anti
        # joins is a single side, not the combined schema.
        bound_post = None
        if post_join_filter is not None:
            output_ns = stt.NamedStruct(
                names=out_names,
                struct=_join_output_struct(
                    type_name,
                    bound_left.relations[-1].root.input,
                    bound_right.relations[-1].root.input,
                    registry=registry,
                ),
            )
            bound_post = resolve_expression(post_join_filter, output_ns, registry)

        return _plan_from(
            [bound_left, bound_right],
            lambda inp: stalg.Rel(
                join=stalg.JoinRel(
                    left=inp[0],
                    right=inp[1],
                    expression=bound_expression.referred_expr[0].expression,
                    post_join_filter=bound_post.referred_expr[0].expression
                    if bound_post
                    else None,
                    type=type,
                    advanced_extension=extension,
                )
            ),
            out_names,
            (bound_left, bound_right, bound_expression, bound_post),
        )

    return build_scoped(resolve)


def lateral_join(
    left: PlanOrUnbound,
    right: Callable[[LateralInput], PlanOrUnbound],
    type: stalg.JoinRel.JoinType,
    *,
    expression: Optional[ExtendedExpressionOrUnbound] = None,
    post_join_filter: Optional[ExtendedExpressionOrUnbound] = None,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """A LateralJoinRel: the right (dependent) input is evaluated once per left
    row and may reference the current left row.

    ``right`` is a function of a :class:`~substrait.builders.extended_expression.LateralInput`
    handle to the left; use ``handle.column(...)`` inside it to correlate on the
    current left row (an id-based ``OuterReference`` to this relation's
    ``rel_anchor``). Capturing the handle avoids counting nesting levels: an
    inner lateral join can reference an outer one by using its handle directly.

    Only INNER and left-oriented join types are valid for lateral joins: INNER,
    LEFT, LEFT_SEMI, LEFT_ANTI, LEFT_SINGLE, LEFT_MARK. ``expression`` is an
    optional match condition over the combined left+right schema.
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_left = _bind(left, registry)
        left_ns = infer_plan_schema(bound_left, registry=registry)

        anchor = next_rel_anchor()
        handle = LateralInput(anchor, left_ns)
        # Bind the left schema to `anchor` while the right input is built and its
        # schema inferred, so id-based references (handle.column(...)) resolve to
        # the current left row during that inference.
        with _outer_anchor_binding(anchor, left_ns.struct):
            unbound_right = right(handle)
            bound_right = _bind(unbound_right, registry)
            right_ns = infer_plan_schema(bound_right, registry=registry)

            # The join condition binds against the combined left+right input row.
            ns = stt.NamedStruct(
                struct=stt.Type.Struct(
                    types=list(left_ns.struct.types) + list(right_ns.struct.types),
                    nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
                ),
                names=list(left_ns.names) + list(right_ns.names),
            )
            bound_expression = (
                resolve_expression(expression, ns, registry)
                if expression is not None
                else None
            )

            # Output names/columns follow the same per-join-type shape as a
            # regular join (semi/anti drop the right side, mark appends a boolean).
            type_name = stalg.JoinRel.JoinType.Name(type)
            out_names = join_output_names(type_name, left_ns.names, right_ns.names)

            # post_join_filter is applied to each output record after
            # join-type-specific output formation (semantically a FilterRel above
            # the join), so it resolves against the *output* schema -- which for
            # semi/anti joins is a single side and for a mark join carries the
            # appended marker column -- not the combined input row.
            bound_post = None
            if post_join_filter is not None:
                output_ns = stt.NamedStruct(
                    names=out_names,
                    struct=_join_struct_from_schemas(
                        type_name, left_ns.struct, right_ns.struct
                    ),
                )
                bound_post = resolve_expression(post_join_filter, output_ns, registry)

        return _plan_from(
            [bound_left, bound_right],
            lambda inp: stalg.Rel(
                lateral_join=stalg.LateralJoinRel(
                    common=stalg.RelCommon(rel_anchor=anchor),
                    left=inp[0],
                    right=inp[1],
                    expression=(
                        bound_expression.referred_expr[0].expression
                        if bound_expression
                        else None
                    ),
                    post_join_filter=(
                        bound_post.referred_expr[0].expression if bound_post else None
                    ),
                    type=type,
                    advanced_extension=extension,
                )
            ),
            out_names,
            (bound_left, bound_right, bound_expression, bound_post),
        )

    return build_scoped(resolve)


def cross(
    left: PlanOrUnbound,
    right: PlanOrUnbound,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_left = _bind(left, registry)
        bound_right = _bind(right, registry)
        left_ns = infer_plan_schema(bound_left, registry=registry)
        right_ns = infer_plan_schema(bound_right, registry=registry)

        ns = stt.NamedStruct(
            struct=stt.Type.Struct(
                types=list(left_ns.struct.types) + list(right_ns.struct.types),
                nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
            ),
            names=list(left_ns.names) + list(right_ns.names),
        )

        return _plan_from(
            [bound_left, bound_right],
            lambda inp: stalg.Rel(
                cross=stalg.CrossRel(
                    left=inp[0],
                    right=inp[1],
                    advanced_extension=extension,
                )
            ),
            ns.names,
            (bound_left, bound_right),
        )

    return build_scoped(resolve)


def aggregate(
    input: PlanOrUnbound,
    grouping_expressions: Iterable[ExtendedExpressionOrUnbound],
    measures: Iterable[ExtendedExpressionOrUnbound],
    *,
    grouping_sets: Optional[Iterable[Iterable[int]]] = None,
    filters: Optional[Iterable[Optional[ExtendedExpressionOrUnbound]]] = None,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """Build an AggregateRel.

    ``grouping_sets`` is an optional list of index lists into
    ``grouping_expressions``; each becomes one ``Grouping`` (GROUPING SETS /
    ROLLUP / CUBE). When omitted, a single grouping over every expression is
    emitted. ``filters`` is an optional list, parallel to ``measures``, of
    per-measure ``FILTER (WHERE ...)`` predicates (or ``None``).
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_input = _bind(input, registry)
        ns = infer_plan_schema(bound_input, registry=registry)

        bound_grouping_expressions = [
            resolve_expression(e, ns, registry) for e in grouping_expressions
        ]
        bound_measures = [resolve_expression(e, ns, registry) for e in measures]
        for m in bound_measures:
            # A measure must be an aggregate_function. Reading `.measure` off a
            # reference holding an `expression` instead yields a default-constructed
            # AggregateFunction, and *assigning* that below would emit a measure that
            # is set but empty -- no function reference, no output type. Such a plan
            # is already malformed, but it is also the one shape that breaks the
            # premise `remap_function_references` relies on (a present message implies
            # a real reference), so its unset reference would be renumbered along with
            # the genuine ones. Refuse it here rather than emit it.
            if m.referred_expr[0].WhichOneof("expr_type") != "measure":
                raise ValueError(
                    "aggregate() measures must be aggregate functions; got a "
                    f"{m.referred_expr[0].WhichOneof('expr_type')!r} for "
                    f"{m.referred_expr[0].output_names[0]!r}. Use "
                    "extended_expression.aggregate_function(...) rather than "
                    "scalar_function(...)."
                )

        _filters = (
            list(filters) if filters is not None else [None] * len(bound_measures)
        )
        bound_filters = [
            resolve_expression(f, ns, registry) if f is not None else None
            for f in _filters
        ]

        # One Grouping per grouping set; default is a single set over all keys.
        sets = (
            [list(s) for s in grouping_sets]
            if grouping_sets is not None
            else [list(range(len(bound_grouping_expressions)))]
        )

        names = [
            e.referred_expr[0].output_names[0] for e in bound_grouping_expressions
        ] + [e.referred_expr[0].output_names[0] for e in bound_measures]

        return _plan_from(
            [bound_input],
            lambda inp: stalg.Rel(
                aggregate=stalg.AggregateRel(
                    input=inp[0],
                    grouping_expressions=[
                        e.referred_expr[0].expression
                        for e in bound_grouping_expressions
                    ],
                    groupings=[
                        stalg.AggregateRel.Grouping(expression_references=refs)
                        for refs in sets
                    ],
                    measures=[
                        stalg.AggregateRel.Measure(
                            measure=m.referred_expr[0].measure,
                            filter=bf.referred_expr[0].expression if bf else None,
                        )
                        for m, bf in zip(bound_measures, bound_filters)
                    ],
                    advanced_extension=extension,
                )
            ),
            names,
            (
                bound_input,
                *bound_grouping_expressions,
                *bound_measures,
                *[bf for bf in bound_filters if bf],
            ),
        )

    return build_scoped(resolve)


def write_named_table(
    table_names: Union[str, Iterable[str]],
    input: PlanOrUnbound,
    create_mode: Union[stalg.WriteRel.CreateMode.ValueType, None] = None,
    op: Union[stalg.WriteRel.WriteOp.ValueType, None] = None,
    output_mode: Union[stalg.WriteRel.OutputMode.ValueType, None] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_input = _bind(input, registry)
        ns = infer_plan_schema(bound_input, registry=registry)
        _table_names = [table_names] if isinstance(table_names, str) else table_names
        _create_mode = create_mode or stalg.WriteRel.CREATE_MODE_ERROR_IF_EXISTS
        _op = op if op is not None else stalg.WriteRel.WRITE_OP_CTAS

        return _plan_from(
            [bound_input],
            lambda inp: stalg.Rel(
                write=stalg.WriteRel(
                    input=inp[0],
                    table_schema=ns,
                    op=_op,
                    create_mode=_create_mode,
                    output=output_mode
                    if output_mode is not None
                    else stalg.WriteRel.OUTPUT_MODE_UNSPECIFIED,
                    named_table=stalg.NamedObjectWrite(names=_table_names),
                )
            ),
            ns.names,
            (bound_input,),
            include_version=False,
        )

    return build_scoped(resolve)


def ddl(
    names: Union[str, Iterable[str]],
    object_type: stalg.DdlRel.DdlObject.ValueType,
    op: stalg.DdlRel.DdlOp.ValueType,
    table_schema: Optional[stt.NamedStruct] = None,
    view_definition: Optional[PlanOrUnbound] = None,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """Build a DdlRel (CREATE / DROP of a TABLE or VIEW).

    ``table_schema`` is required for CREATE TABLE; for CREATE VIEW the schema is
    inferred from ``view_definition`` when omitted. DROP needs neither.
    """
    _names = [names] if isinstance(names, str) else list(names)

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        merge_sources = []
        bound_inputs = []
        schema = table_schema
        if view_definition is not None:
            view_plan = _bind(view_definition, registry)
            bound_inputs = [view_plan]
            merge_sources.append(view_plan)
            if schema is None:
                schema = infer_plan_schema(view_plan, registry=registry)

        out_names = list(schema.names) if schema is not None else []
        return _plan_from(
            bound_inputs,
            lambda inp: stalg.Rel(
                ddl=stalg.DdlRel(
                    named_object=stalg.NamedObjectWrite(names=_names),
                    table_schema=schema,
                    object=object_type,
                    op=op,
                    view_definition=inp[0] if inp else None,
                    advanced_extension=extension,
                )
            ),
            out_names,
            tuple(merge_sources),
        )

    return build_scoped(resolve)


def update(
    table_names: Union[str, Iterable[str]],
    table_schema: stt.NamedStruct,
    transformations: Iterable[tuple[int, ExtendedExpressionOrUnbound]],
    condition: Optional[ExtendedExpressionOrUnbound] = None,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """Build an UpdateRel: set ``(column_index -> expression)`` where ``condition``."""
    _names = [table_names] if isinstance(table_names, str) else list(table_names)

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_condition = (
            resolve_expression(condition, table_schema, registry)
            if condition is not None
            else None
        )
        transforms = []
        merge_sources = []
        for column_index, expression in transformations:
            bound = resolve_expression(expression, table_schema, registry)
            merge_sources.append(bound)
            transforms.append(
                stalg.UpdateRel.TransformExpression(
                    column_target=column_index,
                    transformation=bound.referred_expr[0].expression,
                )
            )
        if bound_condition is not None:
            merge_sources.append(bound_condition)

        update_rel = stalg.UpdateRel(
            table_schema=table_schema,
            condition=bound_condition.referred_expr[0].expression
            if bound_condition
            else None,
            transformations=transforms,
        )
        update_rel.named_table.names.extend(_names)

        return stp.Plan(
            version=default_version,
            relations=[
                stp.PlanRel(
                    root=stalg.RelRoot(
                        input=stalg.Rel(update=update_rel),
                        names=list(table_schema.names),
                    )
                )
            ],
            **_merge_plan_metadata(*merge_sources),
        )

    return build_scoped(resolve)


def consistent_partition_window(
    plan: PlanOrUnbound,
    window_functions: Iterable[ExtendedExpressionOrUnbound],
    partition_expressions: Iterable[ExtendedExpressionOrUnbound] = (),
    sorts: Iterable[
        Union[
            ExtendedExpressionOrUnbound,
            tuple[ExtendedExpressionOrUnbound, stalg.SortField.SortDirection.ValueType],
        ]
    ] = (),
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = _bind(plan, registry)
        ns = infer_plan_schema(bound_plan, registry=registry)

        bound_partitions = [
            resolve_expression(e, ns, registry) for e in partition_expressions
        ]

        bound_sorts = [
            (e, stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST)
            if not isinstance(e, tuple)
            else e
            for e in sorts
        ]
        bound_sorts = [
            (resolve_expression(e[0], ns, registry), e[1]) for e in bound_sorts
        ]

        bound_window_fns = [
            resolve_expression(e, ns, registry) for e in window_functions
        ]

        window_rel_functions = []
        for wf_ee in bound_window_fns:
            wf_expr = wf_ee.referred_expr[0].expression.window_function
            window_rel_functions.append(
                stalg.ConsistentPartitionWindowRel.WindowRelFunction(
                    function_reference=wf_expr.function_reference,
                    arguments=list(wf_expr.arguments),
                    options=list(wf_expr.options),
                    output_type=wf_expr.output_type,
                    phase=wf_expr.phase,
                    invocation=wf_expr.invocation,
                    lower_bound=wf_expr.lower_bound
                    if wf_expr.HasField("lower_bound")
                    else None,
                    upper_bound=wf_expr.upper_bound
                    if wf_expr.HasField("upper_bound")
                    else None,
                    bounds_type=wf_expr.bounds_type,
                )
            )

        names = list(bound_plan.relations[-1].root.names) + [
            wf_ee.referred_expr[0].output_names[0]
            if wf_ee.referred_expr[0].output_names
            else f"window_{i}"
            for i, wf_ee in enumerate(bound_window_fns)
        ]

        return _plan_from(
            [bound_plan],
            lambda inp: stalg.Rel(
                window=stalg.ConsistentPartitionWindowRel(
                    input=inp[0],
                    window_functions=window_rel_functions,
                    partition_expressions=[
                        e.referred_expr[0].expression for e in bound_partitions
                    ],
                    sorts=[
                        stalg.SortField(
                            expr=e[0].referred_expr[0].expression,
                            direction=e[1],
                        )
                        for e in bound_sorts
                    ],
                    advanced_extension=extension,
                )
            ),
            names,
            (
                bound_plan,
                *bound_partitions,
                *[e[0] for e in bound_sorts],
                *bound_window_fns,
            ),
        )

    return build_scoped(resolve)


def expand(
    plan: PlanOrUnbound,
    fields: Iterable[tuple],
    names: Iterable[str],
) -> UnboundPlan:
    """Build an ExpandRel (duplicate rows per the expand fields; UNPIVOT).

    Each field is a ``(kind, payload)`` tuple: ``("switching", [exprs])`` for a
    field that takes a different value in each duplicate, or ``("consistent",
    expr)`` for one repeated across duplicates. ``names`` are the output column
    names -- one per field plus a trailing name for the i32 duplicate index.
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_input = _bind(plan, registry)
        ns = infer_plan_schema(bound_input, registry=registry)

        expand_fields = []
        merge_sources = [bound_input]
        for kind, payload in fields:
            if kind == "switching":
                bounds = [resolve_expression(e, ns, registry) for e in payload]
                merge_sources.extend(bounds)
                expand_fields.append(
                    stalg.ExpandRel.ExpandField(
                        switching_field=stalg.ExpandRel.SwitchingField(
                            duplicates=[b.referred_expr[0].expression for b in bounds]
                        )
                    )
                )
            else:  # "consistent"
                bound = resolve_expression(payload, ns, registry)
                merge_sources.append(bound)
                expand_fields.append(
                    stalg.ExpandRel.ExpandField(
                        consistent_field=bound.referred_expr[0].expression
                    )
                )

        return _plan_from(
            [bound_input],
            lambda inp: stalg.Rel(
                expand=stalg.ExpandRel(
                    input=inp[0],
                    fields=expand_fields,
                )
            ),
            list(names),
            tuple(merge_sources),
        )

    return build_scoped(resolve)


def nested_loop_join(
    left: PlanOrUnbound,
    right: PlanOrUnbound,
    expression: ExtendedExpressionOrUnbound,
    type: stalg.NestedLoopJoinRel.JoinType.ValueType,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """A NestedLoopJoinRel: join over the Cartesian product using ``expression``."""

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_left = _bind(left, registry)
        bound_right = _bind(right, registry)
        left_ns = infer_plan_schema(bound_left, registry=registry)
        right_ns = infer_plan_schema(bound_right, registry=registry)

        ns = stt.NamedStruct(
            struct=stt.Type.Struct(
                types=list(left_ns.struct.types) + list(right_ns.struct.types),
                nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
            ),
            names=list(left_ns.names) + list(right_ns.names),
        )
        bound_expression = resolve_expression(expression, ns, registry)

        out_names = join_output_names(
            stalg.NestedLoopJoinRel.JoinType.Name(type),
            left_ns.names,
            right_ns.names,
        )
        return _plan_from(
            [bound_left, bound_right],
            lambda inp: stalg.Rel(
                nested_loop_join=stalg.NestedLoopJoinRel(
                    left=inp[0],
                    right=inp[1],
                    expression=bound_expression.referred_expr[0].expression,
                    type=type,
                    advanced_extension=extension,
                )
            ),
            out_names,
            (bound_left, bound_right, bound_expression),
        )

    return build_scoped(resolve)


def _comparison_join_keys(left_keys, right_keys, left_ns, right_ns, registry):
    """Build EQ ComparisonJoinKeys from column names/indices on each side."""
    keys = []
    for left_key, right_key in zip(left_keys, right_keys):
        from substrait.builders.extended_expression import column

        left_ref = (
            resolve_expression(column(left_key), left_ns, registry)
            .referred_expr[0]
            .expression.selection
        )
        right_ref = (
            resolve_expression(column(right_key), right_ns, registry)
            .referred_expr[0]
            .expression.selection
        )
        keys.append(
            stalg.ComparisonJoinKey(
                left=left_ref,
                right=right_ref,
                comparison=stalg.ComparisonJoinKey.ComparisonType(
                    simple=stalg.ComparisonJoinKey.SIMPLE_COMPARISON_TYPE_EQ
                ),
            )
        )
    return keys


def _physical_equi_join(rel_name, rel_cls):
    """Factory for the hash_join / merge_join builders (equi-join on key columns)."""

    def builder(
        left: PlanOrUnbound,
        right: PlanOrUnbound,
        left_keys: Iterable[Union[str, int]],
        right_keys: Iterable[Union[str, int]],
        type,
        *,
        post_join_filter: Optional[ExtendedExpressionOrUnbound] = None,
        residual_expression: Optional[ExtendedExpressionOrUnbound] = None,
        extension: Optional[AdvancedExtension] = None,
    ) -> UnboundPlan:
        def resolve(registry: ExtensionRegistry) -> stp.Plan:
            bound_left = _bind(left, registry)
            bound_right = _bind(right, registry)
            left_ns = infer_plan_schema(bound_left, registry=registry)
            right_ns = infer_plan_schema(bound_right, registry=registry)
            keys = _comparison_join_keys(
                list(left_keys), list(right_keys), left_ns, right_ns, registry
            )
            type_name = rel_cls.JoinType.Name(type)
            names = join_output_names(type_name, left_ns.names, right_ns.names)

            # post_join_filter is applied to each output record after
            # join-type-specific output formation (semantically a FilterRel above
            # the join), so it resolves against the output schema -- which for
            # semi/anti joins is a single side. residual_expression is evaluated
            # on each candidate key-match (both rows present), so it resolves
            # against the combined left+right schema. Each is built only when the
            # corresponding predicate is supplied.
            bound_post = None
            if post_join_filter is not None:
                output_ns = stt.NamedStruct(
                    names=names,
                    struct=_join_output_struct(
                        type_name,
                        bound_left.relations[-1].root.input,
                        bound_right.relations[-1].root.input,
                        registry=registry,
                    ),
                )
                bound_post = resolve_expression(post_join_filter, output_ns, registry)

            bound_residual = None
            if residual_expression is not None:
                combined_ns = stt.NamedStruct(
                    struct=stt.Type.Struct(
                        types=list(left_ns.struct.types) + list(right_ns.struct.types),
                        nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
                    ),
                    names=list(left_ns.names) + list(right_ns.names),
                )
                bound_residual = resolve_expression(
                    residual_expression, combined_ns, registry
                )

            return _plan_from(
                [bound_left, bound_right],
                lambda inp: stalg.Rel(
                    **{
                        rel_name: rel_cls(
                            left=inp[0],
                            right=inp[1],
                            keys=keys,
                            type=type,
                            post_join_filter=bound_post.referred_expr[0].expression
                            if bound_post
                            else None,
                            residual_expression=bound_residual.referred_expr[
                                0
                            ].expression
                            if bound_residual
                            else None,
                            advanced_extension=extension,
                        )
                    }
                ),
                names,
                (bound_left, bound_right, bound_post, bound_residual),
            )

        return build_scoped(resolve)

    return builder


hash_join = _physical_equi_join("hash_join", stalg.HashJoinRel)
merge_join = _physical_equi_join("merge_join", stalg.MergeJoinRel)


def _detail_any(detail):
    """A detail object's serialized Any, or the Any itself if already one."""
    return detail.to_any() if hasattr(detail, "to_any") else detail


def extension_leaf(detail, names: Optional[Iterable[str]] = None) -> UnboundPlan:
    """An ExtensionLeafRel (a custom source) from an ExtensionLeafDetail.

    Output names come from the detail's ``derive_schema`` (or ``names`` when a
    raw ``Any`` is passed instead of a detail object).
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        out_names = (
            list(detail.derive_schema().names)
            if hasattr(detail, "derive_schema")
            else list(names or [])
        )
        rel = stalg.Rel(
            extension_leaf=stalg.ExtensionLeafRel(detail=_detail_any(detail))
        )
        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=out_names))],
        )

    return build_scoped(resolve)


def extension_single(plan: PlanOrUnbound, detail) -> UnboundPlan:
    """An ExtensionSingleRel wrapping ``input``.

    ``detail`` is an ``ExtensionSingleDetail`` (its ``derive_schema`` defines the
    output) or a raw ``google.protobuf.Any`` (the input schema is assumed to pass
    through, since the detail is then opaque to inference).
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = _bind(plan, registry)
        if hasattr(detail, "derive_schema"):
            input_struct = infer_plan_schema(bound_plan, registry=registry).struct
            names = list(detail.derive_schema(input_struct).names)
        else:
            names = list(bound_plan.relations[-1].root.names)
        return _plan_from(
            [bound_plan],
            lambda inp: stalg.Rel(
                extension_single=stalg.ExtensionSingleRel(
                    input=inp[0], detail=_detail_any(detail)
                )
            ),
            names,
            (bound_plan,),
        )

    return build_scoped(resolve)


def extension_multi(inputs: Iterable[PlanOrUnbound], detail) -> UnboundPlan:
    """An ExtensionMultiRel over ``inputs`` from an ExtensionMultiDetail."""

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_inputs = [_bind(i, registry) for i in inputs]
        input_structs = [
            infer_plan_schema(b, registry=registry).struct for b in bound_inputs
        ]
        names = list(detail.derive_schema(input_structs).names)
        return _plan_from(
            bound_inputs,
            lambda inp: stalg.Rel(
                extension_multi=stalg.ExtensionMultiRel(
                    inputs=inp,
                    detail=_detail_any(detail),
                )
            ),
            names,
            tuple(bound_inputs),
        )

    return build_scoped(resolve)


def exchange(
    plan: PlanOrUnbound,
    partition_count: int = 0,
    broadcast: bool = False,
) -> UnboundPlan:
    """An ExchangeRel that redistributes rows (schema unchanged).

    Defaults to round-robin partitioning into ``partition_count`` partitions;
    pass ``broadcast=True`` to broadcast every row to all partitions.
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = _bind(plan, registry)
        kind = (
            {"broadcast": stalg.ExchangeRel.Broadcast()}
            if broadcast
            else {"round_robin": stalg.ExchangeRel.RoundRobin()}
        )
        return _plan_from(
            [bound_plan],
            lambda inp: stalg.Rel(
                exchange=stalg.ExchangeRel(
                    input=inp[0],
                    partition_count=partition_count,
                    **kind,
                )
            ),
            bound_plan.relations[-1].root.names,
            (bound_plan,),
        )

    return build_scoped(resolve)


def top_n(
    plan: PlanOrUnbound,
    sorts: Iterable[
        tuple[ExtendedExpressionOrUnbound, stalg.SortField.SortDirection.ValueType]
    ],
    count: ExtendedExpressionOrUnbound,
    offset: Optional[ExtendedExpressionOrUnbound] = None,
    with_ties: bool = False,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """A TopNRel: a fused sort + fetch (ORDER BY ... LIMIT).

    ``with_ties`` selects ``FETCH_MODE_WITH_TIES`` (keep rows tied with the last)
    over the default ``FETCH_MODE_ROWS_ONLY``.
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = _bind(plan, registry)
        ns = infer_plan_schema(bound_plan, registry=registry)
        bound_sorts = [
            (resolve_expression(e, ns, registry), direction) for e, direction in sorts
        ]
        bound_count = resolve_expression(count, ns, registry)
        bound_offset = (
            resolve_expression(offset, ns, registry) if offset is not None else None
        )

        return _plan_from(
            [bound_plan],
            lambda inp: stalg.Rel(
                top_n=stalg.TopNRel(
                    input=inp[0],
                    sorts=[
                        stalg.SortField(
                            expr=s.referred_expr[0].expression, direction=direction
                        )
                        for s, direction in bound_sorts
                    ],
                    count=bound_count.referred_expr[0].expression,
                    offset=bound_offset.referred_expr[0].expression
                    if bound_offset
                    else None,
                    mode=stalg.FetchMode.FETCH_MODE_WITH_TIES
                    if with_ties
                    else stalg.FetchMode.FETCH_MODE_ROWS_ONLY,
                    advanced_extension=extension,
                )
            ),
            bound_plan.relations[-1].root.names,
            (bound_plan, *[s for s, _ in bound_sorts], bound_count, bound_offset),
        )

    return build_scoped(resolve)
