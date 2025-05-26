import yaml

import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.builders.extended_expression import window_function
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
window_functions:
  - name: "row_number"
    description: "the number of the current row within its partition, starting at 1"
    impls:
      - args: []
        nullability: DECLARED_OUTPUT
        decomposable: NONE
        return: i64?
        window_type: PARTITION
  - name: "rank"
    description: "the rank of the current row, with gaps."
    impls:
      - args: []
        nullability: DECLARED_OUTPUT
        decomposable: NONE
        return: i64?
        window_type: PARTITION
"""


registry = ExtensionRegistry(load_default_extensions=False)
registry.register_extension_dict(yaml.safe_load(content), uri="test_uri")


def test_row_number():
    e = window_function("test_uri", "row_number", expressions=[], alias="rn")(
        named_struct, registry
    )

    expected = stee.ExtendedExpression(
        extension_uris=[ste.SimpleExtensionURI(extension_uri_anchor=1, uri="test_uri")],
        extensions=[
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_uri_reference=1, function_anchor=1, name="row_number"
                )
            )
        ],
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    window_function=stalg.Expression.WindowFunction(
                        function_reference=1,
                        output_type=stt.Type(
                            i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_NULLABLE)
                        ),
                    )
                ),
                output_names=["rn"],
            )
        ],
        base_schema=named_struct,
    )

    assert e == expected
