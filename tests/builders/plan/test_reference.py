import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import literal
from substrait.builders.plan import (
    default_version,
    fetch,
    read_named_table,
    reference,
    set,
)
from substrait.builders.type import i64
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(
    types=[
        stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
        stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED)),
    ],
    nullability=stt.Type.NULLABILITY_REQUIRED,
)
named_struct = stt.NamedStruct(names=["id", "v"], struct=struct)


def test_reference_emits_shared_subtree_and_ref_root():
    table = read_named_table("t", named_struct)
    plan = reference(table)(registry)

    assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "root"]
    # The promoted subtree is the source read; the root references it by ordinal 0.
    assert plan.relations[0].rel.HasField("read")
    root = plan.relations[-1].root
    assert root.input.WhichOneof("rel_type") == "reference"
    assert root.input.reference.subtree_ordinal == 0
    assert list(root.names) == ["id", "v"]


def test_reference_schema_inference_resolves_through_ref():
    # A plan rooted at a ReferenceRel infers its schema from the shared subtree.
    plan = reference(read_named_table("t", named_struct))(registry)
    ns = infer_plan_schema(plan, registry=registry)
    assert ns == named_struct


def test_reference_shared_subtree_deduped_across_inputs(find_reference):
    # The same cached subtree feeding two branches that meet at a set collapses to
    # a single shared subtree, referenced from both inputs.
    base = reference(read_named_table("t", named_struct))
    plan = set([base, base], stalg.SetRel.SET_OP_UNION_ALL)(registry)

    assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "root"]
    set_inputs = plan.relations[-1].root.input.set.inputs
    assert [find_reference(i) for i in set_inputs] == [0, 0]


def test_reference_distinct_subtrees_are_rebased(find_reference):
    # Two *different* cached subtrees merged at a set keep distinct ordinals; the
    # second input's ReferenceRel is rebased from 0 to 1.
    a = reference(read_named_table("a", named_struct))
    b = reference(read_named_table("b", named_struct))
    plan = set([a, b], stalg.SetRel.SET_OP_UNION_ALL)(registry)

    assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "rel", "root"]
    assert list(plan.relations[0].rel.read.named_table.names) == ["a"]
    assert list(plan.relations[1].rel.read.named_table.names) == ["b"]
    set_inputs = plan.relations[-1].root.input.set.inputs
    assert [find_reference(i) for i in set_inputs] == [0, 1]


def test_reference_carried_through_single_input_builder():
    # A downstream single-input builder keeps the leading subtree (and its ordinal),
    # wrapping the ReferenceRel rather than inlining the source.
    base = reference(read_named_table("t", named_struct))
    plan = fetch(base, offset=literal(0, i64()), count=literal(5, i64()))(registry)

    assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "root"]
    assert plan.relations[0].rel.HasField("read")
    fetch_rel = plan.relations[-1].root.input
    assert fetch_rel.WhichOneof("rel_type") == "fetch"
    assert fetch_rel.fetch.input.reference.subtree_ordinal == 0
    # Schema still resolves through the wrapped reference.
    assert infer_plan_schema(plan, registry=registry) == named_struct


def test_reference_out_of_range_ordinal_raises():
    # A bare ReferenceRel with no subtrees in scope cannot be inferred.
    ref_plan = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(reference=stalg.ReferenceRel(subtree_ordinal=0)),
                    names=["id", "v"],
                )
            )
        ],
    )
    with pytest.raises(Exception, match="out of range"):
        infer_plan_schema(ref_plan, registry=registry)
