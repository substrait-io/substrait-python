import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import cast, literal
from substrait.builders.type import i8, i16
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

registry = ExtensionRegistry(load_default_extensions=False)


def test_cast():
    e = cast(input=literal(3, i8()), type=i16())(named_struct, registry)

    expected = stee.ExtendedExpression(
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    cast=stalg.Expression.Cast(
                        type=stt.Type(
                            i16=stt.Type.I16(nullability=stt.Type.NULLABILITY_NULLABLE)
                        ),
                        input=stalg.Expression(
                            literal=stalg.Expression.Literal(i8=3, nullable=True)
                        ),
                        failure_behavior=stalg.Expression.Cast.FAILURE_BEHAVIOR_RETURN_NULL,
                    )
                ),
                output_names=["cast(Literal(3))"],
            )
        ],
        base_schema=named_struct,
    )

    assert e == expected


def test_cast_with_extension():
    import substrait.extensions.extensions_pb2 as ste
    import yaml

    from substrait.builders.extended_expression import scalar_function

    registry_with_ext = ExtensionRegistry(load_default_extensions=False)
    content = """%YAML 1.2
---
urn: extension:test:functions
scalar_functions:
  - name: "add"
    description: ""
    impls:
      - args:
          - value: i8
          - value: i8
        return: i8
"""
    registry_with_ext.register_extension_dict(
        yaml.safe_load(content), uri="https://test.example.com/functions.yaml"
    )

    actual = cast(
        input=scalar_function(
            "extension:test:functions",
            "add",
            expressions=[literal(1, i8()), literal(2, i8())],
        ),
        type=i16(),
    )(named_struct, registry_with_ext)

    expected = stee.ExtendedExpression(
        extension_uris=[
            ste.SimpleExtensionURI(
                extension_uri_anchor=1, uri="https://test.example.com/functions.yaml"
            )
        ],
        extension_urns=[
            ste.SimpleExtensionURN(
                extension_urn_anchor=1, urn="extension:test:functions"
            )
        ],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=1,
                    extension_urn_reference=1,
                    function_anchor=1,
                    name="add:i8_i8",
                )
            )
        ],
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    cast=stalg.Expression.Cast(
                        type=stt.Type(
                            i16=stt.Type.I16(nullability=stt.Type.NULLABILITY_NULLABLE)
                        ),
                        input=stalg.Expression(
                            scalar_function=stalg.Expression.ScalarFunction(
                                function_reference=1,
                                output_type=stt.Type(
                                    i8=stt.Type.I8(
                                        nullability=stt.Type.NULLABILITY_NULLABLE
                                    )
                                ),
                                arguments=[
                                    stalg.FunctionArgument(
                                        value=stalg.Expression(
                                            literal=stalg.Expression.Literal(
                                                i8=1, nullable=True
                                            )
                                        )
                                    ),
                                    stalg.FunctionArgument(
                                        value=stalg.Expression(
                                            literal=stalg.Expression.Literal(
                                                i8=2, nullable=True
                                            )
                                        )
                                    ),
                                ],
                            )
                        ),
                        failure_behavior=stalg.Expression.Cast.FAILURE_BEHAVIOR_RETURN_NULL,
                    )
                ),
                output_names=["cast(add(Literal(1),Literal(2)))"],
            )
        ],
        base_schema=named_struct,
    )

    assert actual == expected
