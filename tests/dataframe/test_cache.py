"""Tests for DataFrame.cache() -- shared subplans / CTEs (ReferenceRel).

A cached frame is emitted once as a leading shared subtree (a ``PlanRel(rel=...)``)
and referenced via a ``ReferenceRel`` wherever it is used; repeated uses that meet
at a multi-input relation collapse to a single shared subtree.
"""

import pytest

import substrait.dataframe as sub


def test_cache_emits_shared_subtree_referenced_twice(find_reference):
    base = sub.read_named_table("t", {"id": sub.i64, "v": sub.i64}).cache()
    plan = (
        base.filter(sub.col("id") < 10)
        .union(base.filter(sub.col("id") >= 10))
        .to_plan()
    )
    assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "root"]
    assert plan.relations[0].rel.HasField("read")
    set_inputs = plan.relations[-1].root.input.set.inputs
    assert [find_reference(i) for i in set_inputs] == [0, 0]


def test_no_cache_inlines_single_relation(find_reference):
    a = sub.read_named_table("t", {"id": sub.i64})
    plan = a.filter(sub.col("id") > 0).union(a.filter(sub.col("id") < 0)).to_plan()
    # Without cache the source is inlined into each union input -- no shared subtree.
    assert len(plan.relations) == 1
    for i in plan.relations[-1].root.input.set.inputs:
        assert find_reference(i) is None


def test_cache_schema_inference_through_reference(find_reference):
    # Filtering/selecting the cached frame requires inferring its schema through the
    # ReferenceRel.
    base = sub.read_named_table("t", {"id": sub.i64, "v": sub.i64}).cache()
    plan = base.filter(sub.col("v") > 0).select("id").to_plan()
    # The plan must actually carry the shared subtree and reach it via a reference
    # (a no-op cache would inline the read and drop both, so these guard the path).
    assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "root"]
    assert find_reference(plan.relations[-1].root.input) == 0
    assert plan.relations[-1].root.input.project.HasField("common")
    assert list(plan.relations[-1].root.names) == ["id"]


def test_cache_merges_subtree_extensions():
    base = sub.read_named_table("t", {"id": sub.i64}).filter(sub.col("id") > 5).cache()
    plan = base.union(base).to_plan()
    # The comparison function used inside the cached subtree must be declared on the
    # merged plan; the shared subtree itself must be emitted (a no-op cache would
    # inline it into both union inputs, giving a single relation).
    assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "root"]
    assert plan.relations[0].rel.filter.HasField("condition")
    urns = {u.urn for u in plan.extension_urns}
    assert "extension:io.substrait:functions_comparison" in urns


def test_distinct_caches_rebased_across_union(find_reference):
    # Two *different* cached frames unioned keep distinct subtree ordinals (0, 1),
    # rebasing the second input's ReferenceRel.
    a = sub.read_named_table("a", {"id": sub.i64}).cache()
    b = sub.read_named_table("b", {"id": sub.i64}).cache()
    plan = a.union(b).to_plan()
    assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "rel", "root"]
    set_inputs = plan.relations[-1].root.input.set.inputs
    assert [find_reference(i) for i in set_inputs] == [0, 1]


def test_nested_cache_references_earlier_subtree(find_reference):
    # A cache built on top of another cache produces a subtree that itself
    # references the earlier subtree.
    a = sub.read_named_table("t", {"id": sub.i64, "v": sub.i64}).cache()
    b = a.filter(sub.col("v") > 0).cache()
    plan = b.union(b).to_plan()
    assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "rel", "root"]
    # subtree 0 is the read; subtree 1 is b's filter, referencing subtree 0.
    assert plan.relations[0].rel.HasField("read")
    assert find_reference(plan.relations[1].rel) == 0
    # Both set inputs reference the promoted b subtree (ordinal 1).
    set_inputs = plan.relations[-1].root.input.set.inputs
    assert [find_reference(i) for i in set_inputs] == [1, 1]


def test_cache_inside_subquery_is_inlined(find_reference):
    # A cached frame consumed inside a subquery cannot carry a plan-global
    # ReferenceRel across the subquery boundary, so it is inlined into the subquery
    # (self-contained) and the outer plan carries no dangling shared subtree.
    from substrait.dataframe.expr import exists

    a = sub.read_named_table("a", {"x": sub.i64}).cache()
    b = sub.read_named_table("b", {"y": sub.i64})
    plan = b.filter(exists(a)).to_plan()
    assert all(r.WhichOneof("rel_type") != "rel" for r in plan.relations)
    tuples = plan.relations[
        -1
    ].root.input.filter.condition.subquery.set_predicate.tuples
    assert find_reference(tuples) is None
    assert tuples.WhichOneof("rel_type") == "read"


def test_hint_after_cache_raises():
    base = sub.read_named_table("t", {"id": sub.i64}).cache()
    with pytest.raises(TypeError, match="cannot attach a hint"):
        base.hint(alias="x").to_plan()


def test_hint_before_cache_is_fine():
    # Hinting the node *before* caching it is allowed (the hint lands on the read).
    plan = (
        sub.read_named_table("t", {"id": sub.i64}).hint(alias="src").cache().to_plan()
    )
    assert plan.relations[0].rel.read.common.hint.alias == "src"
