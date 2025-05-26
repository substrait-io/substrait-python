import yaml

import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.builders.extended_expression import scalar_function, literal
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
scalar_functions:
  - name: "test_func"
    description: ""
    impls:
      - args:
          - value: i8
        variadic:
          min: 2
        return: i8
  - name: "is_positive"
    description: ""
    impls:
      - args:
          - value: i8
        return: boolean
"""


registry = ExtensionRegistry(load_default_extensions=False)
registry.register_extension_dict(yaml.safe_load(content), uri="test_uri")


def test_sclar_add():
    e = scalar_function(
        "test_uri",
        "test_func",
        expressions=[
            literal(
                10,
                type=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
            ),
            literal(
                20,
                type=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
            ),
        ],
    )(named_struct, registry)

    expected = stee.ExtendedExpression(
        extension_uris=[ste.SimpleExtensionURI(extension_uri_anchor=1, uri="test_uri")],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=1, function_anchor=1, name="test_func"
                )
            )
        ],
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    scalar_function=stalg.Expression.ScalarFunction(
                        function_reference=1,
                        arguments=[
                            stalg.FunctionArgument(
                                value=stalg.Expression(
                                    literal=stalg.Expression.Literal(
                                        i8=10, nullable=False
                                    )
                                )
                            ),
                            stalg.FunctionArgument(
                                value=stalg.Expression(
                                    literal=stalg.Expression.Literal(
                                        i8=20, nullable=False
                                    )
                                )
                            ),
                        ],
                        output_type=stt.Type(
                            i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                        ),
                    )
                ),
                output_names=["test_func(Literal(10),Literal(20))"],
            )
        ],
        base_schema=named_struct,
    )

    assert e == expected


def test_nested_scalar_calls():
    e = scalar_function(
        "test_uri",
        "is_positive",
        expressions=[
            scalar_function(
                "test_uri",
                "test_func",
                expressions=[
                    literal(
                        10,
                        type=stt.Type(
                            i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                        ),
                    ),
                    literal(
                        20,
                        type=stt.Type(
                            i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                        ),
                    ),
                ],
            )
        ],
        alias="positive",
    )(named_struct, registry)

    expected = stee.ExtendedExpression(
        extension_uris=[ste.SimpleExtensionURI(extension_uri_anchor=1, uri="test_uri")],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=1, function_anchor=2, name="is_positive"
                )
            ),
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=1, function_anchor=1, name="test_func"
                )
            ),
        ],
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    scalar_function=stalg.Expression.ScalarFunction(
                        function_reference=2,
                        arguments=[
                            stalg.FunctionArgument(
                                value=stalg.Expression(
                                    scalar_function=stalg.Expression.ScalarFunction(
                                        function_reference=1,
                                        arguments=[
                                            stalg.FunctionArgument(
                                                value=stalg.Expression(
                                                    literal=stalg.Expression.Literal(
                                                        i8=10, nullable=False
                                                    )
                                                )
                                            ),
                                            stalg.FunctionArgument(
                                                value=stalg.Expression(
                                                    literal=stalg.Expression.Literal(
                                                        i8=20, nullable=False
                                                    )
                                                )
                                            ),
                                        ],
                                        output_type=stt.Type(
                                            i8=stt.Type.I8(
                                                nullability=stt.Type.NULLABILITY_REQUIRED
                                            )
                                        ),
                                    )
                                )
                            )
                        ],
                        output_type=stt.Type(
                            bool=stt.Type.Boolean(
                                nullability=stt.Type.NULLABILITY_REQUIRED
                            )
                        ),
                    )
                ),
                output_names=["positive"],
            )
        ],
        base_schema=named_struct,
    )

    assert e == expected
