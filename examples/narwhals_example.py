# Install duckdb and pyarrow before running this example
# /// script
# dependencies = [
#   "narwhals==2.9.0",
#   "substrait[extensions] @ file:///${PROJECT_ROOT}/"
# ]
# ///

from substrait.builders.plan import read_named_table
from substrait.builders.type import i64, boolean, struct, named_struct
from substrait.extension_registry import ExtensionRegistry

from narwhals.typing import FrameT
import narwhals as nw
import substrait.dataframe as sdf


registry = ExtensionRegistry(load_default_extensions=True)

ns = named_struct(
    names=["id", "is_applicable"],
    struct=struct(types=[i64(nullable=False), boolean()], nullable=False),
)

table = read_named_table("example_table", ns)


lazy_frame: FrameT = nw.from_native(
    sdf.DataFrame(read_named_table("example_table", ns))
)

lazy_frame = lazy_frame.select(nw.col("id").abs(), new_id=nw.col("id"))

df: sdf.DataFrame = lazy_frame.to_native()

print(df.to_substrait(registry))
