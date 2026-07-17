import pytest
import substrait.algebra_pb2 as stalg
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import column, literal, scalar_function
from substrait.builders.plan import (
    exchange,
    hash_join,
    merge_join,
    nested_loop_join,
    read_named_table,
)
from substrait.builders.type import fp64, i64, string
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema

registry = ExtensionRegistry(load_default_extensions=True)
COMPARISON = "extension:io.substrait:functions_comparison"


def _left():
    return read_named_table(
        "a",
        stt.NamedStruct(
            names=["x", "y"],
            struct=stt.Type.Struct(
                types=[i64(nullable=False), string(nullable=False)],
                nullability=stt.Type.NULLABILITY_REQUIRED,
            ),
        ),
    )


def _right():
    return read_named_table(
        "b",
        stt.NamedStruct(
            names=["w", "z"],
            struct=stt.Type.Struct(
                types=[i64(nullable=False), fp64(nullable=False)],
                nullability=stt.Type.NULLABILITY_REQUIRED,
            ),
        ),
    )


def test_nested_loop_join_rel_and_schema():
    plan = nested_loop_join(
        _left(),
        _right(),
        expression=scalar_function(
            COMPARISON, "equal", expressions=[column("x"), column("w")]
        ),
        type=stalg.NestedLoopJoinRel.JOIN_TYPE_INNER,
    )(registry)

    nlj = plan.relations[-1].root.input.nested_loop_join
    assert nlj.type == stalg.NestedLoopJoinRel.JOIN_TYPE_INNER
    assert nlj.left.HasField("read") and nlj.right.HasField("read")
    # inner join output = left ++ right
    kinds = [t.WhichOneof("kind") for t in infer_plan_schema(plan).struct.types]
    assert kinds == ["i64", "string", "i64", "fp64"]


def test_nested_loop_left_semi_schema_is_left_only():
    plan = nested_loop_join(
        _left(),
        _right(),
        expression=scalar_function(
            COMPARISON, "equal", expressions=[column("x"), column("w")]
        ),
        type=stalg.NestedLoopJoinRel.JOIN_TYPE_LEFT_SEMI,
    )(registry)
    kinds = [t.WhichOneof("kind") for t in infer_plan_schema(plan).struct.types]
    assert kinds == ["i64", "string"]


def test_exchange_round_robin_preserves_schema():
    plan = exchange(_left(), partition_count=8)(registry)
    ex = plan.relations[-1].root.input.exchange
    assert ex.WhichOneof("exchange_kind") == "round_robin"
    assert ex.partition_count == 8
    # schema unchanged from the input
    kinds = [t.WhichOneof("kind") for t in infer_plan_schema(plan).struct.types]
    assert kinds == ["i64", "string"]


def test_exchange_broadcast():
    plan = exchange(_left(), broadcast=True)(registry)
    assert (
        plan.relations[-1].root.input.exchange.WhichOneof("exchange_kind")
        == "broadcast"
    )


@pytest.mark.parametrize(
    "builder, rel_field, rel_cls",
    [
        (hash_join, "hash_join", stalg.HashJoinRel),
        (merge_join, "merge_join", stalg.MergeJoinRel),
    ],
)
def test_equi_join_inner_residual_and_post_filter(builder, rel_field, rel_cls):
    # For an inner join the output schema equals the combined schema [x, y, w, z],
    # so post_join_filter on the right-only column z binds to index 3.
    # residual_expression references one column from each side (x on the left, w on
    # the right), confirming it binds against the combined left+right schema.
    plan = builder(
        _left(),
        _right(),
        ["x"],
        ["w"],
        rel_cls.JOIN_TYPE_INNER,
        post_join_filter=scalar_function(
            COMPARISON, "gt", expressions=[column("z"), literal(1.0, fp64())]
        ),
        residual_expression=scalar_function(
            COMPARISON, "gt", expressions=[column("x"), column("w")]
        ),
    )(registry)

    rel = getattr(plan.relations[-1].root.input, rel_field)
    assert rel.HasField("post_join_filter")
    assert rel.HasField("residual_expression")
    # z is the 4th field (index 3) of the inner-join output (== combined schema).
    post_ref = rel.post_join_filter.scalar_function.arguments[0].value.selection
    assert post_ref.direct_reference.struct_field.field == 3
    # residual: x -> 0 (left input), w -> 2 (right input).
    res_args = rel.residual_expression.scalar_function.arguments
    assert res_args[0].value.selection.direct_reference.struct_field.field == 0
    assert res_args[1].value.selection.direct_reference.struct_field.field == 2
    # The comparison extension used by the predicates is declared on the plan.
    assert len(plan.extension_urns) == 1
    assert len(plan.extensions) == 1


@pytest.mark.parametrize(
    "builder, rel_field, rel_cls",
    [
        (hash_join, "hash_join", stalg.HashJoinRel),
        (merge_join, "merge_join", stalg.MergeJoinRel),
    ],
)
def test_equi_join_post_filter_binds_output_schema(builder, rel_field, rel_cls):
    # post_join_filter applies to the join OUTPUT. A right-semi join emits the
    # right side only ([w, z]), so a filter on the right column z must bind to the
    # output-relative index 1 -- not the combined-schema index 3. residual_expression
    # still binds against the combined schema (x -> 0, w -> 2).
    plan = builder(
        _left(),
        _right(),
        ["x"],
        ["w"],
        rel_cls.JOIN_TYPE_RIGHT_SEMI,
        post_join_filter=scalar_function(
            COMPARISON, "gt", expressions=[column("z"), literal(1.0, fp64())]
        ),
        residual_expression=scalar_function(
            COMPARISON, "gt", expressions=[column("x"), column("w")]
        ),
    )(registry)

    assert list(plan.relations[-1].root.names) == ["w", "z"]
    rel = getattr(plan.relations[-1].root.input, rel_field)
    post_ref = rel.post_join_filter.scalar_function.arguments[0].value.selection
    assert post_ref.direct_reference.struct_field.field == 1
    res_args = rel.residual_expression.scalar_function.arguments
    assert res_args[0].value.selection.direct_reference.struct_field.field == 0
    assert res_args[1].value.selection.direct_reference.struct_field.field == 2


@pytest.mark.parametrize(
    "builder, rel_cls",
    [(hash_join, stalg.HashJoinRel), (merge_join, stalg.MergeJoinRel)],
)
def test_equi_join_post_filter_on_dropped_side_raises(builder, rel_cls):
    # A right-semi join drops the left side from its output, so a post_join_filter
    # referencing a left column cannot resolve -- it fails fast rather than emitting
    # a dangling field reference.
    with pytest.raises(ValueError, match="not in list"):
        builder(
            _left(),
            _right(),
            ["x"],
            ["w"],
            rel_cls.JOIN_TYPE_RIGHT_SEMI,
            post_join_filter=scalar_function(
                COMPARISON, "gt", expressions=[column("x"), literal(1, i64())]
            ),
        )(registry)


@pytest.mark.parametrize(
    "builder, rel_field, rel_cls",
    [
        (hash_join, "hash_join", stalg.HashJoinRel),
        (merge_join, "merge_join", stalg.MergeJoinRel),
    ],
)
def test_equi_join_predicates_unset_by_default(builder, rel_field, rel_cls):
    plan = builder(_left(), _right(), ["x"], ["w"], rel_cls.JOIN_TYPE_INNER)(registry)
    rel = getattr(plan.relations[-1].root.input, rel_field)
    assert not rel.HasField("post_join_filter")
    assert not rel.HasField("residual_expression")


@pytest.mark.parametrize("builder, rel_cls", [(hash_join, stalg.HashJoinRel)])
def test_equi_join_optional_args_are_keyword_only(builder, rel_cls):
    # post_join_filter / residual_expression / extension are keyword-only so a
    # positional arg after `type` cannot silently rebind one of them.
    with pytest.raises(TypeError):
        builder(
            _left(),
            _right(),
            ["x"],
            ["w"],
            rel_cls.JOIN_TYPE_INNER,
            None,  # would have bound to post_join_filter positionally
        )
