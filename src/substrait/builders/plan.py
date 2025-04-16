from typing import Iterable, Union

import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
from substrait.extension_registry import ExtensionRegistry
from substrait.builders.extended_expression import UnboundExtendedExpression
from substrait.type_inference import infer_plan_schema
from substrait.utils import merge_extension_declarations, merge_extension_uris


def _merge_extensions(*objs):
    return {
        "extension_uris": merge_extension_uris(*[b.extension_uris for b in objs]),
        "extensions": merge_extension_declarations(*[b.extensions for b in objs]),
    }


def read_named_table(names: Union[str, Iterable[str]], named_struct: stt.NamedStruct):
    names = [names] if isinstance(names, str) else names
    
    rel = stalg.Rel(
        read=stalg.ReadRel(
            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
            base_schema=named_struct,
            named_table=stalg.ReadRel.NamedTable(names=names),
        )
    )

    return stp.Plan(
        relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=named_struct.names))]
    )


def project(
    plan: stp.Plan, expressions: Iterable[UnboundExtendedExpression], registry: ExtensionRegistry
) -> stp.Plan:
    ns = infer_plan_schema(plan)
    expressions: Iterable[stee.ExtendedExpression] = [e(ns, registry) for e in expressions]

    start_index = len(plan.relations[-1].root.names)

    names = [e.output_names[0] for ee in expressions for e in ee.referred_expr]

    rel = stalg.Rel(
        project=stalg.ProjectRel(
            common=stalg.RelCommon(
                emit=stalg.RelCommon.Emit(
                    output_mapping=[i + start_index for i in range(len(names))]
                )
            ),
            input=plan.relations[-1].root.input,
            expressions=[e.expression for ee in expressions for e in ee.referred_expr],
        )
    )

    return stp.Plan(
        relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
        **_merge_extensions(plan, *expressions),
    )

def filter(
    plan: stp.Plan, expression: UnboundExtendedExpression, registry: ExtensionRegistry
) -> stp.Plan:
    ns = infer_plan_schema(plan)
    expression: stee.ExtendedExpression = expression(ns, registry)

    rel = stalg.Rel(
        filter=stalg.FilterRel(
            input=plan.relations[-1].root.input,
            condition=expression.referred_expr[0].expression,
        )
    )

    names = ns.names

    return stp.Plan(
        relations=[stp.PlanRel(root=stalg.RelRoot(input=rel, names=names))],
        **_merge_extensions(plan, expression),
    )
