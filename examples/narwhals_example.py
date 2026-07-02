# Example of the `substrait.narwhals` integration layer: drive Substrait plan
# construction through Narwhals (`nw.from_native`), so backend-agnostic Narwhals
# code compiles to a Substrait plan.
#
# For building plans directly (without Narwhals), see `api_example.py`, which
# uses the Substrait-native DataFrame in `substrait.api` / `substrait.frame`.
#
# /// script
# dependencies = [
#   "narwhals==2.9.0",
#   "substrait[extensions] @ file:///${PROJECT_ROOT}/"
# ]
# ///

import narwhals as nw
from narwhals.typing import FrameT

import substrait.narwhals as sn
from substrait.builders.plan import read_named_table
from substrait.builders.type import boolean, i64, named_struct, struct
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=True)

ns = named_struct(
    names=["id", "is_applicable"],
    struct=struct(types=[i64(nullable=False), boolean()], nullable=False),
)

# Wrap the Substrait Narwhals backend and drive it with the Narwhals API.
lazy_frame: FrameT = nw.from_native(sn.DataFrame(read_named_table("example_table", ns)))

lazy_frame = lazy_frame.select(nw.col("id").abs(), new_id=nw.col("id"))

df: sn.DataFrame = lazy_frame.to_native()

print(df.to_substrait(registry))
