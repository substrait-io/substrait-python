import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
from substrait.type_inference import infer_rel_schema


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
