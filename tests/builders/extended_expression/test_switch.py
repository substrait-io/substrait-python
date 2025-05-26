import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
from substrait.builders.extended_expression import switch, literal
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


def test_switch():
    e = switch(
        match=literal(3, i8()),
        ifs=[
            (literal(1, i8()), literal(1, i8())),
            (literal(2, i8()), literal(4, i8())),
        ],
        _else=literal(9, i8()),
    )(named_struct, registry)

    expected = stee.ExtendedExpression(
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    switch_expression=stalg.Expression.SwitchExpression(
                        match=stalg.Expression(
                            literal=stalg.Expression.Literal(i8=3, nullable=True)
                        ),
                        ifs=[
                            stalg.Expression.SwitchExpression.IfValue(
                                **{
                                    "if": stalg.Expression.Literal(i8=1, nullable=True),
                                    "then": stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=1, nullable=True
                                        )
                                    ),
                                }
                            ),
                            stalg.Expression.SwitchExpression.IfValue(
                                **{
                                    "if": stalg.Expression.Literal(i8=2, nullable=True),
                                    "then": stalg.Expression(
                                        literal=stalg.Expression.Literal(
                                            i8=4, nullable=True
                                        )
                                    ),
                                }
                            ),
                        ],
                        **{
                            "else": stalg.Expression(
                                literal=stalg.Expression.Literal(i8=9, nullable=True)
                            )
                        },
                    )
                ),
                output_names=["switch"],
            )
        ],
        base_schema=named_struct,
    )

    assert e == expected
