import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.builders.type import boolean, i64
from substrait.builders.plan import read_named_table, aggregate
from substrait.builders.extended_expression import column, aggregate_function
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema
import yaml

content = """%YAML 1.2
---
aggregate_functions:
  - name: "count"
    description: Count a set of values
    impls:
      - args:
          - name: x
            value: any
        nullability: DECLARED_OUTPUT
        decomposable: MANY
        intermediate: i64
        return: i64
"""


registry = ExtensionRegistry(load_default_extensions=False)
registry.register_extension_dict(yaml.safe_load(content), uri="test_uri")

struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_aggregate():
    table = read_named_table("table", named_struct)

    group_expr = column("id")
    measure_expr = aggregate_function(
        "test_uri", "count", expressions=[column("is_applicable")], alias=["count"]
    )

    actual = aggregate(
        table, grouping_expressions=[group_expr], measures=[measure_expr]
    )(registry)

    ns = infer_plan_schema(table(None))

    expected = stp.Plan(
        extension_uris=[ste.SimpleExtensionURI(extension_uri_anchor=1, uri="test_uri")],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=1, function_anchor=1, name="count"
                )
            )
        ],
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        aggregate=stalg.AggregateRel(
                            input=table(None).relations[-1].root.input,
                            grouping_expressions=[
                                group_expr(ns, registry).referred_expr[0].expression
                            ],
                            groupings=[
                                stalg.AggregateRel.Grouping(
                                    grouping_expressions=[
                                        group_expr(ns, registry)
                                        .referred_expr[0]
                                        .expression
                                    ],
                                    expression_references=[0],
                                )
                            ],
                            measures=[
                                stalg.AggregateRel.Measure(
                                    measure=measure_expr(ns, registry)
                                    .referred_expr[0]
                                    .measure
                                )
                            ],
                        )
                    ),
                    names=["id", "count"],
                )
            )
        ],
    )

    assert actual == expected
