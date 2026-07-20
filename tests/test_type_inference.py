import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.type_inference import (
    infer_expression_type,
    infer_nested_type,
    infer_plan_schema,
    infer_rel_schema,
)

_REQ = stt.Type.NULLABILITY_REQUIRED
_NULL = stt.Type.NULLABILITY_NULLABLE

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


def test_inference_set_emit():
    # A SetRel's own RelCommon.Emit must drive the output schema; regression for
    # the branch reading rel.fetch.common instead of rel.set.common (issue #217).
    rel = stalg.Rel(
        set=stalg.SetRel(
            inputs=[read_rel, read_rel],
            op=stalg.SetRel.SET_OP_UNION_ALL,
            common=stalg.RelCommon(emit=stalg.RelCommon.Emit(output_mapping=[2, 0])),
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
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


def test_inference_lateral_join_inner():
    # A lateral join emits the same columns as the equivalent JoinRel; only the
    # right input's evaluation semantics differ.
    rel = stalg.Rel(
        lateral_join=stalg.LateralJoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JOIN_TYPE_INNER,
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


def test_inference_lateral_join_left_semi():
    # Left-oriented semi/anti joins drop the right side, just like JoinRel.
    rel = stalg.Rel(
        lateral_join=stalg.LateralJoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JOIN_TYPE_LEFT_SEMI,
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


def test_inference_lateral_join_left_mark():
    # Left-mark joins append a nullable boolean marker column.
    rel = stalg.Rel(
        lateral_join=stalg.LateralJoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JOIN_TYPE_LEFT_MARK,
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


def _outer_rel_reference(anchor: int, field: int) -> stalg.Expression:
    """An OuterReference resolved by id: rel_reference -> the given rel_anchor,
    selecting the struct field at ``field``."""
    return stalg.Expression(
        selection=stalg.Expression.FieldReference(
            outer_reference=stalg.Expression.FieldReference.OuterReference(
                rel_reference=anchor
            ),
            direct_reference=stalg.Expression.ReferenceSegment(
                struct_field=stalg.Expression.ReferenceSegment.StructField(field=field)
            ),
        )
    )


def test_inference_lateral_join_correlated_rel_reference():
    # The right (dependent) input references the current left row via an
    # OuterReference.rel_reference pointing to the lateral join's rel_anchor.
    # Inference must resolve that against the left schema registered under the
    # anchor. Here the right input projects the left's first column (i64) on top
    # of its own columns.
    anchor = 7
    correlated_right = stalg.Rel(
        project=stalg.ProjectRel(
            input=right_read_rel,
            expressions=[_outer_rel_reference(anchor, 0)],
        )
    )
    rel = stalg.Rel(
        lateral_join=stalg.LateralJoinRel(
            common=stalg.RelCommon(rel_anchor=anchor),
            left=read_rel,
            right=correlated_right,
            type=stalg.JoinRel.JOIN_TYPE_INNER,
        )
    )

    expected = stt.Type.Struct(
        types=[
            # left columns
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
            stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
            # right columns
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
            stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)),
            # right's projected OuterReference to the left's first column (i64)
            stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
        ],
        nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
    )

    assert infer_rel_schema(rel) == expected


def test_inference_lateral_join_unknown_rel_anchor_raises():
    # A rel_reference that does not match the (only) enclosing lateral join's
    # rel_anchor cannot be resolved.
    correlated_right = stalg.Rel(
        project=stalg.ProjectRel(
            input=right_read_rel,
            expressions=[_outer_rel_reference(99, 0)],
        )
    )
    rel = stalg.Rel(
        lateral_join=stalg.LateralJoinRel(
            common=stalg.RelCommon(rel_anchor=7),
            left=read_rel,
            right=correlated_right,
            type=stalg.JoinRel.JOIN_TYPE_INNER,
        )
    )

    with pytest.raises(Exception, match="unknown rel_anchor 99"):
        infer_rel_schema(rel)


def test_infer_expression_type_rel_reference_resolves_against_anchor():
    # infer_expression_type resolves an id-based OuterReference against the schema
    # bound to the matching rel_anchor in the current anchor scope.
    from substrait.type_inference import _outer_anchor_binding

    # rel_anchor 5 -> `struct` ([i64, string, fp32]); field 1 is the string.
    with _outer_anchor_binding(5, struct):
        result = infer_expression_type(_outer_rel_reference(5, 1), right_struct)

    assert result == stt.Type(
        string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)
    )


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


# Three set inputs, one i64 column per (required/nullable) combination across
# them, matching the worked example in the Substrait spec's set-operation
# "Output Type Derivation" table (issue #219). Columns, per (primary, s1, s2):
#   RRR  RRN  RNR  RNN  NRR  NRN  NNR  NNN
_SET_INPUT_NULLABILITIES = [
    [_REQ, _REQ, _REQ, _REQ, _NULL, _NULL, _NULL, _NULL],  # primary
    [_REQ, _REQ, _NULL, _NULL, _REQ, _REQ, _NULL, _NULL],  # secondary
    [_REQ, _NULL, _REQ, _NULL, _REQ, _NULL, _REQ, _NULL],  # secondary
]


@pytest.mark.parametrize(
    ("op", "expected"),
    [
        # MINUS variants inherit the primary input's nullability.
        (
            stalg.SetRel.SET_OP_MINUS_PRIMARY,
            [_REQ, _REQ, _REQ, _REQ, _NULL, _NULL, _NULL, _NULL],
        ),
        (
            stalg.SetRel.SET_OP_MINUS_PRIMARY_ALL,
            [_REQ, _REQ, _REQ, _REQ, _NULL, _NULL, _NULL, _NULL],
        ),
        (
            stalg.SetRel.SET_OP_MINUS_MULTISET,
            [_REQ, _REQ, _REQ, _REQ, _NULL, _NULL, _NULL, _NULL],
        ),
        # Nullable only if nullable in the primary and some secondary.
        (
            stalg.SetRel.SET_OP_INTERSECTION_PRIMARY,
            [_REQ, _REQ, _REQ, _REQ, _REQ, _NULL, _NULL, _NULL],
        ),
        # Required if required in any input.
        (
            stalg.SetRel.SET_OP_INTERSECTION_MULTISET,
            [_REQ, _REQ, _REQ, _REQ, _REQ, _REQ, _REQ, _NULL],
        ),
        (
            stalg.SetRel.SET_OP_INTERSECTION_MULTISET_ALL,
            [_REQ, _REQ, _REQ, _REQ, _REQ, _REQ, _REQ, _NULL],
        ),
        # Nullable if nullable in any input.
        (
            stalg.SetRel.SET_OP_UNION_DISTINCT,
            [_REQ, _NULL, _NULL, _NULL, _NULL, _NULL, _NULL, _NULL],
        ),
        (
            stalg.SetRel.SET_OP_UNION_ALL,
            [_REQ, _NULL, _NULL, _NULL, _NULL, _NULL, _NULL, _NULL],
        ),
    ],
)
def test_inference_set_nullability(op, expected):
    inputs = [
        stalg.Rel(
            read=stalg.ReadRel(
                base_schema=stt.NamedStruct(
                    names=[f"c{i}" for i in range(len(nullabilities))],
                    struct=stt.Type.Struct(
                        types=[
                            stt.Type(i64=stt.Type.I64(nullability=n))
                            for n in nullabilities
                        ]
                    ),
                )
            )
        )
        for nullabilities in _SET_INPUT_NULLABILITIES
    ]

    rel = stalg.Rel(set=stalg.SetRel(inputs=inputs, op=op))

    result = [t.i64.nullability for t in infer_rel_schema(rel).types]
    assert result == expected


def test_inference_set_nullability_preserves_field_types():
    # Combining nullability must keep each field's full type (parameters and
    # nested element types) intact -- only the top-level nullability changes.
    def _struct(dec_null, vc_null, list_null):
        return stt.Type.Struct(
            types=[
                stt.Type(
                    decimal=stt.Type.Decimal(
                        precision=10, scale=2, nullability=dec_null
                    )
                ),
                stt.Type(varchar=stt.Type.VarChar(length=5, nullability=vc_null)),
                stt.Type(
                    list=stt.Type.List(
                        type=stt.Type(string=stt.Type.String(nullability=_REQ)),
                        nullability=list_null,
                    )
                ),
            ],
            nullability=_REQ,
        )

    def _read(struct):
        return stalg.Rel(
            read=stalg.ReadRel(
                base_schema=stt.NamedStruct(names=["d", "v", "l"], struct=struct)
            )
        )

    primary = _read(_struct(_NULL, _REQ, _REQ))
    secondary = _read(_struct(_REQ, _NULL, _NULL))
    rel = stalg.Rel(
        set=stalg.SetRel(inputs=[primary, secondary], op=stalg.SetRel.SET_OP_UNION_ALL)
    )

    # UNION -> nullable if nullable in any input; types (decimal 10/2, varchar 5,
    # list<string>) and the required inner string element are preserved.
    assert infer_rel_schema(rel) == _struct(_NULL, _NULL, _NULL)


def test_inference_reference_resolves_against_subtree():
    # A ReferenceRel's schema is the schema of the shared subtree its
    # subtree_ordinal indexes into, taken from the `subtrees` list.
    ref = stalg.Rel(reference=stalg.ReferenceRel(subtree_ordinal=1))
    assert infer_rel_schema(ref, subtrees=[right_read_rel, read_rel]) == struct


def test_inference_reference_through_wrapping_relation():
    # A reference nested under another relation resolves too (subtrees thread down).
    filt = stalg.Rel(
        filter=stalg.FilterRel(
            input=stalg.Rel(reference=stalg.ReferenceRel(subtree_ordinal=0))
        )
    )
    assert infer_rel_schema(filt, subtrees=[read_rel]) == struct


def test_inference_reference_out_of_range_raises():
    ref = stalg.Rel(reference=stalg.ReferenceRel(subtree_ordinal=3))
    with pytest.raises(Exception, match="out of range"):
        infer_rel_schema(ref, subtrees=[read_rel])
    # No subtrees in scope at all is also out of range.
    with pytest.raises(Exception, match="out of range"):
        infer_rel_schema(ref)


def _outer_ref(field, *, rel_reference=None, steps_out=None):
    outer = stalg.Expression.FieldReference.OuterReference()
    if rel_reference is not None:
        outer.rel_reference = rel_reference
    else:
        outer.steps_out = steps_out
    return stalg.Expression(
        selection=stalg.Expression.FieldReference(
            outer_reference=outer,
            direct_reference=stalg.Expression.ReferenceSegment(
                struct_field=stalg.Expression.ReferenceSegment.StructField(field=field)
            ),
        )
    )


def test_infer_rel_reference_resolves_against_anchored_subtree():
    # A rel_reference resolves against the output schema of whatever relation in the
    # plan carries the matching rel_anchor -- here a shared subtree -- which the
    # offset-based steps_out could not address. The project appends order_total
    # (field 2, fp32 nullable) pulled from the anchored subtree.
    anchored = stalg.Rel(
        read=stalg.ReadRel(
            base_schema=named_struct,
            common=stalg.RelCommon(rel_anchor=7),
            named_table=stalg.ReadRel.NamedTable(names=["shared"]),
        )
    )
    root_input = stalg.Rel(
        project=stalg.ProjectRel(
            input=right_read_rel,
            expressions=[_outer_ref(2, rel_reference=7)],
        )
    )
    plan = stp.Plan(
        relations=[
            stp.PlanRel(rel=anchored),
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=root_input,
                    names=["order_id", "is_refundable", "order_total"],
                )
            ),
        ]
    )

    expected = stt.Type.Struct(
        types=list(right_struct.types)
        + [stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE))]
    )
    assert infer_plan_schema(plan).struct == expected


def test_infer_rel_reference_unknown_anchor_raises():
    root_input = stalg.Rel(
        project=stalg.ProjectRel(
            input=right_read_rel, expressions=[_outer_ref(0, rel_reference=99)]
        )
    )
    plan = stp.Plan(
        relations=[
            stp.PlanRel(root=stalg.RelRoot(input=root_input, names=["a", "b", "c"]))
        ]
    )
    with pytest.raises(Exception, match="unknown rel_anchor 99"):
        infer_plan_schema(plan)


def test_infer_expression_rel_reference_without_plan_context_raises():
    # Resolving a rel_reference needs the plan-wide anchor index; a bare
    # infer_expression_type call (no infer_plan_schema) has no index in scope.
    with pytest.raises(Exception, match="whole-plan context"):
        infer_expression_type(_outer_ref(0, rel_reference=1), struct)


def test_infer_rel_reference_anchor_zero_is_a_distinct_anchor():
    # rel_anchor has explicit field presence, so 0 is a set, valid anchor distinct
    # from "absent". The anchor index must key on presence, not truthiness, or a
    # legitimate anchor 0 would be silently dropped. (The builder-side converter
    # never emits 0, but an externally-produced or #228 lateral-join plan can.)
    anchored = stalg.Rel(
        read=stalg.ReadRel(
            base_schema=named_struct,
            common=stalg.RelCommon(rel_anchor=0),
            named_table=stalg.ReadRel.NamedTable(names=["shared"]),
        )
    )
    root_input = stalg.Rel(
        project=stalg.ProjectRel(
            input=right_read_rel,
            expressions=[_outer_ref(2, rel_reference=0)],
        )
    )
    plan = stp.Plan(
        relations=[
            stp.PlanRel(rel=anchored),
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=root_input,
                    names=["order_id", "is_refundable", "order_total"],
                )
            ),
        ]
    )

    expected = stt.Type.Struct(
        types=list(right_struct.types)
        + [stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE))]
    )
    assert infer_plan_schema(plan).struct == expected
