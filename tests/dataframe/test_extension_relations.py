"""Tests for user-defined extension relations (leaf / single / multi).

A user implements a detail class (to_any / from_any / derive_schema) and
registers it, after which the frame builds the custom relation and schema
inference follows it -- the Python analog of substrait-java's Extension.*RelDetail.
"""

import pytest
import substrait.type_pb2 as stt
from google.protobuf.any_pb2 import Any

import substrait.dataframe as sub
from substrait.type_inference import infer_plan_schema

_BOOL = stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED))


def _required(types, names):
    return stt.NamedStruct(
        names=names,
        struct=stt.Type.Struct(types=types, nullability=stt.Type.NULLABILITY_REQUIRED),
    )


class MySource(sub.ExtensionLeafDetail):
    """A leaf source that yields a single i64 ``id`` column."""

    type_url = "example.com/MySource"

    def to_any(self):
        return Any(type_url=self.type_url, value=b"")

    @classmethod
    def from_any(cls, detail):
        return cls()

    def derive_schema(self):
        return _required([sub.i64.non_null], ["id"])


class AddFlag(sub.ExtensionSingleDetail):
    """A single-input relation that appends a boolean ``flag`` column."""

    type_url = "example.com/AddFlag"

    def to_any(self):
        return Any(type_url=self.type_url, value=b"")

    @classmethod
    def from_any(cls, detail):
        return cls()

    def derive_schema(self, input):
        names = [f"c{i}" for i in range(len(input.types))] + ["flag"]
        return _required(list(input.types) + [_BOOL], names)


class Zip(sub.ExtensionMultiDetail):
    """A multi-input relation that concatenates its inputs' columns."""

    type_url = "example.com/Zip"

    def to_any(self):
        return Any(type_url=self.type_url, value=b"")

    @classmethod
    def from_any(cls, detail):
        return cls()

    def derive_schema(self, inputs):
        types = [t for schema in inputs for t in schema.types]
        return _required(types, [f"z{i}" for i in range(len(types))])


registry = sub.ExtensionRegistry(load_default_extensions=True)
for _cls in (MySource, AddFlag, Zip):
    registry.register_extension_relation(_cls)


def _kinds(plan):
    return [
        t.WhichOneof("kind")
        for t in infer_plan_schema(plan, registry=registry).struct.types
    ]


def test_extension_leaf_source():
    plan = sub.extension_leaf(MySource(), registry=registry).to_plan()
    rel = plan.relations[-1].root.input
    assert rel.HasField("extension_leaf")
    assert rel.extension_leaf.detail.type_url == "example.com/MySource"
    assert list(plan.relations[-1].root.names) == ["id"]
    assert _kinds(plan) == ["i64"]


def test_extension_single_derives_schema_and_chains():
    df = sub.extension_leaf(MySource(), registry=registry).extension(AddFlag())
    plan = df.filter(sub.col("flag")).to_plan()  # references the derived column
    # AddFlag output = input columns (c0) + the appended flag
    assert list(plan.relations[-1].root.names) == ["c0", "flag"]
    assert _kinds(plan) == ["i64", "bool"]
    es = plan.relations[-1].root.input.filter.input.extension_single
    assert es.detail.type_url == "example.com/AddFlag"


def test_extension_multi_concatenates_inputs():
    a = sub.read_named_table("a", {"x": sub.i64}, registry=registry)
    b = sub.read_named_table("b", {"y": sub.string}, registry=registry)
    plan = a.extension_multi([b], Zip()).to_plan()
    rel = plan.relations[-1].root.input.extension_multi
    assert len(rel.inputs) == 2
    assert list(plan.relations[-1].root.names) == ["z0", "z1"]
    assert _kinds(plan) == ["i64", "string"]


def test_extension_single_raw_any_passthrough():
    # Backward-compatible raw-Any path: schema is assumed unchanged.
    df = sub.read_named_table("t", {"a": sub.i64, "b": sub.i64}, registry=registry)
    plan = (
        df.extension(Any(type_url="example.com/Opaque", value=b"x"))
        .filter(sub.col("a") > 0)
        .to_plan()
    )
    assert list(plan.relations[-1].root.names) == ["a", "b"]


def test_unregistered_extension_leaf_chain_raises():
    # Chaining needs the schema; an unregistered leaf can't derive one.
    df = sub.extension_leaf(Any(type_url="example.com/Unknown", value=b""))
    with pytest.raises(Exception, match="no schema deriver"):
        df.filter(sub.col("x") > 0).to_plan()


def test_deriver_registration_is_scoped_to_registry():
    # Derivers live on the ExtensionRegistry instance, not a process-global: a
    # detail class registered on one registry must not derive on an independent
    # one (issue #206).
    plan = sub.extension_leaf(MySource(), registry=registry).to_plan()

    other = sub.ExtensionRegistry(load_default_extensions=True)
    with pytest.raises(Exception, match="no schema deriver"):
        infer_plan_schema(plan, registry=other)

    # ...and the registry it was registered on still derives it.
    assert [
        t.WhichOneof("kind")
        for t in infer_plan_schema(plan, registry=registry).struct.types
    ] == ["i64"]
