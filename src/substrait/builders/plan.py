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
    resolve_expression,
)
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema, join_output_names
from substrait.utils import (
    merge_extension_declarations,
    merge_extension_urns,
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


def _merge_extensions(*objs):
    """Merge extension URNs and declarations from multiple plan/expression objects."""
    return {
        "extension_urns": merge_extension_urns(*[b.extension_urns for b in objs if b]),
        "extensions": merge_extension_declarations(*[b.extensions for b in objs if b]),
    }


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

    return resolve


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

    return resolve


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

    return resolve


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

    return resolve


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
        _plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        ns = infer_plan_schema(_plan)
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            resolve_expression(e, ns, registry) for e in expressions
        ]

        names = list(_plan.relations[-1].root.names) + [
            e.output_names[0] for ee in bound_expressions for e in ee.referred_expr
        ]

        rel = stalg.Rel(
            project=stalg.ProjectRel(
                input=_plan.relations[-1].root.input,
                expressions=[
                    e.expression for ee in bound_expressions for e in ee.referred_expr
                ],
                advanced_extension=extension,
            )
        )

        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
            **_merge_extensions(_plan, *bound_expressions),
        )

    return resolve


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
        _plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        ns = infer_plan_schema(_plan)
        bound_expressions: Iterable[stee.ExtendedExpression] = [
            resolve_expression(e, ns, registry) for e in expressions
        ]

        start_index = len(_plan.relations[-1].root.names)

        names = [
            e.output_names[0] for ee in bound_expressions for e in ee.referred_expr
        ]

        rel = stalg.Rel(
            project=stalg.ProjectRel(
                common=stalg.RelCommon(
                    emit=stalg.RelCommon.Emit(
                        output_mapping=[i + start_index for i in range(len(names))]
                    )
                ),
                input=_plan.relations[-1].root.input,
                expressions=[
                    e.expression for ee in bound_expressions for e in ee.referred_expr
                ],
                advanced_extension=extension,
            )
        )

        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
            **_merge_extensions(_plan, *bound_expressions),
        )

    return resolve


def filter(
    plan: PlanOrUnbound,
    expression: ExtendedExpressionOrUnbound,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        ns = infer_plan_schema(bound_plan)
        bound_expression: stee.ExtendedExpression = resolve_expression(
            expression, ns, registry
        )

        rel = stalg.Rel(
            filter=stalg.FilterRel(
                input=bound_plan.relations[-1].root.input,
                condition=bound_expression.referred_expr[0].expression,
                advanced_extension=extension,
            )
        )

        names = ns.names

        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
            **_merge_extensions(bound_plan, bound_expression),
        )

    return resolve


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
        bound_plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        ns = infer_plan_schema(bound_plan)

        bound_expressions = [
            (e, stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST)
            if not isinstance(e, tuple)
            else e
            for e in expressions
        ]
        bound_expressions = [
            (resolve_expression(e[0], ns, registry), e[1]) for e in bound_expressions
        ]

        rel = stalg.Rel(
            sort=stalg.SortRel(
                input=bound_plan.relations[-1].root.input,
                sorts=[
                    stalg.SortField(
                        expr=e[0].referred_expr[0].expression,
                        direction=e[1],
                    )
                    for e in bound_expressions
                ],
                advanced_extension=extension,
            ),
        )

        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=ns.names))],
            **_merge_extensions(bound_plan, *[e[0] for e in bound_expressions]),
        )

    return resolve


def set(inputs: Iterable[PlanOrUnbound], op: stalg.SetRel.SetOp) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_inputs = [i if isinstance(i, stp.Plan) else i(registry) for i in inputs]
        rel = stalg.Rel(
            set=stalg.SetRel(
                inputs=[plan.relations[-1].root.input for plan in bound_inputs], op=op
            )
        )

        return stp.Plan(
            version=default_version,
            relations=[
                stp.PlanRel(
                    root=stalg.RelRoot(
                        input=rel, names=bound_inputs[0].relations[-1].root.names
                    )
                )
            ],
            **_merge_extensions(*bound_inputs),
        )

    return resolve


def fetch(
    plan: PlanOrUnbound,
    offset: ExtendedExpressionOrUnbound,
    count: Optional[ExtendedExpressionOrUnbound],
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        ns = infer_plan_schema(bound_plan)

        bound_offset = resolve_expression(offset, ns, registry) if offset else None
        # count=None means "all remaining rows" (FetchRel leaves count_expr unset).
        bound_count = (
            resolve_expression(count, ns, registry) if count is not None else None
        )

        rel = stalg.Rel(
            fetch=stalg.FetchRel(
                input=bound_plan.relations[-1].root.input,
                offset_expr=bound_offset.referred_expr[0].expression
                if bound_offset
                else None,
                count_expr=bound_count.referred_expr[0].expression
                if bound_count
                else None,
                advanced_extension=extension,
            )
        )

        return stp.Plan(
            version=default_version,
            relations=[
                stp.PlanRel(
                    root=stalg.RelRoot(
                        input=rel, names=bound_plan.relations[-1].root.names
                    )
                )
            ],
            **_merge_extensions(bound_plan, bound_offset, bound_count),
        )

    return resolve


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
        bound_left = left if isinstance(left, stp.Plan) else left(registry)
        bound_right = right if isinstance(right, stp.Plan) else right(registry)
        left_ns = infer_plan_schema(bound_left)
        right_ns = infer_plan_schema(bound_right)

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
        bound_post = (
            resolve_expression(post_join_filter, ns, registry)
            if post_join_filter is not None
            else None
        )

        rel = stalg.Rel(
            join=stalg.JoinRel(
                left=bound_left.relations[-1].root.input,
                right=bound_right.relations[-1].root.input,
                expression=bound_expression.referred_expr[0].expression,
                post_join_filter=bound_post.referred_expr[0].expression
                if bound_post
                else None,
                type=type,
                advanced_extension=extension,
            )
        )

        # The join condition resolves against the combined left+right schema, but
        # the output names must match the columns the join type actually emits
        # (semi/anti drop a side, mark appends a boolean).
        out_names = join_output_names(
            stalg.JoinRel.JoinType.Name(type), left_ns.names, right_ns.names
        )
        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=out_names))],
            **_merge_extensions(bound_left, bound_right, bound_expression, bound_post),
        )

    return resolve


def cross(
    left: PlanOrUnbound,
    right: PlanOrUnbound,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_left = left if isinstance(left, stp.Plan) else left(registry)
        bound_right = right if isinstance(right, stp.Plan) else right(registry)
        left_ns = infer_plan_schema(bound_left)
        right_ns = infer_plan_schema(bound_right)

        ns = stt.NamedStruct(
            struct=stt.Type.Struct(
                types=list(left_ns.struct.types) + list(right_ns.struct.types),
                nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
            ),
            names=list(left_ns.names) + list(right_ns.names),
        )

        rel = stalg.Rel(
            cross=stalg.CrossRel(
                left=bound_left.relations[-1].root.input,
                right=bound_right.relations[-1].root.input,
                advanced_extension=extension,
            )
        )

        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=ns.names))],
            **_merge_extensions(bound_left, bound_right),
        )

    return resolve


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
        bound_input = input if isinstance(input, stp.Plan) else input(registry)
        ns = infer_plan_schema(bound_input)

        bound_grouping_expressions = [
            resolve_expression(e, ns, registry) for e in grouping_expressions
        ]
        bound_measures = [resolve_expression(e, ns, registry) for e in measures]

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

        rel = stalg.Rel(
            aggregate=stalg.AggregateRel(
                input=bound_input.relations[-1].root.input,
                grouping_expressions=[
                    e.referred_expr[0].expression for e in bound_grouping_expressions
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
        )

        names = [
            e.referred_expr[0].output_names[0] for e in bound_grouping_expressions
        ] + [e.referred_expr[0].output_names[0] for e in bound_measures]

        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
            **_merge_extensions(
                bound_input,
                *bound_grouping_expressions,
                *bound_measures,
                *[bf for bf in bound_filters if bf],
            ),
        )

    return resolve


def write_named_table(
    table_names: Union[str, Iterable[str]],
    input: PlanOrUnbound,
    create_mode: Union[stalg.WriteRel.CreateMode.ValueType, None] = None,
    op: Union[stalg.WriteRel.WriteOp.ValueType, None] = None,
    output_mode: Union[stalg.WriteRel.OutputMode.ValueType, None] = None,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_input = input if isinstance(input, stp.Plan) else input(registry)
        ns = infer_plan_schema(bound_input)
        _table_names = [table_names] if isinstance(table_names, str) else table_names
        _create_mode = create_mode or stalg.WriteRel.CREATE_MODE_ERROR_IF_EXISTS
        _op = op if op is not None else stalg.WriteRel.WRITE_OP_CTAS

        write_rel = stalg.Rel(
            write=stalg.WriteRel(
                input=bound_input.relations[-1].root.input,
                table_schema=ns,
                op=_op,
                create_mode=_create_mode,
                output=output_mode
                if output_mode is not None
                else stalg.WriteRel.OUTPUT_MODE_UNSPECIFIED,
                named_table=stalg.NamedObjectWrite(names=_table_names),
            )
        )
        return stp.Plan(
            relations=[
                stp.PlanRel(root=stalg.RelRoot(input=write_rel, names=ns.names))
            ],
            **_merge_extensions(bound_input),
        )

    return resolve


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
        view_rel = None
        schema = table_schema
        if view_definition is not None:
            view_plan = (
                view_definition
                if isinstance(view_definition, stp.Plan)
                else view_definition(registry)
            )
            view_rel = view_plan.relations[-1].root.input
            merge_sources.append(view_plan)
            if schema is None:
                schema = infer_plan_schema(view_plan)

        ddl_rel = stalg.Rel(
            ddl=stalg.DdlRel(
                named_object=stalg.NamedObjectWrite(names=_names),
                table_schema=schema,
                object=object_type,
                op=op,
                view_definition=view_rel,
                advanced_extension=extension,
            )
        )
        out_names = list(schema.names) if schema is not None else []
        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=ddl_rel, names=out_names))],
            **_merge_extensions(*merge_sources),
        )

    return resolve


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
            **_merge_extensions(*merge_sources),
        )

    return resolve


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
        bound_plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        ns = infer_plan_schema(bound_plan)

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

        rel = stalg.Rel(
            window=stalg.ConsistentPartitionWindowRel(
                input=bound_plan.relations[-1].root.input,
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
        )

        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
            **_merge_extensions(
                bound_plan,
                *bound_partitions,
                *[e[0] for e in bound_sorts],
                *bound_window_fns,
            ),
        )

    return resolve


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
        bound_input = plan if isinstance(plan, stp.Plan) else plan(registry)
        ns = infer_plan_schema(bound_input)

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

        rel = stalg.Rel(
            expand=stalg.ExpandRel(
                input=bound_input.relations[-1].root.input,
                fields=expand_fields,
            )
        )
        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=list(names)))],
            **_merge_extensions(*merge_sources),
        )

    return resolve


def nested_loop_join(
    left: PlanOrUnbound,
    right: PlanOrUnbound,
    expression: ExtendedExpressionOrUnbound,
    type: stalg.NestedLoopJoinRel.JoinType.ValueType,
    extension: Optional[AdvancedExtension] = None,
) -> UnboundPlan:
    """A NestedLoopJoinRel: join over the Cartesian product using ``expression``."""

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_left = left if isinstance(left, stp.Plan) else left(registry)
        bound_right = right if isinstance(right, stp.Plan) else right(registry)
        left_ns = infer_plan_schema(bound_left)
        right_ns = infer_plan_schema(bound_right)

        ns = stt.NamedStruct(
            struct=stt.Type.Struct(
                types=list(left_ns.struct.types) + list(right_ns.struct.types),
                nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
            ),
            names=list(left_ns.names) + list(right_ns.names),
        )
        bound_expression = resolve_expression(expression, ns, registry)

        rel = stalg.Rel(
            nested_loop_join=stalg.NestedLoopJoinRel(
                left=bound_left.relations[-1].root.input,
                right=bound_right.relations[-1].root.input,
                expression=bound_expression.referred_expr[0].expression,
                type=type,
                advanced_extension=extension,
            )
        )
        out_names = join_output_names(
            stalg.NestedLoopJoinRel.JoinType.Name(type),
            left_ns.names,
            right_ns.names,
        )
        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=out_names))],
            **_merge_extensions(bound_left, bound_right, bound_expression),
        )

    return resolve


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
        extension: Optional[AdvancedExtension] = None,
    ) -> UnboundPlan:
        def resolve(registry: ExtensionRegistry) -> stp.Plan:
            bound_left = left if isinstance(left, stp.Plan) else left(registry)
            bound_right = right if isinstance(right, stp.Plan) else right(registry)
            left_ns = infer_plan_schema(bound_left)
            right_ns = infer_plan_schema(bound_right)
            keys = _comparison_join_keys(
                list(left_keys), list(right_keys), left_ns, right_ns, registry
            )
            names = join_output_names(
                rel_cls.JoinType.Name(type), left_ns.names, right_ns.names
            )
            rel = stalg.Rel(
                **{
                    rel_name: rel_cls(
                        left=bound_left.relations[-1].root.input,
                        right=bound_right.relations[-1].root.input,
                        keys=keys,
                        type=type,
                        advanced_extension=extension,
                    )
                }
            )
            return stp.Plan(
                version=default_version,
                relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
                **_merge_extensions(bound_left, bound_right),
            )

        return resolve

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

    return resolve


def extension_single(plan: PlanOrUnbound, detail) -> UnboundPlan:
    """An ExtensionSingleRel wrapping ``input``.

    ``detail`` is an ``ExtensionSingleDetail`` (its ``derive_schema`` defines the
    output) or a raw ``google.protobuf.Any`` (the input schema is assumed to pass
    through, since the detail is then opaque to inference).
    """

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        if hasattr(detail, "derive_schema"):
            input_struct = infer_plan_schema(bound_plan).struct
            names = list(detail.derive_schema(input_struct).names)
        else:
            names = list(bound_plan.relations[-1].root.names)
        rel = stalg.Rel(
            extension_single=stalg.ExtensionSingleRel(
                input=bound_plan.relations[-1].root.input, detail=_detail_any(detail)
            )
        )
        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
            **_merge_extensions(bound_plan),
        )

    return resolve


def extension_multi(inputs: Iterable[PlanOrUnbound], detail) -> UnboundPlan:
    """An ExtensionMultiRel over ``inputs`` from an ExtensionMultiDetail."""

    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_inputs = [i if isinstance(i, stp.Plan) else i(registry) for i in inputs]
        input_structs = [infer_plan_schema(b).struct for b in bound_inputs]
        names = list(detail.derive_schema(input_structs).names)
        rel = stalg.Rel(
            extension_multi=stalg.ExtensionMultiRel(
                inputs=[b.relations[-1].root.input for b in bound_inputs],
                detail=_detail_any(detail),
            )
        )
        return stp.Plan(
            version=default_version,
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
            **_merge_extensions(*bound_inputs),
        )

    return resolve


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
        bound_plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        kind = (
            {"broadcast": stalg.ExchangeRel.Broadcast()}
            if broadcast
            else {"round_robin": stalg.ExchangeRel.RoundRobin()}
        )
        rel = stalg.Rel(
            exchange=stalg.ExchangeRel(
                input=bound_plan.relations[-1].root.input,
                partition_count=partition_count,
                **kind,
            )
        )
        return stp.Plan(
            version=default_version,
            relations=[
                stp.PlanRel(
                    root=stalg.RelRoot(
                        input=rel, names=bound_plan.relations[-1].root.names
                    )
                )
            ],
            **_merge_extensions(bound_plan),
        )

    return resolve


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
        bound_plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        ns = infer_plan_schema(bound_plan)
        bound_sorts = [
            (resolve_expression(e, ns, registry), direction) for e, direction in sorts
        ]
        bound_count = resolve_expression(count, ns, registry)
        bound_offset = (
            resolve_expression(offset, ns, registry) if offset is not None else None
        )

        rel = stalg.Rel(
            top_n=stalg.TopNRel(
                input=bound_plan.relations[-1].root.input,
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
        )
        return stp.Plan(
            version=default_version,
            relations=[
                stp.PlanRel(
                    root=stalg.RelRoot(
                        input=rel, names=bound_plan.relations[-1].root.names
                    )
                )
            ],
            **_merge_extensions(
                bound_plan,
                *[s for s, _ in bound_sorts],
                bound_count,
                bound_offset,
            ),
        )

    return resolve
