import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.type_pb2 as stt

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


def test_column_by_ordinal():
    # column() takes an index as well as a name, and the index is a top-level field
    # ordinal -- so the output name is read from the same slice of base_schema.names
    # that a lookup by name would have landed on.
    assert column(1)(named_struct, None) == column("description")(named_struct, None)


def test_column_by_ordinal_over_a_nested_struct():
    # A struct field consumes several entries of base_schema.names (its own plus one
    # per member), so the ordinal indexes top-level fields while the output names come
    # from the flattened list: field 1 is shop_details, carrying its two members.
    by_ordinal = column(1)(nested_named_struct, None)

    assert by_ordinal == column("shop_details")(nested_named_struct, None)
    assert list(by_ordinal.referred_expr[0].output_names) == [
        "shop_details",
        "shop_id",
        "shop_total",
    ]
