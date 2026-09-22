import pytest
import substrait.algebra_pb2 as stalg
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import column, scalar_function
from substrait.builders.plan import (
    hash_join,
    join,
    lateral_join,
    merge_join,
    nested_loop_join,
    read_named_table,
)
from substrait.builders.type import boolean, i64, string
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema, infer_rel_schema

REGISTRY = ExtensionRegistry()
LEFT = stt.NamedStruct(
    names=["l_id", "payload", "text", "l_flag"],
    struct=stt.Type.Struct(
        types=[
            i64(nullable=False),
            stt.Type(
                struct=stt.Type.Struct(
                    types=[string()], nullability=stt.Type.NULLABILITY_REQUIRED
                )
            ),
            boolean(nullable=False),
        ],
        nullability=stt.Type.NULLABILITY_REQUIRED,
    ),
)
RIGHT = stt.NamedStruct(
    names=["r_id", "r_flag"],
    struct=stt.Type.Struct(
        types=[i64(), boolean()], nullability=stt.Type.NULLABILITY_REQUIRED
    ),
)
JOIN_CASES = [
    pytest.param(builder, field, cls, side, id=f"{field}-{side.lower()}")
    for builder, field, cls in [
        (join, "join", stalg.JoinRel),
        (lateral_join, "lateral_join", stalg.JoinRel),
        (nested_loop_join, "nested_loop_join", stalg.NestedLoopJoinRel),
        (hash_join, "hash_join", stalg.HashJoinRel),
        (merge_join, "merge_join", stalg.MergeJoinRel),
    ]
    for side in ("LEFT", "RIGHT")
    if builder is not lateral_join or side == "LEFT"
]


def _mark_plan(builder, cls, side, post_field="mark"):
    left = read_named_table("l", LEFT)
    right = read_named_table("r", RIGHT)
    condition = scalar_function(
        "extension:io.substrait:functions_comparison",
        "equal",
        expressions=[column("l_id"), column("r_id")],
    )
    join_type = getattr(cls, f"JOIN_TYPE_{side}_MARK")
    if builder is nested_loop_join:
        plan = builder(left, right, condition, join_type)
    elif builder is lateral_join:
        plan = builder(
            left,
            lambda _: right,
            join_type,
            expression=condition,
            post_join_filter=column(post_field),
        )
    elif builder is join:
        plan = builder(
            left, right, condition, join_type, post_join_filter=column(post_field)
        )
    else:
        plan = builder(
            left,
            right,
            ["l_id"],
            ["r_id"],
            join_type,
            post_join_filter=column(post_field),
            residual_expression=condition,
        )
    return plan(REGISTRY)


@pytest.mark.parametrize("builder,field,cls,side", JOIN_CASES)
def test_mark_join_output_and_condition_bindings(builder, field, cls, side):
    plan = _mark_plan(builder, cls, side)
    root = plan.relations[-1].root
    rel = getattr(root.input, field)
    condition = (
        rel.residual_expression
        if builder in (hash_join, merge_join)
        else rel.expression
    )
    # Conditions use both inputs, counting top-level fields rather than DFS names.
    assert [
        arg.value.selection.direct_reference.struct_field.field
        for arg in condition.scalar_function.arguments
    ] == [0, 3]

    kept = LEFT if side == "LEFT" else RIGHT
    expected = stt.NamedStruct(
        names=[*kept.names, "mark"],
        struct=stt.Type.Struct(
            types=[*kept.struct.types, boolean()],
            nullability=stt.Type.NULLABILITY_REQUIRED,
        ),
    )
    assert list(root.names) == list(expected.names)
    assert infer_rel_schema(root.input, registry=REGISTRY) == expected.struct
    assert infer_plan_schema(plan, registry=REGISTRY) == expected
    if builder is not nested_loop_join:
        ref = rel.post_join_filter.selection.direct_reference.struct_field
        assert ref.field == len(kept.struct.types)


@pytest.mark.parametrize(
    "builder,field,cls,side",
    [case for case in JOIN_CASES if case.values[0] is not nested_loop_join],
)
def test_mark_join_post_filter_cannot_reference_dropped_side(builder, field, cls, side):
    dropped_field = "r_flag" if side == "LEFT" else "l_flag"
    with pytest.raises(ValueError, match=dropped_field):
        _mark_plan(builder, cls, side, dropped_field)


@pytest.mark.parametrize("builder,field,cls,side", JOIN_CASES)
def test_mark_join_emit_indexes_selected_side_and_marker(builder, field, cls, side):
    plan = _mark_plan(builder, cls, side)
    kept = LEFT if side == "LEFT" else RIGHT
    root = plan.relations[-1].root
    rel = getattr(root.input, field)
    rel.common.emit.output_mapping[:] = [
        len(kept.struct.types),
        0,
        len(kept.struct.types),
    ]
    root.names[:] = ["first_mark", "id", "second_mark"]
    assert infer_plan_schema(plan, registry=REGISTRY) == stt.NamedStruct(
        names=list(root.names),
        struct=stt.Type.Struct(
            types=[boolean(), kept.struct.types[0], boolean()],
            nullability=stt.Type.NULLABILITY_REQUIRED,
        ),
    )
