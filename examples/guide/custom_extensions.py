"""Runnable source for the snippets in docs/custom-extensions.md.

Run from this file's directory so ``register_extension_yaml("my_functions.yaml")``
resolves the fixture next to this script. The ``definitions`` dict, the single-
and multi-input detail classes, and the ``base`` / ``other*`` frames used by the
"building the relation" snippet are defined here as hidden fixtures.
"""

import os
from pathlib import Path

os.chdir(Path(__file__).parent)

# Fixture: an already-parsed extension dict for register_extension_dict (a
# distinct urn so it doesn't collide with my_functions.yaml).
definitions = {
    "urn": "extension:example:more_functions",
    "scalar_functions": [
        {
            "name": "my_triple",
            "impls": [{"args": [{"name": "x", "value": "i64"}], "return": "i64"}],
        }
    ],
}

# --8<-- [start:registry_setup]
import substrait.dataframe as sub

reg = sub.ExtensionRegistry(load_default_extensions=True)
reg.register_extension_yaml("my_functions.yaml")  # from a YAML file
# or, from an already-parsed dict (must contain a "urn" field):
reg.register_extension_dict(definitions)
# --8<-- [end:registry_setup]

# --8<-- [start:pass_registry]
df = sub.read_named_table("t", {"x": sub.i64}, registry=reg)
# --8<-- [end:pass_registry]

# --8<-- [start:reach_functions]
myf = sub.functions_for(reg)
myf.my_double(sub.col("x"))

# equivalently, off a frame built with `reg`:
df.f.my_double(sub.col("x"))
# --8<-- [end:reach_functions]

# --8<-- [start:detail_class]
import substrait.dataframe as sub
import substrait.type_pb2 as stt
from google.protobuf.any_pb2 import Any


class MyLeaf(sub.ExtensionLeafDetail):
    type_url = "example.com/my.LeafDetail"

    def to_any(self) -> Any:
        payload = Any()
        payload.type_url = self.type_url
        # payload.value = ... serialize your fields ...
        return payload

    @classmethod
    def from_any(cls, detail: Any) -> "MyLeaf":
        return cls()  # ... deserialize your fields ...

    def derive_schema(self) -> stt.NamedStruct:
        return sub.named_struct(names=["x"], struct=sub.struct([sub.i64.non_null]))


# --8<-- [end:detail_class]


# Fixtures for the "building the relation" snippet: a single- and a multi-input
# detail class plus the frames they apply to.
class MySingle(sub.ExtensionSingleDetail):
    type_url = "example.com/my.SingleDetail"

    def to_any(self) -> Any:
        return Any(type_url=self.type_url)

    @classmethod
    def from_any(cls, detail: Any) -> "MySingle":
        return cls()

    def derive_schema(self, input: stt.Type.Struct) -> stt.NamedStruct:
        return sub.named_struct(names=["x"], struct=sub.struct([sub.i64.non_null]))


class MyMulti(sub.ExtensionMultiDetail):
    type_url = "example.com/my.MultiDetail"

    def to_any(self) -> Any:
        return Any(type_url=self.type_url)

    @classmethod
    def from_any(cls, detail: Any) -> "MyMulti":
        return cls()

    def derive_schema(self, inputs: "list[stt.Type.Struct]") -> stt.NamedStruct:
        return sub.named_struct(names=["x"], struct=sub.struct([sub.i64.non_null]))


base = sub.read_named_table("base", {"x": sub.i64.non_null})
other1 = sub.read_named_table("other1", {"x": sub.i64.non_null})
other2 = sub.read_named_table("other2", {"x": sub.i64.non_null})

# --8<-- [start:build_relation]
# leaf (a source): starts a new DataFrame
df = sub.extension_leaf(MyLeaf())

# single-input: applied to an existing frame
df = base.extension(MySingle())

# multi-input: this frame plus others
df = base.extension_multi([other1, other2], MyMulti())
# --8<-- [end:build_relation]

# --8<-- [start:register_relation]
reg.register_extension_relation(MyLeaf)
# --8<-- [end:register_relation]
