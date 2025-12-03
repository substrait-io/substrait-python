"""
test suite for URI <-> URN migration.

This test set ensures that generated plans from builders contain both uris and urns.

NOTE: This file is temporary and can be removed once the URI -> URN migration
is complete across all Substrait implementations.
"""

import yaml

import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.extended_expression_pb2 as stex
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.builders.extended_expression import (
    scalar_function,
    literal,
    column,
    aggregate_function,
)
from substrait.builders.type import i64
from substrait.builders.plan import (
    read_named_table,
    aggregate,
    project,
    filter,
    default_version,
)
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema


def test_extended_expression_outputs_both_uri_and_urn():
    """Test that scalar_function outputs both SimpleExtensionURI and SimpleExtensionURN."""
    content = """%YAML 1.2
---
urn: extension:test:functions
scalar_functions:
  - name: "test_func"
    description: ""
    impls:
      - args:
          - value: i8
        return: i8
"""
    uri = "https://test.example.com/functions.yaml"
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(yaml.safe_load(content), uri=uri)

    struct = stt.Type.Struct(
        types=[stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED))]
    )
    named_struct = stt.NamedStruct(names=["value"], struct=struct)

    func_expr = scalar_function(
        "extension:test:functions",
        "test_func",
        expressions=[
            literal(
                10,
                type=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
            )
        ],
    )

    actual = func_expr(named_struct, registry)

    expected = stex.ExtendedExpression(
        extension_urns=[
            ste.SimpleExtensionURN(
                extension_urn_anchor=1, urn="extension:test:functions"
            )
        ],
        extension_uris=[ste.SimpleExtensionURI(extension_uri_anchor=1, uri=uri)],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_urn_reference=1,
                    extension_uri_reference=1,
                    function_anchor=1,
                    name="test_func:i8",
                )
            )
        ],
        referred_expr=[
            stex.ExpressionReference(
                expression=stalg.Expression(
                    scalar_function=stalg.Expression.ScalarFunction(
                        function_reference=1,
                        output_type=stt.Type(
                            i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                        ),
                        arguments=[
                            stalg.FunctionArgument(
                                value=stalg.Expression(
                                    literal=stalg.Expression.Literal(i8=10)
                                )
                            )
                        ],
                    )
                ),
                output_names=["test_func(Literal(10))"],
            )
        ],
        base_schema=stt.NamedStruct(
            names=["value"],
            struct=stt.Type.Struct(
                types=[
                    stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED))
                ]
            ),
        ),
    )

    assert actual == expected


def test_project_outputs_both_uri_and_urn():
    """Test that project plans with scalar functions have both URI and URN in proto."""
    content = """%YAML 1.2
---
urn: extension:test:math
scalar_functions:
  - name: "add"
    description: ""
    impls:
      - args:
          - value: i64
          - value: i64
        return: i64
"""
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(
        yaml.safe_load(content), uri="https://test.example.com/math.yaml"
    )

    struct = stt.Type.Struct(types=[i64(nullable=False), i64(nullable=False)])
    named_struct = stt.NamedStruct(names=["a", "b"], struct=struct)

    table = read_named_table("table", named_struct)
    add_expr = scalar_function(
        "extension:test:math",
        "add",
        expressions=[column("a"), column("b")],
        alias=["add"],
    )

    actual = project(table, [add_expr])(registry)

    ns = infer_plan_schema(table(None))

    expected = stp.Plan(
        version=default_version,
        extension_urns=[
            ste.SimpleExtensionURN(extension_urn_anchor=1, urn="extension:test:math")
        ],
        extension_uris=[
            ste.SimpleExtensionURI(
                extension_uri_anchor=1, uri="https://test.example.com/math.yaml"
            )
        ],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_urn_reference=1,
                    extension_uri_reference=1,
                    function_anchor=1,
                    name="add:i64_i64",
                )
            )
        ],
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        project=stalg.ProjectRel(
                            common=stalg.RelCommon(
                                emit=stalg.RelCommon.Emit(output_mapping=[2])
                            ),
                            input=table(None).relations[-1].root.input,
                            expressions=[
                                add_expr(ns, registry).referred_expr[0].expression
                            ],
                        )
                    ),
                    names=["add"],
                )
            )
        ],
    )

    assert actual == expected


def test_filter_outputs_both_uri_and_urn():
    """Test that filter plans with scalar functions have both URI and URN in proto."""
    content = """%YAML 1.2
---
urn: extension:test:comparison
scalar_functions:
  - name: "greater_than"
    description: ""
    impls:
      - args:
          - value: i64
          - value: i64
        return: boolean
"""
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(
        yaml.safe_load(content), uri="https://test.example.com/comparison.yaml"
    )

    struct = stt.Type.Struct(types=[i64(nullable=False)])
    named_struct = stt.NamedStruct(names=["value"], struct=struct)

    table = read_named_table("table", named_struct)
    gt_expr = scalar_function(
        "extension:test:comparison",
        "greater_than",
        expressions=[column("value"), literal(100, i64(nullable=False))],
    )

    actual = filter(table, gt_expr)(registry)

    ns = infer_plan_schema(table(None))

    expected = stp.Plan(
        version=default_version,
        extension_urns=[
            ste.SimpleExtensionURN(
                extension_urn_anchor=1, urn="extension:test:comparison"
            )
        ],
        extension_uris=[
            ste.SimpleExtensionURI(
                extension_uri_anchor=1, uri="https://test.example.com/comparison.yaml"
            )
        ],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_urn_reference=1,
                    extension_uri_reference=1,
                    function_anchor=1,
                    name="greater_than:i64_i64",
                )
            )
        ],
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        filter=stalg.FilterRel(
                            input=table(None).relations[-1].root.input,
                            condition=gt_expr(ns, registry).referred_expr[0].expression,
                        )
                    ),
                    names=["value"],
                )
            )
        ],
    )

    assert actual == expected


def test_aggregate_with_aggregate_function():
    """Test that aggregate plans with aggregate functions have both URI and URN in proto."""
    content = """%YAML 1.2
---
urn: extension:test:aggregate
aggregate_functions:
  - name: "sum"
    description: ""
    impls:
      - args:
          - value: i64
        nullability: DECLARED_OUTPUT
        decomposable: MANY
        intermediate: i64
        return: i64
"""
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(
        yaml.safe_load(content), uri="https://test.example.com/aggregate.yaml"
    )

    struct = stt.Type.Struct(types=[i64(nullable=False), i64(nullable=False)])
    named_struct = stt.NamedStruct(names=["id", "value"], struct=struct)

    table = read_named_table("table", named_struct)
    sum_expr = aggregate_function(
        "extension:test:aggregate", "sum", expressions=[column("value")], alias=["sum"]
    )

    actual = aggregate(table, grouping_expressions=[column("id")], measures=[sum_expr])(
        registry
    )

    ns = infer_plan_schema(table(None))

    expected = stp.Plan(
        version=default_version,
        extension_urns=[
            ste.SimpleExtensionURN(
                extension_urn_anchor=1, urn="extension:test:aggregate"
            )
        ],
        extension_uris=[
            ste.SimpleExtensionURI(
                extension_uri_anchor=1, uri="https://test.example.com/aggregate.yaml"
            )
        ],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_urn_reference=1,
                    extension_uri_reference=1,
                    function_anchor=1,
                    name="sum:i64",
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
                                column("id")(ns, registry).referred_expr[0].expression
                            ],
                            groupings=[
                                stalg.AggregateRel.Grouping(
                                    grouping_expressions=[
                                        column("id")(ns, registry)
                                        .referred_expr[0]
                                        .expression
                                    ],
                                    expression_references=[0],
                                )
                            ],
                            measures=[
                                stalg.AggregateRel.Measure(
                                    measure=sum_expr(ns, registry)
                                    .referred_expr[0]
                                    .measure
                                )
                            ],
                        )
                    ),
                    names=["id", "sum"],
                )
            )
        ],
    )

    assert actual == expected
