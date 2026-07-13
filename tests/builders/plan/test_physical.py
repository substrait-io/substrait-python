import substrait.algebra_pb2 as stalg
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import column, scalar_function
from substrait.builders.plan import exchange, nested_loop_join, read_named_table
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
