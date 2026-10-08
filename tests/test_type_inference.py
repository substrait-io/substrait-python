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


def _field_reference(field: int) -> stalg.Expression:
    return stalg.Expression(
        selection=stalg.Expression.FieldReference(
            root_reference=stalg.Expression.FieldReference.RootReference(),
            direct_reference=stalg.Expression.ReferenceSegment(
                struct_field=stalg.Expression.ReferenceSegment.StructField(field=field)
            ),
        )
    )


@pytest.mark.parametrize(
    "sets, expected",
    [
        ([[0, 1]], [("i64", _REQ), ("i64", _REQ)]),
        ([[0], [1]], [("i64", _NULL), ("i64", _NULL), ("i32", _REQ)]),
        ([[0, 1], [0]], [("i64", _REQ), ("i64", _NULL), ("i32", _REQ)]),
        ([[0, 1], [1]], [("i64", _NULL), ("i64", _REQ), ("i32", _REQ)]),
        ([[0, 1], []], [("i64", _NULL), ("i64", _NULL), ("i32", _REQ)]),
    ],
)
def test_inference_aggregate_grouping_key_absent_from_a_set(sets, expected):
    # A grouping key missing from any grouping set is null in that set's records,
    # so its column is nullable; a key in every set keeps its own nullability.
    # Both keys reference the REQUIRED field 0 so that a failure to widen is
    # observable at either position.
    rel = stalg.Rel(
        aggregate=stalg.AggregateRel(
            input=read_rel,
            grouping_expressions=[_field_reference(0), _field_reference(0)],
            groupings=[
                stalg.AggregateRel.Grouping(expression_references=s) for s in sets
            ],
        )
    )

    schema = infer_rel_schema(rel)

    assert [
        (t.WhichOneof("kind"), getattr(t, t.WhichOneof("kind")).nullability)
        for t in schema.types
    ] == expected


def test_inference_aggregate_grouping_reference_out_of_range():
    rel = stalg.Rel(
        aggregate=stalg.AggregateRel(
            input=read_rel,
            grouping_expressions=[_field_reference(0)],
            groupings=[
                stalg.AggregateRel.Grouping(expression_references=[0]),
                stalg.AggregateRel.Grouping(expression_references=[1]),
            ],
        )
    )

    with pytest.raises(ValueError, match="index 1 is out of range"):
        infer_rel_schema(rel)


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


@pytest.mark.parametrize(
    ("join_type", "left_nullability", "right_nullability"),
    [
        ("JOIN_TYPE_INNER", _REQ, _REQ),
        ("JOIN_TYPE_LEFT", _REQ, _NULL),
        ("JOIN_TYPE_LEFT_SINGLE", _REQ, _NULL),
        ("JOIN_TYPE_RIGHT", _NULL, _REQ),
        ("JOIN_TYPE_RIGHT_SINGLE", _NULL, _REQ),
        ("JOIN_TYPE_OUTER", _NULL, _NULL),
    ],
)
def test_inference_join_null_padded_side(
    join_type, left_nullability, right_nullability
):
    # The side a join fills with nulls for unmatched rows is nullable in the
    # output; the other side keeps what its input declared. Only the two i64
    # columns are required in the inputs, so they are the ones that move.
    rel = stalg.Rel(
        join=stalg.JoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JoinType.Value(join_type),
            expression=None,
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=left_nullability)),
            stt.Type(string=stt.Type.String(nullability=_NULL)),
            stt.Type(fp32=stt.Type.FP32(nullability=_NULL)),
            stt.Type(i64=stt.Type.I64(nullability=right_nullability)),
            stt.Type(bool=stt.Type.Boolean(nullability=_NULL)),
        ],
        nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
    )

    assert infer_rel_schema(rel) == expected


def test_inference_join_padding_leaves_inputs_alone():
    # Padding copies each field type, so the inputs still carry what they declare.
    rel = stalg.Rel(
        join=stalg.JoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JOIN_TYPE_OUTER,
            expression=None,
        )
    )

    infer_rel_schema(rel)

    assert infer_rel_schema(rel.join.left) == struct
    assert infer_rel_schema(rel.join.right) == right_struct


def test_inference_join_padding_leaves_an_unbound_field_alone():
    # An unbound field type carries no nullability, so padding leaves it as it is.
    unbound = stt.Type(unbound=stt.Type.Unbound())
    right = stalg.Rel(
        read=stalg.ReadRel(
            base_schema=stt.NamedStruct(
                names=["u"], struct=stt.Type.Struct(types=[unbound], nullability=_REQ)
            ),
            named_table=stalg.ReadRel.NamedTable(names=["unbound_table"]),
        )
    )
    rel = stalg.Rel(
        join=stalg.JoinRel(
            left=read_rel, right=right, type=stalg.JoinRel.JOIN_TYPE_LEFT
        )
    )

    assert list(infer_rel_schema(rel).types)[-1] == unbound


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


def test_inference_lateral_join_left_pads_right():
    # A lateral join pads like the JoinRel of the same type: a left join leaves
    # the right columns nullable even where the dependent input requires them.
    rel = stalg.Rel(
        lateral_join=stalg.LateralJoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JOIN_TYPE_LEFT,
        )
    )

    expected = stt.Type.Struct(
        types=[
            stt.Type(i64=stt.Type.I64(nullability=_REQ)),
            stt.Type(string=stt.Type.String(nullability=_NULL)),
            stt.Type(fp32=stt.Type.FP32(nullability=_NULL)),
            stt.Type(i64=stt.Type.I64(nullability=_NULL)),
            stt.Type(bool=stt.Type.Boolean(nullability=_NULL)),
        ],
        nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
    )

    assert infer_rel_schema(rel) == expected


@pytest.mark.parametrize(
    "join_type",
    [
        "JOIN_TYPE_RIGHT",
        "JOIN_TYPE_RIGHT_SINGLE",
        "JOIN_TYPE_OUTER",
        "JOIN_TYPE_RIGHT_SEMI",
        "JOIN_TYPE_RIGHT_ANTI",
        "JOIN_TYPE_RIGHT_MARK",
    ],
)
def test_inference_lateral_join_rejects_right_oriented_types(join_type):
    # A lateral join's left row always exists, so the spec allows only inner and
    # left-oriented types; inference refuses the rest instead of padding the left.
    rel = stalg.Rel(
        lateral_join=stalg.LateralJoinRel(
            left=read_rel,
            right=right_read_rel,
            type=stalg.JoinRel.JoinType.Value(join_type),
        )
    )

    with pytest.raises(ValueError, match=join_type):
        infer_rel_schema(rel)


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


def _lambda_ref(field=0, *, steps_out=0):
    return stalg.Expression(
        selection=stalg.Expression.FieldReference(
            lambda_parameter_reference=stalg.Expression.FieldReference.LambdaParameterReference(
                steps_out=steps_out
            ),
            direct_reference=stalg.Expression.ReferenceSegment(
                struct_field=stalg.Expression.ReferenceSegment.StructField(field=field)
            ),
        )
    )


def _lambda_expression(parameters, body, *, invoke=False, arguments=()):
    lam = stalg.Expression.Lambda(
        parameters=stt.Type.Struct(types=parameters, nullability=_REQ), body=body
    )
    if invoke:
        return stalg.Expression(
            lambda_invocation=stalg.Expression.LambdaInvocation(
                **{
                    "lambda": lam,
                    "arguments": stalg.Expression.Nested.Struct(fields=arguments),
                }
            )
        )
    return stalg.Expression(**{"lambda": lam})


@pytest.mark.parametrize("nullable", [False, True])
def test_infer_lambda_invocation_literal_body(nullable):
    body = stalg.Expression(literal=stalg.Expression.Literal(i32=7, nullable=nullable))
    expr = _lambda_expression([], body, invoke=True)

    assert infer_expression_type(expr, struct) == stt.Type(
        i32=stt.Type.I32(nullability=_NULL if nullable else _REQ)
    )


@pytest.mark.parametrize("argument_count", [0, 2])
def test_lambda_invocation_requires_one_argument_per_parameter(argument_count):
    expr = _lambda_expression(
        [struct.types[0]],
        _lambda_ref(),
        invoke=True,
        arguments=[_field_reference(0)] * argument_count,
    )
    with pytest.raises(Exception, match="one argument per lambda parameter"):
        infer_expression_type(expr, struct)


@pytest.mark.parametrize(
    "parameter_type, argument_type",
    [
        (struct.types[0], struct.types[1]),
        (struct.types[0], stt.Type(i64=stt.Type.I64(nullability=_NULL))),
        (
            stt.Type(decimal=stt.Type.Decimal(precision=10, scale=2, nullability=_REQ)),
            stt.Type(decimal=stt.Type.Decimal(precision=10, scale=3, nullability=_REQ)),
        ),
        (
            struct.types[0],
            stt.Type(i64=stt.Type.I64(nullability=_REQ, type_variation_reference=1)),
        ),
    ],
)
@pytest.mark.parametrize("argument_index", [0, 1])
@pytest.mark.parametrize("matches", [False, True])
def test_lambda_invocation_argument_types_must_match_parameters(
    parameter_type, argument_type, argument_index, matches
):
    argument_types = [parameter_type, parameter_type]
    if not matches:
        argument_types[argument_index] = argument_type
    expr = _lambda_expression(
        [parameter_type, parameter_type],
        _lambda_ref(),
        invoke=True,
        arguments=[_field_reference(0), _field_reference(1)],
    )
    row = stt.Type.Struct(types=argument_types, nullability=_REQ)
    if matches:
        assert infer_expression_type(expr, row) == parameter_type
    else:
        with pytest.raises(Exception, match="argument type must match parameter type"):
            infer_expression_type(expr, row)


@pytest.mark.parametrize("steps_out", [0, 1])
@pytest.mark.parametrize("argument_index", [0, 1])
def test_lambda_invocation_arguments_cannot_use_the_invoked_lambda_scope(
    steps_out, argument_index
):
    arguments = [_field_reference(0), _field_reference(0)]
    arguments[argument_index] = _lambda_ref(steps_out=steps_out)
    expr = _lambda_expression(
        [struct.types[0], struct.types[0]],
        _lambda_ref(),
        invoke=True,
        arguments=arguments,
    )
    with pytest.raises(Exception, match="outside an enclosing lambda scope"):
        infer_expression_type(expr, struct)


def test_nested_lambda_invocation_argument_uses_the_callers_scope():
    outer = struct.types[1]
    inner = _lambda_expression(
        [outer], _lambda_ref(), invoke=True, arguments=[_lambda_ref()]
    )
    expr = _lambda_expression([outer], inner)
    assert infer_expression_type(expr, struct).func.return_type == outer


@pytest.mark.parametrize("invoke", [False, True])
@pytest.mark.parametrize("reference", ["root", "parameter"])
def test_infer_lambda_keeps_row_and_parameter_scopes_distinct(invoke, reference):
    # Same field index, different types: a root reference captures the input row.
    row_type = stt.Type(string=stt.Type.String(nullability=_NULL))
    parameter = stt.Type(i64=stt.Type.I64(nullability=_REQ))
    body = _field_reference(0) if reference == "root" else _lambda_ref()
    expr = _lambda_expression(
        [parameter],
        body,
        invoke=invoke,
        arguments=[stalg.Expression(literal=stalg.Expression.Literal(i64=42))],
    )
    original = expr.SerializeToString()
    result = infer_expression_type(
        expr, stt.Type.Struct(types=[row_type], nullability=_REQ)
    )
    expected = row_type if reference == "root" else parameter

    if invoke:
        assert result == expected
    else:
        assert result == stt.Type(
            func=stt.Type.Func(
                parameter_types=[parameter], return_type=expected, nullability=_REQ
            )
        )
    assert expr.SerializeToString() == original


@pytest.mark.parametrize("steps_out", [0, 1])
@pytest.mark.parametrize("invoke", [False, True])
def test_infer_nested_lambda_parameter_scopes(steps_out, invoke):
    outer = stt.Type(string=stt.Type.String(nullability=_NULL))
    inner = stt.Type(i64=stt.Type.I64(nullability=_REQ))
    inner_expr = _lambda_expression(
        [inner],
        _lambda_ref(steps_out=steps_out),
        invoke=invoke,
        arguments=[stalg.Expression(literal=stalg.Expression.Literal(i64=42))],
    )
    expr = _lambda_expression(
        [outer],
        inner_expr,
        invoke=invoke,
        arguments=[
            stalg.Expression(
                literal=stalg.Expression.Literal(string="x", nullable=True)
            )
        ],
    )
    result = infer_expression_type(expr, struct)
    expected = inner if steps_out == 0 else outer

    if invoke:
        assert result == expected
    else:
        assert result.func.return_type.func.return_type == expected


def test_lambda_parameter_reference_cannot_reach_a_missing_scope():
    parameter = stt.Type(i32=stt.Type.I32(nullability=_REQ))
    expr = _lambda_expression([parameter], _lambda_ref(steps_out=1))

    with pytest.raises(Exception, match="outside an enclosing lambda scope"):
        infer_expression_type(expr, struct)


@pytest.mark.parametrize("steps_out", [0, 1])
def test_standalone_lambda_parameter_reference_cannot_reach_a_missing_scope(steps_out):
    with pytest.raises(Exception, match="outside an enclosing lambda scope"):
        infer_expression_type(_lambda_ref(steps_out=steps_out), struct)


def test_project_lambda_parameter_reference_requires_a_lambda_scope():
    rel = stalg.Rel(
        project=stalg.ProjectRel(
            input=stalg.Rel(read=stalg.ReadRel(base_schema=named_struct)),
            expressions=[_lambda_ref()],
        )
    )
    with pytest.raises(Exception, match="outside an enclosing lambda scope"):
        infer_rel_schema(rel)


@pytest.mark.parametrize("fail", [False, True])
def test_lambda_parameter_scope_does_not_leak(fail):
    parameter = stt.Type(i32=stt.Type.I32(nullability=_REQ))
    supplied = stt.Type.Struct(
        types=[stt.Type(string=stt.Type.String(nullability=_NULL))], nullability=_REQ
    )
    body = _field_reference(99) if fail else _lambda_ref()
    expr = _lambda_expression([parameter], body)
    if fail:
        with pytest.raises(IndexError):
            infer_expression_type(expr, supplied)
    else:
        assert infer_expression_type(expr, supplied).func.return_type == parameter

    with pytest.raises(Exception, match="outside an enclosing lambda scope"):
        infer_expression_type(_lambda_ref(), supplied)


def _expand_switching(types, duplicates):
    inp = stalg.Rel(
        read=stalg.ReadRel(
            named_table=stalg.ReadRel.NamedTable(names=["t"]),
            base_schema=stt.NamedStruct(
                names=[f"c{i}" for i in range(len(types))],
                struct=stt.Type.Struct(types=types, nullability=_REQ),
            ),
        )
    )
    fields = [
        stalg.ExpandRel.ExpandField(
            switching_field=stalg.ExpandRel.SwitchingField(duplicates=duplicates)
        )
    ] + [
        stalg.ExpandRel.ExpandField(consistent_field=_field_reference(i))
        for i in range(1, len(types))
    ]
    return stalg.Rel(expand=stalg.ExpandRel(input=inp, fields=fields))


@pytest.mark.parametrize("nullable", [False, True])
def test_expand_switching_field_with_lambda_invocation(nullable):
    integer = stt.Type(i32=stt.Type.I32(nullability=_REQ))
    body = stalg.Expression(literal=stalg.Expression.Literal(i32=7, nullable=nullable))
    rel = _expand_switching([integer], [_lambda_expression([], body, invoke=True)])
    original = rel.SerializeToString()

    assert infer_rel_schema(rel).types[0] == stt.Type(
        i32=stt.Type.I32(nullability=_NULL if nullable else _REQ)
    )
    assert rel.SerializeToString() == original


def test_expand_switching_lambda_captures_input_row():
    integer = stt.Type(i32=stt.Type.I32(nullability=_REQ))
    function = stt.Type(func=stt.Type.Func(return_type=integer, nullability=_REQ))
    rel = _expand_switching(
        [function, integer], [_lambda_expression([], _field_reference(1))]
    )
    original = rel.SerializeToString()

    assert infer_rel_schema(rel).types[0] == function
    assert rel.SerializeToString() == original


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


@pytest.mark.parametrize("root", ["row", "outer_steps", "outer_anchor", "lambda"])
@pytest.mark.parametrize("depth", [1, 2])
@pytest.mark.parametrize("nullable", [False, True])
def test_infer_expression_type_nested_struct_selection(root, depth, nullable):
    from substrait.type_inference import (
        _outer_anchor_binding,
        lambda_scope,
        outer_schemas,
    )

    expected = stt.Type(string=stt.Type.String(nullability=_NULL if nullable else _REQ))
    selected = expected
    segment = stalg.Expression.ReferenceSegment(
        struct_field=stalg.Expression.ReferenceSegment.StructField(field=1)
    )
    for level in range(depth):
        selected = stt.Type(
            struct=stt.Type.Struct(types=[struct.types[0], selected], nullability=_REQ)
        )
        segment = stalg.Expression.ReferenceSegment(
            struct_field=stalg.Expression.ReferenceSegment.StructField(
                field=0 if level == depth - 1 else 1, child=segment
            )
        )
    row = stt.Type.Struct(types=[selected], nullability=_REQ)
    ref = stalg.Expression.FieldReference(direct_reference=segment)
    if root == "row":
        ref.root_reference.SetInParent()
        actual = infer_expression_type(stalg.Expression(selection=ref), row)
    elif root == "lambda":
        ref.lambda_parameter_reference.steps_out = 0
        with lambda_scope(row):
            actual = infer_expression_type(stalg.Expression(selection=ref), struct)
    elif root == "outer_anchor":
        ref.outer_reference.rel_reference = 5
        with _outer_anchor_binding(5, row):
            actual = infer_expression_type(stalg.Expression(selection=ref), struct)
    else:
        ref.outer_reference.steps_out = 1
        token = outer_schemas.set((stt.NamedStruct(struct=row),))
        try:
            actual = infer_expression_type(stalg.Expression(selection=ref), struct)
        finally:
            outer_schemas.reset(token)
    assert actual == expected


@pytest.mark.parametrize("index", [-1, 3])
def test_nested_struct_selection_rejects_out_of_range_field(index):
    row = stt.Type.Struct(types=[stt.Type(struct=struct)], nullability=_REQ)
    expr = _field_reference(0)
    expr.selection.direct_reference.struct_field.child.struct_field.field = index
    with pytest.raises(IndexError, match="Struct field index .* is out of range"):
        infer_expression_type(expr, row)


def test_nested_struct_selection_rejects_child_on_scalar():
    expr = _field_reference(0)
    expr.selection.direct_reference.struct_field.child.struct_field.field = 0
    with pytest.raises(ValueError, match="Struct field child requires a struct"):
        infer_expression_type(expr, struct)


@pytest.mark.parametrize("kind", ["list_element", "map_key"])
@pytest.mark.parametrize("nullable", [False, True])
def test_nested_collection_selection(kind, nullable):
    expr = _field_reference(0)
    child = expr.selection.direct_reference.struct_field.child
    expected = stt.Type(string=stt.Type.String(nullability=_NULL if nullable else _REQ))
    if kind == "list_element":
        child.list_element.offset = -1
        selected = stt.Type(list=stt.Type.List(type=expected, nullability=_REQ))
    else:
        child.map_key.map_key.string = "key"
        selected = stt.Type(
            map=stt.Type.Map(
                key=stt.Type(string=stt.Type.String(nullability=_REQ)),
                value=expected,
                nullability=_REQ,
            )
        )
    row = stt.Type.Struct(types=[selected], nullability=_REQ)
    assert infer_expression_type(expr, row) == expected


def test_nested_collection_selection_continues_through_struct():
    expected = stt.Type(string=stt.Type.String(nullability=_NULL))
    value = stt.Type(struct=stt.Type.Struct(types=[expected], nullability=_REQ))
    mapping = stt.Type(
        map=stt.Type.Map(
            key=stt.Type(string=stt.Type.String(nullability=_REQ)),
            value=value,
            nullability=_REQ,
        )
    )
    row = stt.Type.Struct(
        types=[stt.Type(list=stt.Type.List(type=mapping, nullability=_REQ))],
        nullability=_REQ,
    )
    expr = _field_reference(0)
    element = expr.selection.direct_reference.struct_field.child.list_element
    element.offset = 0
    key = element.child.map_key
    key.map_key.string = "key"
    key.child.struct_field.field = 0
    assert infer_expression_type(expr, row) == expected


@pytest.mark.parametrize(
    "kind, message",
    [
        ("list_element", "List element reference requires a list"),
        ("map_key", "Map key reference requires a map"),
    ],
)
def test_nested_collection_selection_rejects_wrong_container(kind, message):
    expr = _field_reference(0)
    getattr(expr.selection.direct_reference.struct_field.child, kind).SetInParent()
    with pytest.raises(ValueError, match=message):
        infer_expression_type(expr, struct)


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


def test_anchor_index_is_built_only_when_a_rel_reference_needs_it(monkeypatch):
    # Indexing rel_anchors walks every relation *and* every expression of the plan to
    # reach the relations embedded in subqueries, so it is whole-plan work on every
    # call. Plans carrying an id-based OuterReference are the exception, and the
    # builders re-infer their input's schema at every level, so the index is built on
    # demand rather than for every inference.
    import substrait.type_inference as type_inference

    iter_plan_rels = type_inference.iter_plan_rels
    indexed = []

    def counting_iter_plan_rels(plan):
        indexed.append(plan)
        return iter_plan_rels(plan)

    monkeypatch.setattr(type_inference, "iter_plan_rels", counting_iter_plan_rels)

    plain = stp.Plan(
        relations=[stp.PlanRel(root=stalg.RelRoot(input=read_rel, names=["a"]))]
    )
    assert infer_plan_schema(plain).struct == struct
    assert indexed == []

    # A rel_reference does need it, and still gets it.
    anchored = stalg.Rel(
        read=stalg.ReadRel(
            base_schema=named_struct,
            common=stalg.RelCommon(rel_anchor=7),
            named_table=stalg.ReadRel.NamedTable(names=["shared"]),
        )
    )
    correlated = stp.Plan(
        relations=[
            stp.PlanRel(rel=anchored),
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        project=stalg.ProjectRel(
                            input=right_read_rel,
                            expressions=[_outer_ref(2, rel_reference=7)],
                        )
                    ),
                    names=["a", "b", "c"],
                )
            ),
        ]
    )
    assert len(infer_plan_schema(correlated).struct.types) == 3
    assert len(indexed) == 1


# The relations that emit their input's rows unchanged. Their schema is their input's,
# so they are worth pinning together: the builders reach them only when a further verb
# resolves the schema above one, which no test happened to do for sort.
PASS_THROUGH_RELS = {
    "filter": stalg.Rel(filter=stalg.FilterRel(input=read_rel)),
    "fetch": stalg.Rel(fetch=stalg.FetchRel(input=read_rel)),
    # Bare of sort fields, like the fetch/top_n entries are of counts: a pass-through
    # relation's schema comes from its input and its own emit, and inference reads
    # neither the sorts nor the counts.
    "sort": stalg.Rel(sort=stalg.SortRel(input=read_rel)),
    "exchange": stalg.Rel(exchange=stalg.ExchangeRel(input=read_rel)),
    "top_n": stalg.Rel(top_n=stalg.TopNRel(input=read_rel)),
}


@pytest.mark.parametrize("rel", PASS_THROUGH_RELS.values(), ids=PASS_THROUGH_RELS)
def test_inference_pass_through_rels_keep_the_input_schema(rel):
    assert infer_rel_schema(rel) == struct


@pytest.mark.parametrize("rel", PASS_THROUGH_RELS.values(), ids=PASS_THROUGH_RELS)
def test_inference_pass_through_rels_apply_emit(rel):
    # A pass-through relation still projects through its own emit, so the schema it
    # reports is not unconditionally its input's.
    emitted = stalg.Rel()
    emitted.CopyFrom(rel)
    node = getattr(emitted, emitted.WhichOneof("rel_type"))
    node.common.emit.output_mapping.extend([2, 0])

    assert infer_rel_schema(emitted) == stt.Type.Struct(
        types=[struct.types[2], struct.types[0]], nullability=struct.nullability
    )
