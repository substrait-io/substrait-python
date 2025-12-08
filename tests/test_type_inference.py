import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
from substrait.type_inference import (
    infer_expression_type,
    infer_nested_type,
    infer_rel_schema,
)

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

read_rel = stalg.Rel(
    read=stalg.ReadRel(
        base_schema=named_struct, named_table=stalg.ReadRel.NamedTable(names=["table"])
    )
)

right_struct = stt.Type.Struct(
    types=[
        stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
        stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ]
)

right_named_struct = stt.NamedStruct(
    names=["order_id", "is_refundable"], struct=right_struct
)

right_read_rel = stalg.Rel(
    read=stalg.ReadRel(
        base_schema=right_named_struct,
        named_table=stalg.ReadRel.NamedTable(names=["table2"]),
    )
)


def test_inference_read_named_table():
    assert infer_rel_schema(read_rel) == struct


def test_inference_project_emit():
    rel = stalg.Rel(
        project=stalg.ProjectRel(
            input=read_rel,
            common=stalg.RelCommon(emit=stalg.RelCommon.Emit(output_mapping=[0, 2])),
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
        ]
    )

    assert infer_rel_schema(rel) == expected


def test_inference_project_literal():
    rel = stalg.Rel(
        project=stalg.ProjectRel(
            input=read_rel,
            expressions=[
                stalg.Expression(
                    literal=stalg.Expression.Literal(boolean=True, nullable=False)
                )
            ],
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)),
        ]
    )

    assert infer_rel_schema(rel) == expected


def test_inference_project_scalar_function():
    rel = stalg.Rel(
        project=stalg.ProjectRel(
            input=read_rel,
            expressions=[
                stalg.Expression(
                    scalar_function=stalg.Expression.ScalarFunction(
                        function_reference=0,
                        output_type=stt.Type(
                            bool=stt.Type.Boolean(
                                nullability=stt.Type.NULLABILITY_REQUIRED
                            )
                        ),
                    )
                )
            ],
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)),
        ]
    )

    assert infer_rel_schema(rel) == expected


def test_inference_aggregate():
    rel = stalg.Rel(
        aggregate=stalg.AggregateRel(
            input=read_rel,
            grouping_expressions=[
                stalg.Expression(
                    selection=stalg.Expression.FieldReference(
                        root_reference=stalg.Expression.FieldReference.RootReference(),
                        direct_reference=stalg.Expression.ReferenceSegment(
                            struct_field=stalg.Expression.ReferenceSegment.StructField(
                                field=1,
                            ),
                        ),
                    )
                )
            ],
            groupings=[stalg.AggregateRel.Grouping(expression_references=[0])],
            measures=[
                stalg.AggregateRel.Measure(
                    measure=stalg.AggregateFunction(
                        function_reference=0,
                        output_type=stt.Type(
                            bool=stt.Type.Boolean(
                                nullability=stt.Type.NULLABILITY_REQUIRED
                            )
                        ),
                    )
                )
            ],
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)),
        ]
    )

    assert infer_rel_schema(rel) == expected


def test_inference_aggregate_multiple_groupings():
    rel = stalg.Rel(
        aggregate=stalg.AggregateRel(
            input=read_rel,
            grouping_expressions=[
                stalg.Expression(
                    selection=stalg.Expression.FieldReference(
                        root_reference=stalg.Expression.FieldReference.RootReference(),
                        direct_reference=stalg.Expression.ReferenceSegment(
                            struct_field=stalg.Expression.ReferenceSegment.StructField(
                                field=1,
                            ),
                        ),
                    )
                )
            ],
            groupings=[
                stalg.AggregateRel.Grouping(expression_references=[]),
                stalg.AggregateRel.Grouping(expression_references=[0]),
            ],
            measures=[
                stalg.AggregateRel.Measure(
                    measure=stalg.AggregateFunction(
                        function_reference=0,
                        output_type=stt.Type(
                            bool=stt.Type.Boolean(
                                nullability=stt.Type.NULLABILITY_REQUIRED
                            )
                        ),
                    )
                )
            ],
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(i32=stt.Type.I32(nullability=stt.Type.NULLABILITY_REQUIRED)),
        ]
    )

    assert infer_rel_schema(rel) == expected


def test_inference_cross():
    rel = stalg.Rel(cross=stalg.CrossRel(left=read_rel, right=right_read_rel))

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)),
        ],
        nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
    )

    assert infer_rel_schema(rel) == expected


def test_inference_join_inner():
    rel = stalg.Rel(
        join=stalg.JoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JOIN_TYPE_INNER,
            expression=None,
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)),
        ],
        nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
    )

    assert infer_rel_schema(rel) == expected


def test_inference_join_left_anti():
    rel = stalg.Rel(
        join=stalg.JoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JOIN_TYPE_LEFT_ANTI,
            expression=None,
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
        ],
        nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
    )

    assert infer_rel_schema(rel) == expected


def test_inference_join_right_anti():
    rel = stalg.Rel(
        join=stalg.JoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JOIN_TYPE_RIGHT_ANTI,
            expression=None,
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)),
        ],
        nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
    )

    assert infer_rel_schema(rel) == expected


def test_inference_join_left_mark():
    rel = stalg.Rel(
        join=stalg.JoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JOIN_TYPE_LEFT_MARK,
            expression=None,
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)),
        ],
        nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
    )

    assert infer_rel_schema(rel) == expected


def test_infer_expression_type_literal():
    """Test infer_expression_type with a literal expression."""
    expr = stalg.Expression(literal=stalg.Expression.Literal(i64=42, nullable=False))

    result = infer_expression_type(expr, struct)

    expected = stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED))
    assert result == expected


def test_infer_expression_type_selection():
    """Test infer_expression_type with a field selection expression."""
    expr = stalg.Expression(
        selection=stalg.Expression.FieldReference(
            root_reference=stalg.Expression.FieldReference.RootReference(),
            direct_reference=stalg.Expression.ReferenceSegment(
                struct_field=stalg.Expression.ReferenceSegment.StructField(field=0),
            ),
        )
    )

    result = infer_expression_type(expr, struct)

    # Should return the type of field 0 from the struct (i64)
    expected = stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED))
    assert result == expected


def test_infer_expression_type_window_function():
    """Test infer_expression_type with a window function expression."""
    expr = stalg.Expression(
        window_function=stalg.Expression.WindowFunction(
            function_reference=0,
            output_type=stt.Type(
                i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_NULLABLE)
            ),
        )
    )

    result = infer_expression_type(expr, struct)

    expected = stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_NULLABLE))
    assert result == expected


def test_infer_nested_type_struct():
    """Test infer_nested_type with a struct nested expression."""
    expr = stalg.Expression(
        nested=stalg.Expression.Nested(
            struct=stalg.Expression.Nested.Struct(
                fields=[
                    stalg.Expression(
                        literal=stalg.Expression.Literal(i32=1, nullable=False)
                    ),
                    stalg.Expression(
                        literal=stalg.Expression.Literal(string="test", nullable=True)
                    ),
                ]
            ),
            nullable=False,
        )
    )

    result = infer_nested_type(expr.nested, struct)

    expected = stt.Type(
        struct=stt.Type.Struct(
            types=[
                stt.Type(i32=stt.Type.I32(nullability=stt.Type.NULLABILITY_REQUIRED)),
                stt.Type(
                    string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)
                ),
            ],
            nullability=stt.Type.NULLABILITY_REQUIRED,
        )
    )
    assert result == expected


def test_infer_nested_type_list():
    """Test infer_nested_type with a list nested expression."""
    expr = stalg.Expression(
        nested=stalg.Expression.Nested(
            list=stalg.Expression.Nested.List(
                values=[
                    stalg.Expression(
                        literal=stalg.Expression.Literal(fp32=3.14, nullable=False)
                    ),
                ]
            ),
            nullable=False,
        )
    )

    result = infer_nested_type(expr.nested, struct)

    expected = stt.Type(
        list=stt.Type.List(
            type=stt.Type(
                fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_REQUIRED)
            ),
            nullability=stt.Type.NULLABILITY_REQUIRED,
        )
    )
    assert result == expected


def test_infer_nested_type_map():
    """Test infer_nested_type with a map nested expression."""
    expr = stalg.Expression(
        nested=stalg.Expression.Nested(
            map=stalg.Expression.Nested.Map(
                key_values=[
                    stalg.Expression.Nested.Map.KeyValue(
                        key=stalg.Expression(
                            literal=stalg.Expression.Literal(
                                string="key", nullable=False
                            )
                        ),
                        value=stalg.Expression(
                            literal=stalg.Expression.Literal(i32=42, nullable=False)
                        ),
                    ),
                ]
            ),
            nullable=False,
        )
    )

    result = infer_nested_type(expr.nested, struct)

    expected = stt.Type(
        map=stt.Type.Map(
            key=stt.Type(
                string=stt.Type.String(nullability=stt.Type.NULLABILITY_REQUIRED)
            ),
            value=stt.Type(i32=stt.Type.I32(nullability=stt.Type.NULLABILITY_REQUIRED)),
            nullability=stt.Type.NULLABILITY_REQUIRED,
        )
    )
    assert result == expected
