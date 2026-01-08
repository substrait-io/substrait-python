import substrait.dataframe as sdf
from substrait.builders.plan import read_named_table
from substrait.builders.type import boolean, i64, named_struct, struct
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=True)

ns = named_struct(
    names=["id", "is_applicable"],
    struct=struct(types=[i64(nullable=False), boolean()], nullable=False),
)

table = read_named_table("example_table", ns)

frame = sdf.DataFrame(read_named_table("example_table", ns))
frame = frame.select(sdf.col("id"))
print(frame.to_substrait(registry))
