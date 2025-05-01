import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
from substrait.builders.extended_expression import column

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

nested_struct = stt.Type.Struct(
    types=[
        stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
        stt.Type(
            struct=stt.Type.Struct(
                types=[
                    stt.Type(
                        i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)
                    ),
                    stt.Type(
                        fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)
                    ),
                ],
                nullability=stt.Type.NULLABILITY_NULLABLE,
            )
        ),
        stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ]
)

nested_named_struct = stt.NamedStruct(
    names=["order_id", "shop_details", "shop_id", "shop_total", "order_total"],
    struct=nested_struct,
)


def test_column_no_nesting():
    assert column("description")(named_struct, None) == stee.ExtendedExpression(
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    selection=stalg.Expression.FieldReference(
                        root_reference=stalg.Expression.FieldReference.RootReference(),
                        direct_reference=stalg.Expression.ReferenceSegment(
                            struct_field=stalg.Expression.ReferenceSegment.StructField(
                                field=1
                            )
                        ),
                    )
                ),
                output_names=["description"],
            )
        ],
        base_schema=named_struct,
    )


def test_column_nesting():
    assert column("order_total")(nested_named_struct, None) == stee.ExtendedExpression(
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    selection=stalg.Expression.FieldReference(
                        root_reference=stalg.Expression.FieldReference.RootReference(),
                        direct_reference=stalg.Expression.ReferenceSegment(
                            struct_field=stalg.Expression.ReferenceSegment.StructField(
                                field=2
                            )
                        ),
                    )
                ),
                output_names=["order_total"],
            )
        ],
        base_schema=nested_named_struct,
    )


def test_column_nested_struct():
    assert column("shop_details")(nested_named_struct, None) == stee.ExtendedExpression(
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    selection=stalg.Expression.FieldReference(
                        root_reference=stalg.Expression.FieldReference.RootReference(),
                        direct_reference=stalg.Expression.ReferenceSegment(
                            struct_field=stalg.Expression.ReferenceSegment.StructField(
                                field=1
                            )
                        ),
                    )
                ),
                output_names=["shop_details", "shop_id", "shop_total"],
            )
        ],
        base_schema=nested_named_struct,
    )
