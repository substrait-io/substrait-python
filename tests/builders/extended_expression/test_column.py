import pytest
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


def test_column_alias_over_a_nested_struct_keeps_member_names():
    # A single alias renames the struct column itself; its members keep their names
    # so the output still carries one name per field in depth-first order.
    aliased = column("shop_details", alias="shop")(nested_named_struct, None)

    assert list(aliased.referred_expr[0].output_names) == [
        "shop",
        "shop_id",
        "shop_total",
    ]


def test_column_alias_list_replaces_all_names():
    aliased = column("shop_details", alias=["shop", "id", "total"])(
        nested_named_struct, None
    )

    assert list(aliased.referred_expr[0].output_names) == ["shop", "id", "total"]


@pytest.mark.parametrize(
    "field, alias",
    [
        ("order_id", ["x", "y"]),
        ("shop_details", ["shop", "id"]),
    ],
)
def test_column_alias_list_must_name_every_field(field, alias):
    # A list alias replaces the depth-first names wholesale, so a wrong length would
    # give the output schema more or fewer names than it has fields.
    with pytest.raises(ValueError, match="needs"):
        column(field, alias=alias)(nested_named_struct, None)


def test_column_empty_alias_keeps_schema_name():
    aliased = column("order_id", alias="")(named_struct, None)

    assert list(aliased.referred_expr[0].output_names) == ["order_id"]


@pytest.mark.parametrize("name", ["missing", "shop_id"])
def test_column_unknown_name_raises(name):
    # A name that is absent, or only names a nested field, is not a top-level column.
    with pytest.raises(
        ValueError,
        match=rf"column '{name}' not found; available columns: "
        r"\['order_id', 'shop_details', 'order_total'\]",
    ):
        column(name)(nested_named_struct, None)


def test_column_unknown_name_on_empty_schema_raises():
    empty = stt.NamedStruct(names=[], struct=stt.Type.Struct(types=[]))
    with pytest.raises(ValueError, match=r"column 'x' not found"):
        column("x")(empty, None)


def test_column_by_name_after_a_map_column():
    map_named_struct = stt.NamedStruct(
        names=["a", "m", "b"],
        struct=stt.Type.Struct(
            types=[
                stt.Type(i64=stt.Type.I64()),
                stt.Type(
                    map=stt.Type.Map(
                        key=stt.Type(string=stt.Type.String()),
                        value=stt.Type(i64=stt.Type.I64()),
                    )
                ),
                stt.Type(i64=stt.Type.I64()),
            ]
        ),
    )
    for index, name in enumerate(["a", "m", "b"]):
        resolved = column(name)(map_named_struct, None).referred_expr[0]
        assert (
            resolved.expression.selection.direct_reference.struct_field.field == index
        )
        assert list(resolved.output_names) == [name]


@pytest.mark.parametrize("index", [-1, 3, True])
def test_column_by_ordinal_out_of_range_raises(index):
    with pytest.raises(ValueError, match=r"out of range; schema has 3 columns"):
        column(index)(named_struct, None)


def test_column_alias_list_on_a_field_without_names_raises_value_error():
    # A schema can carry fewer names than fields; the error must still be reported.
    unnamed = stt.NamedStruct(names=["order_id"], struct=struct)

    with pytest.raises(ValueError, match="2 needs 0"):
        column(2, alias=["g", "h"])(unnamed, None)
