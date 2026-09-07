"""The per-build schema memo: what it costs to build a pipeline, and the pairing it
relies on.

Every verb resolves its input's schema, and a plan is built as nested resolvers, so
without memoization an N-verb chain re-walks the whole subtree beneath it at every
level -- O(N^2) inference (#207). ``builders.plan._remember_input_schemas`` records
each embedded input relation's schema as the plan is assembled, and
``infer_plan_schema`` builds its ``rel_anchor`` index only when an id-based outer
reference asks for one. Both are invisible in the emitted plan, so they need tests
that observe cost, plus tests that the recorded schemas land on the right relations.
"""

import collections

import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

import substrait.type_inference as type_inference
from substrait.builders.extended_expression import column, literal
from substrait.builders.plan import (
    cross,
    exchange,
    hash_join,
    join,
    lateral_join,
    merge_join,
    nested_loop_join,
    project,
    read_named_table,
    reference,
    set,
    with_execution_behavior,
    write_named_table,
)
from substrait.builders.type import boolean, i64, string
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema, schema_memo

registry = ExtensionRegistry(load_default_extensions=False)

named_struct = stt.NamedStruct(
    names=["k", "v"],
    struct=stt.Type.Struct(
        types=[i64(nullable=False), i64(nullable=False)],
        nullability=stt.Type.NULLABILITY_REQUIRED,
    ),
)

# Same arity as `named_struct` but a different second column type, so pairing the
# two sides of a join the wrong way round shows up in the types alone.
right_named_struct = stt.NamedStruct(
    names=["rk", "rv"],
    struct=stt.Type.Struct(
        types=[i64(nullable=False), string()],
        nullability=stt.Type.NULLABILITY_REQUIRED,
    ),
)


@pytest.fixture
def counts(monkeypatch):
    """Counts of the two whole-subtree walks a build must not repeat per level.

    Both are patched on ``substrait.type_inference`` because that is where the
    recursion and the anchor index resolve them from.
    """
    counted: collections.Counter = collections.Counter()

    infer_rel_schema = type_inference.infer_rel_schema
    iter_plan_rels = type_inference.iter_plan_rels

    def counting_infer_rel_schema(rel, **kwargs):
        counted["infer_rel_schema"] += 1
        return infer_rel_schema(rel, **kwargs)

    def counting_iter_plan_rels(plan):
        counted["iter_plan_rels"] += 1
        return iter_plan_rels(plan)

    monkeypatch.setattr(type_inference, "infer_rel_schema", counting_infer_rel_schema)
    monkeypatch.setattr(type_inference, "iter_plan_rels", counting_iter_plan_rels)
    return counted


def _project_chain(length: int):
    plan = read_named_table("t", named_struct)
    for _ in range(length):
        plan = project(plan, expressions=[column("v")])
    return plan


def _exchange_chain(length: int):
    plan = read_named_table("t", named_struct)
    for _ in range(length):
        plan = exchange(plan, partition_count=2)
    return plan


def _behavior_chain(length: int):
    plan = read_named_table("t", named_struct)
    for _ in range(length):
        plan = with_execution_behavior(
            plan, stp.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_PLAN
        )
    return plan


# Chains of verbs that never ask their input for a schema, so no lookup ever resolves
# and nothing is released by one -- the case that makes recording, not resolving, the
# point at which unreachable entries have to be dropped. Both shapes are here because
# they record at different depths: `exchange` names the input relation embedded in the
# relation it assembled, `with_execution_behavior` the root input of the plan it copied,
# one level shallower.
NON_INFERRING_CHAINS = [_exchange_chain, _behavior_chain]
NON_INFERRING_IDS = ["exchange", "with_execution_behavior"]


# Deliberately well above the 4N-4 this currently does and well below the ~N^2/2 it
# did before, so the test tracks the complexity class rather than the exact count. Only
# the longer chains can discriminate: unmemoized costs 10/36/136/528 for the four
# lengths, so 4 and 8 come in under any bound that 16 and 32 fail, and are here to
# exercise short chains rather than to catch the regression.
_CALLS_PER_VERB = 6


@pytest.mark.parametrize("length", [4, 8, 16, 32])
def test_building_a_chain_infers_each_level_a_bounded_number_of_times(counts, length):
    built = _project_chain(length)(registry)

    assert len(built.relations[-1].root.names) == 2 + length
    assert counts["infer_rel_schema"] <= _CALLS_PER_VERB * length


def test_building_a_chain_never_indexes_rel_anchors(counts):
    # Indexing walks every relation and expression in the plan. Nothing here carries
    # an id-based OuterReference, so nothing should ask for the index. Asserted against
    # a positive control, because a Counter reads 0 for a key nothing ever wrote: were
    # the patch to stop intercepting, a bare `== 0` would keep passing.
    _project_chain(8)(registry)
    assert counts["infer_rel_schema"] > 0
    assert counts["iter_plan_rels"] == 0


@pytest.mark.parametrize(
    "chain",
    [_project_chain, *NON_INFERRING_CHAINS],
    ids=["project", *NON_INFERRING_IDS],
)
def test_memo_retention_does_not_grow_with_chain_length(monkeypatch, chain):
    # An entry keys on a live submessage, which keeps its whole plan's arena alive, so
    # entries that accumulate hold every intermediate plan of the build rather than the
    # levels in flight. `_release_boundaries_of` drops each entry once it is unreachable
    # -- when a lookup has resolved through it, and when a new entry is recorded over an
    # unresolved one, which is the only release a chain that resolves nothing ever gets.
    # This pins both, by watching how many entries are ever live at once.
    peaks = {}
    original = type_inference._SchemaMemo.remember_plan_output

    for length in (4, 8, 16, 32):
        peak = 0

        def counting_remember(self, rel, plan):
            nonlocal peak
            original(self, rel, plan)
            peak = max(peak, len(self._structs) + len(self._pending))

        monkeypatch.setattr(
            type_inference._SchemaMemo, "remember_plan_output", counting_remember
        )
        chain(length)(registry)
        peaks[length] = peak

    # Bounded by the levels in flight, not by the chain: 8x the verbs must not mean
    # meaningfully more live entries.
    assert peaks[32] <= peaks[4] + 2, peaks


@pytest.mark.parametrize("chain", NON_INFERRING_CHAINS, ids=NON_INFERRING_IDS)
def test_inference_above_a_chain_that_resolved_nothing_still_gets_its_schema(chain):
    # Recording releases the unresolved entries it supersedes, so the first inference
    # above such a chain walks it a level at a time instead of hopping the boundaries
    # that were recorded through it. It has to arrive at the same schema either way.
    built = project(chain(4), expressions=[column("v")])(registry)

    schema = infer_plan_schema(built, registry=registry)
    assert list(schema.names) == ["k", "v", "v"]
    assert list(schema.struct.types) == [i64(nullable=False)] * 3


@pytest.mark.parametrize("length", [4, 8, 16])
def test_a_chain_that_resolves_nothing_costs_no_walk_per_level_above_it(counts, length):
    # The verbs below resolve nothing, so the projections above them are what force the
    # boundaries -- and must not each re-walk the whole run to do it.
    project_chain = _exchange_chain(length)
    for _ in range(length):
        project_chain = project(project_chain, expressions=[column("v")])

    project_chain(registry)

    assert counts["infer_rel_schema"] <= _CALLS_PER_VERB * 2 * length


def test_memo_does_not_outlive_the_build():
    # The memo keys on object identity and holds its keys alive, so leaking it past
    # the build would both pin memory and answer for relations of a later one.
    assert schema_memo.get() is None
    built = _project_chain(2)(registry)
    assert schema_memo.get() is None

    # Inference of the finished plan is unmemoized and still correct.
    assert list(infer_plan_schema(built, registry=registry).names) == [
        "k",
        "v",
        "v",
        "v",
    ]


def _left():
    return read_named_table("left", named_struct)


def _right():
    return read_named_table("right", right_named_struct)


def _true():
    return literal(True, boolean())


# The builders that embed more than one input relation into a *pair* of fields, since
# those are the ones whose recorded schemas could be paired with the wrong side. The
# repeated-field ones (`set`, `extension_multi`) take their inputs in one list and are
# covered separately below, where order shows up in the output rather than in the types.
TWO_INPUT_BUILDERS = {
    "join": lambda: join(_left(), _right(), _true(), stalg.JoinRel.JOIN_TYPE_INNER),
    "cross": lambda: cross(_left(), _right()),
    "nested_loop_join": lambda: nested_loop_join(
        _left(), _right(), _true(), stalg.NestedLoopJoinRel.JOIN_TYPE_INNER
    ),
    "hash_join": lambda: hash_join(
        _left(), _right(), ["k"], ["rk"], stalg.HashJoinRel.JOIN_TYPE_INNER
    ),
    "merge_join": lambda: merge_join(
        _left(), _right(), ["k"], ["rk"], stalg.MergeJoinRel.JOIN_TYPE_INNER
    ),
    "lateral_join": lambda: lateral_join(
        _left(), lambda handle: _right(), stalg.JoinRel.JOIN_TYPE_INNER
    ),
}


@pytest.mark.parametrize("builder", TWO_INPUT_BUILDERS.values(), ids=TWO_INPUT_BUILDERS)
def test_two_input_builders_record_each_side_against_its_own_relation(builder):
    # write_named_table emits the schema it inferred for its input, so it reports what
    # the level above the join sees: left columns then right columns. Swapping the
    # recorded schemas keeps the arity and the names but reorders the types.
    written = write_named_table("out", builder())(registry)

    table_schema = written.relations[-1].root.input.write.table_schema
    assert list(table_schema.names) == ["k", "v", "rk", "rv"]
    assert list(table_schema.struct.types) == [
        i64(nullable=False),
        i64(nullable=False),
        i64(nullable=False),
        string(),
    ]


def test_lateral_join_records_a_correlated_right_input_against_its_own_relation():
    # `lateral_join` assembles its relation *outside* the anchor binding its right input
    # was built under, so the recorded schema is resolved later, with the binding
    # re-established by inference rather than by the builder. A right input that
    # actually correlates is what exercises that: it can only be inferred while the
    # left row is bound to the join's rel_anchor.
    lateral = lateral_join(
        _left(),
        lambda handle: project(_right(), expressions=[handle.column("k")]),
        stalg.JoinRel.JOIN_TYPE_INNER,
    )
    written = write_named_table("out", lateral)(registry)

    table_schema = written.relations[-1].root.input.write.table_schema
    assert list(table_schema.names) == ["k", "v", "rk", "rv", "k"]
    assert list(table_schema.struct.types) == [
        i64(nullable=False),
        i64(nullable=False),
        i64(nullable=False),
        string(),
        i64(nullable=False),
    ]


def test_set_records_each_input_against_its_own_relation():
    # SetRel takes its inputs as one repeated field, so a mispairing shows up in the
    # ops whose output is not symmetric in the inputs: MINUS takes each field's
    # nullability from the *primary* (first) input alone, so pairing the recorded
    # schemas the wrong way round reports the secondary's nullability instead.
    primary = read_named_table(
        "primary",
        stt.NamedStruct(
            names=["k"],
            struct=stt.Type.Struct(
                types=[i64(nullable=False)], nullability=stt.Type.NULLABILITY_REQUIRED
            ),
        ),
    )
    secondary = read_named_table(
        "secondary",
        stt.NamedStruct(
            names=["k"],
            struct=stt.Type.Struct(
                types=[i64(nullable=True)], nullability=stt.Type.NULLABILITY_REQUIRED
            ),
        ),
    )
    written = write_named_table(
        "out", set([primary, secondary], stalg.SetRel.SET_OP_MINUS_PRIMARY)
    )(registry)

    table_schema = written.relations[-1].root.input.write.table_schema
    assert list(table_schema.struct.types) == [i64(nullable=False)]


def test_reference_records_the_promoted_subtree_and_the_reference():
    # A ReferenceRel's schema is its subtree's, and `reference` records both so a
    # downstream verb resolves it by lookup rather than by walking the subtree.
    written = write_named_table("out", reference(_left()))(registry)

    table_schema = written.relations[-1].root.input.write.table_schema
    assert table_schema == named_struct


def test_with_execution_behavior_records_the_copied_root():
    # This builder copies its input plan wholesale rather than assembling a fresh
    # relation, so the copy needs its own record.
    written = write_named_table(
        "out",
        with_execution_behavior(
            _left(), stp.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_RECORD
        ),
    )(registry)

    table_schema = written.relations[-1].root.input.write.table_schema
    assert table_schema == named_struct
