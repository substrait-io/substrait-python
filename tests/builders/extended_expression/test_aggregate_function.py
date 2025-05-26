import yaml

import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.builders.extended_expression import aggregate_function, literal
from substrait.extension_registry import ExtensionRegistry

struct = stt.Type.Struct(
    types=[
        stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
        stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
        stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ]
)

named_struct = stt.NamedStruct(
    names=["order_id", "description", "order_total"], struct=struct
)

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


def test_aggregate_count():
    e = aggregate_function(
        "test_uri",
        "count",
        expressions=[
            literal(
                10,
                type=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
            )
        ],
        alias="count",
    )(named_struct, registry)

    expected = stee.ExtendedExpression(
        extension_uris=[ste.SimpleExtensionURI(extension_uri_anchor=1, uri="test_uri")],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=1, function_anchor=1, name="count"
                )
            )
        ],
        referred_expr=[
            stee.ExpressionReference(
                measure=stalg.AggregateFunction(
                    function_reference=1,
                    arguments=[
                        stalg.FunctionArgument(
                            value=stalg.Expression(
                                literal=stalg.Expression.Literal(i8=10, nullable=False)
                            )
                        ),
                    ],
                    output_type=stt.Type(
                        i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)
                    ),
                ),
                output_names=["count"],
            )
        ],
        base_schema=named_struct,
    )

    assert e == expected
