import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
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
                output_names=["cast"],
            )
        ],
        base_schema=named_struct,
    )

    assert e == expected
