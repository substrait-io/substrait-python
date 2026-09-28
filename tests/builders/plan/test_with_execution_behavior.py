import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.plan import (
    default_version,
    exchange,
    read_named_table,
    set,
    with_execution_behavior,
)
from substrait.builders.type import boolean, i64

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()],
    nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
)

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)

PER_PLAN = stp.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_PLAN
PER_RECORD = stp.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_RECORD


def test_with_execution_behavior_per_record():
    base = read_named_table("example_table", named_struct)

    actual = with_execution_behavior(base, PER_RECORD)(None)

    expected = read_named_table("example_table", named_struct)(None)
    expected.execution_behavior.CopyFrom(
        stp.ExecutionBehavior(variable_eval_mode=PER_RECORD)
    )

    assert actual == expected
    assert actual.version == default_version


def test_with_execution_behavior_per_plan_preserves_relations():
    base = read_named_table("example_table", named_struct)

    actual = with_execution_behavior(base, PER_PLAN)(None)

    assert actual.execution_behavior.variable_eval_mode == PER_PLAN
    # the underlying relation is left untouched
    assert actual.relations == base(None).relations


def test_with_execution_behavior_accepts_bound_plan_without_mutating_it():
    bound = read_named_table("example_table", named_struct)(None)

    actual = with_execution_behavior(bound, PER_PLAN)(None)

    assert actual.execution_behavior.variable_eval_mode == PER_PLAN
    # the caller's input plan is not mutated in place
    assert not bound.HasField("execution_behavior")


def test_execution_behavior_survives_subsequent_builder():
    # Applying a builder after the setting must not drop it: the fresh output
    # Plan carries the execution behavior over from its input.
    base = with_execution_behavior(read_named_table("t", named_struct), PER_RECORD)

    actual = exchange(base, partition_count=2)(None)

    assert actual.execution_behavior.variable_eval_mode == PER_RECORD


def test_with_execution_behavior_overwrites_existing():
    # Applying it again replaces the previous mode (last wins), rather than
    # merging or keeping the earlier value.
    base = with_execution_behavior(read_named_table("t", named_struct), PER_PLAN)

    actual = with_execution_behavior(base, PER_RECORD)(None)

    assert actual.execution_behavior.variable_eval_mode == PER_RECORD


def test_execution_behavior_taken_from_first_input():
    # For multi-input builders the first input that declares one wins.
    left = with_execution_behavior(read_named_table("l", named_struct), PER_RECORD)
    right = with_execution_behavior(read_named_table("r", named_struct), PER_PLAN)

    actual = set([left, right], stalg.SetRel.SET_OP_UNION_ALL)(None)

    assert actual.execution_behavior.variable_eval_mode == PER_RECORD


def test_plans_have_no_execution_behavior_by_default():
    plan = read_named_table("example_table", named_struct)(None)

    assert not plan.HasField("execution_behavior")


def test_execution_behavior_on_a_plan_carrying_no_relations():
    # This is the one builder that copies a caller-supplied Plan wholesale instead of
    # assembling the relations itself, so it has to stay total over the Plans it
    # accepts -- including degenerate ones it only sets a field on. Recording the
    # copied root's schema for the build (see builders.plan._remember_input_schemas)
    # must not turn that into an IndexError.
    actual = with_execution_behavior(stp.Plan(version=default_version), PER_RECORD)(
        None
    )

    assert actual.execution_behavior.variable_eval_mode == PER_RECORD
    assert not actual.relations


def test_execution_behavior_on_a_plan_whose_last_relation_is_a_subtree():
    # Likewise for a Plan whose trailing entry is a shared subtree rather than a query
    # root: there is no root schema to record, and reading one would key the build's
    # memo on an unset-oneof stub that a later write could reify in place.
    base = read_named_table("example_table", named_struct)(None)
    subtree_only = stp.Plan(
        version=default_version,
        relations=[stp.PlanRel(rel=base.relations[-1].root.input)],
    )

    actual = with_execution_behavior(subtree_only, PER_RECORD)(None)

    assert actual.execution_behavior.variable_eval_mode == PER_RECORD
    assert [r.WhichOneof("rel_type") for r in actual.relations] == ["rel"]
