import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
from substrait.builders.extended_expression import singular_or_list, literal
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
    e = singular_or_list(
        value=literal(3, i8()), options=[literal(1, i8()), literal(2, i8())]
    )(named_struct, registry)

    expected = stee.ExtendedExpression(
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    singular_or_list=stalg.Expression.SingularOrList(
                        value=stalg.Expression(
                            literal=stalg.Expression.Literal(i8=3, nullable=True)
                        ),
                        options=[
                            stalg.Expression(
                                literal=stalg.Expression.Literal(i8=1, nullable=True)
                            ),
                            stalg.Expression(
                                literal=stalg.Expression.Literal(i8=2, nullable=True)
                            ),
                        ],
                    )
                ),
                output_names=["singular_or_list"],
            )
        ],
        base_schema=named_struct,
    )

    assert e == expected
