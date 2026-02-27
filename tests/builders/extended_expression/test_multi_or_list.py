import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import literal, multi_or_list
from substrait.builders.type import i8
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


def test_singular_or_list():
    e = multi_or_list(
        value=[literal(1, i8()), literal(2, i8())],
        options=[
            [literal(1, i8()), literal(2, i8())],
            [literal(3, i8()), literal(4, i8())],
        ],
    )(named_struct, registry)

    expected = stee.ExtendedExpression(
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    multi_or_list=stalg.Expression.MultiOrList(
                        value=[
                            stalg.Expression(
                                literal=stalg.Expression.Literal(i8=1, nullable=True)
                            ),
                            stalg.Expression(
                                literal=stalg.Expression.Literal(i8=2, nullable=True)
                            ),
                        ],
                        options=[
                            stalg.Expression.MultiOrList.Record(
                                fields=[
                                    stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=1, nullable=True
                                        )
                                    ),
                                    stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=2, nullable=True
                                        )
                                    ),
                                ]
                            ),
                            stalg.Expression.MultiOrList.Record(
                                fields=[
                                    stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=3, nullable=True
                                        )
                                    ),
                                    stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=4, nullable=True
                                        )
                                    ),
                                ]
                            ),
                        ],
                    )
                ),
                output_names=["multi_or_list"],
            )
        ],
        base_schema=named_struct,
    )

    assert e == expected


def test_multi_or_list_with_extension():
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

    actual = multi_or_list(
        value=[
            scalar_function(
                "extension:test:functions:add",
                expressions=[literal(1, i8()), literal(2, i8())],
            ),
            literal(10, i8()),
        ],
        options=[
            [literal(3, i8()), literal(11, i8())],
            [literal(4, i8()), literal(12, i8())],
        ],
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
                    multi_or_list=stalg.Expression.MultiOrList(
                        value=[
                            stalg.Expression(
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
                            stalg.Expression(
                                literal=stalg.Expression.Literal(i8=10, nullable=True)
                            ),
                        ],
                        options=[
                            stalg.Expression.MultiOrList.Record(
                                fields=[
                                    stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=3, nullable=True
                                        )
                                    ),
                                    stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=11, nullable=True
                                        )
                                    ),
                                ]
                            ),
                            stalg.Expression.MultiOrList.Record(
                                fields=[
                                    stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=4, nullable=True
                                        )
                                    ),
                                    stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=12, nullable=True
                                        )
                                    ),
                                ]
                            ),
                        ],
                    )
                ),
                output_names=["multi_or_list"],
            )
        ],
        base_schema=named_struct,
    )

    assert actual == expected
