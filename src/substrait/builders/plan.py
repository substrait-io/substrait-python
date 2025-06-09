"""
Plan builders take either Plan or UnboundPlan objects as input rather than plain Rels.
This is to make sure that additional information like extension types of functions are not lost.
All builders return UnboundPlan objects that can be materialized to a Plan using an ExtensionRegistry.
See `examples/builder_example.py` for usage.
"""

from typing import Iterable, Union, Callable

import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
from substrait.extension_registry import ExtensionRegistry
from substrait.builders.extended_expression import (
    ExtendedExpressionOrUnbound,
    resolve_expression,
)
from substrait.type_inference import infer_plan_schema
from substrait.utils import merge_extension_declarations, merge_extension_uris

UnboundPlan = Callable[[ExtensionRegistry], stp.Plan]

PlanOrUnbound = Union[stp.Plan, UnboundPlan]


def _merge_extensions(*objs):
    return {
        "extension_uris": merge_extension_uris(*[b.extension_uris for b in objs if b]),
        "extensions": merge_extension_declarations(*[b.extensions for b in objs if b]),
    }


def read_named_table(
    names: Union[str, Iterable[str]], named_struct: stt.NamedStruct
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        _names = [names] if isinstance(names, str) else names

        rel = stalg.Rel(
            read=stalg.ReadRel(
                common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                base_schema=named_struct,
                named_table=stalg.ReadRel.NamedTable(names=_names),
            )
        )

        return stp.Plan(
            relations=[
                stp.PlanRel(root=stalg.RelRoot(input=rel, names=named_struct.names))
            ]
        )

    return resolve


def project(
    plan: PlanOrUnbound, expressions: Iterable[ExtendedExpressionOrUnbound]
) -> UnboundPlan:
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
            )
        )

        return stp.Plan(
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
            **_merge_extensions(_plan, *bound_expressions),
        )

    return resolve


def filter(plan: PlanOrUnbound, expression: ExtendedExpressionOrUnbound) -> UnboundPlan:
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
            )
        )

        names = ns.names

        return stp.Plan(
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
            )
        )

        return stp.Plan(
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
    count: ExtendedExpressionOrUnbound,
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_plan = plan if isinstance(plan, stp.Plan) else plan(registry)
        ns = infer_plan_schema(bound_plan)

        bound_offset = resolve_expression(offset, ns, registry) if offset else None
        bound_count = resolve_expression(count, ns, registry)

        rel = stalg.Rel(
            fetch=stalg.FetchRel(
                input=bound_plan.relations[-1].root.input,
                offset_expr=bound_offset.referred_expr[0].expression
                if bound_offset
                else None,
                count_expr=bound_count.referred_expr[0].expression,
            )
        )

        return stp.Plan(
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

        rel = stalg.Rel(
            join=stalg.JoinRel(
                left=bound_left.relations[-1].root.input,
                right=bound_right.relations[-1].root.input,
                expression=bound_expression.referred_expr[0].expression,
                type=type,
            )
        )

        return stp.Plan(
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=ns.names))],
            **_merge_extensions(bound_left, bound_right, bound_expression),
        )

    return resolve


def cross(
    left: PlanOrUnbound,
    right: PlanOrUnbound,
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
            )
        )

        return stp.Plan(
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=ns.names))],
            **_merge_extensions(bound_left, bound_right),
        )

    return resolve


# TODO grouping sets
def aggregate(
    input: PlanOrUnbound,
    grouping_expressions: Iterable[ExtendedExpressionOrUnbound],
    measures: Iterable[ExtendedExpressionOrUnbound],
) -> UnboundPlan:
    def resolve(registry: ExtensionRegistry) -> stp.Plan:
        bound_input = input if isinstance(input, stp.Plan) else input(registry)
        ns = infer_plan_schema(bound_input)

        bound_grouping_expressions = [
            resolve_expression(e, ns, registry) for e in grouping_expressions
        ]
        bound_measures = [resolve_expression(e, ns, registry) for e in measures]

        rel = stalg.Rel(
            aggregate=stalg.AggregateRel(
                input=bound_input.relations[-1].root.input,
                grouping_expressions=[
                    e.referred_expr[0].expression for e in bound_grouping_expressions
                ],
                groupings=[
                    stalg.AggregateRel.Grouping(
                        expression_references=range(len(bound_grouping_expressions)),
                        grouping_expressions=[
                            e.referred_expr[0].expression
                            for e in bound_grouping_expressions
                        ],
                    )
                ],
                measures=[
                    stalg.AggregateRel.Measure(measure=m.referred_expr[0].measure)
                    for m in bound_measures
                ],
            )
        )

        names = [
            e.referred_expr[0].output_names[0] for e in bound_grouping_expressions
        ] + [e.referred_expr[0].output_names[0] for e in bound_measures]

        return stp.Plan(
            relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
            **_merge_extensions(
                bound_input, *bound_grouping_expressions, *bound_measures
            ),
        )

    return resolve
