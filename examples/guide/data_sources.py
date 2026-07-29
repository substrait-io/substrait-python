"""Runnable source for the snippets in docs/data-sources.md.

The last two snippets are custom-source teasers (covered fully in
docs/custom-extensions.md); the ``my_any_detail`` payload and ``MyLeafDetail``
class they need are defined here as hidden fixtures so the shown code runs.
"""

# --8<-- [start:named_table]
import substrait.dataframe as sub

people = sub.read_named_table(
    "people", {"id": sub.i64.non_null, "name": sub.string, "age": sub.i64}
)
# --8<-- [end:named_table]

# --8<-- [start:multipart_name]
sub.read_named_table(["main", "public", "people"], {"id": sub.i64})
# --8<-- [end:multipart_name]

# --8<-- [start:from_records]
df = sub.from_records(
    [
        {"id": 1, "name": "Ada"},
        {"id": 2, "name": "Alan"},
        (3, None),  # positional; name is a typed null
    ],
    {"id": sub.i64.non_null, "name": sub.string},
)
# --8<-- [end:from_records]

# --8<-- [start:files]
sub.read_parquet("data/events.parquet", {"ts": sub.i64, "kind": sub.string})
sub.read_orc(["a.orc", "b.orc"], {"x": sub.i64})
sub.read_arrow("table.arrow", {"x": sub.i64})
# --8<-- [end:files]

# --8<-- [start:csv]
sub.read_csv(
    "data/people.csv",
    {"id": sub.i64, "name": sub.string},
    delimiter=",",  # use "\t" for TSV
    header_lines_to_skip=1,  # skip the header row
)
# --8<-- [end:csv]

# Fixtures for the custom-source teasers below (see docs/custom-extensions.md).
import substrait.type_pb2 as stt
from google.protobuf.any_pb2 import Any

my_any_detail = Any(type_url="example.com/my.TableDetail")


class MyLeafDetail(sub.ExtensionLeafDetail):
    type_url = "example.com/my.LeafDetail"

    def to_any(self) -> Any:
        return Any(type_url=self.type_url)

    @classmethod
    def from_any(cls, detail: Any) -> "MyLeafDetail":
        return cls()

    def derive_schema(self) -> stt.NamedStruct:
        return sub.named_struct(names=["x"], struct=sub.struct([sub.i64.non_null]))


# --8<-- [start:read_extension_table]
sub.read_extension_table({"x": sub.i64}, my_any_detail)
# --8<-- [end:read_extension_table]

# --8<-- [start:extension_leaf]
sub.extension_leaf(MyLeafDetail())
# --8<-- [end:extension_leaf]
