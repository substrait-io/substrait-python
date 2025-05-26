import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
from substrait.builders.extended_expression import if_then, literal


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


def test_if_else():
    actual = if_then(
        ifs=[
            (
                literal(
                    True,
                    type=stt.Type(
                        bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)
                    ),
                ),
                literal(
                    10,
                    type=stt.Type(
                        i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                    ),
                ),
            )
        ],
        _else=literal(
            20, type=stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED))
        ),
    )(named_struct, None)

    expected = stee.ExtendedExpression(
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    if_then=stalg.Expression.IfThen(
                        **{
                            "ifs": [
                                stalg.Expression.IfThen.IfClause(
                                    **{
                                        "if": stalg.Expression(
                                            literal=stalg.Expression.Literal(
                                                boolean=True, nullable=False
                                            )
                                        ),
                                        "then": stalg.Expression(
                                            literal=stalg.Expression.Literal(
                                                i8=10, nullable=False
                                            )
                                        ),
                                    }
                                )
                            ],
                            "else": stalg.Expression(
                                literal=stalg.Expression.Literal(i8=20, nullable=False)
                            ),
                        }
                    )
                ),
                output_names=["IfThen(Literal(True),Literal(10),Literal(20))"],
            )
        ],
        base_schema=named_struct,
    )

    assert actual == expected
