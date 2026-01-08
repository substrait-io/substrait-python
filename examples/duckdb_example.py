# Install duckdb and pyarrow before running this example
# /// script
# dependencies = [
#   "pyarrow==20.0.0",
#   "duckdb==1.2.1",
#   "substrait[extensions] @ file:///${PROJECT_ROOT}/"
# ]
# ///


import duckdb
import pyarrow.substrait as pa_substrait

from substrait.builders.extended_expression import column, literal, scalar_function
from substrait.builders.plan import filter, read_named_table, select
from substrait.builders.type import i32
from substrait.extension_registry import ExtensionRegistry

try:
    duckdb.install_extension("substrait")
except duckdb.duckdb.HTTPException:
    duckdb.install_extension("substrait", repository="community")
duckdb.load_extension("substrait")

duckdb.install_extension("tpch")
duckdb.load_extension("tpch")

duckdb.sql("CALL dbgen(sf = 1);")

registry = ExtensionRegistry(load_default_extensions=True)


def read_duckdb_named_table(name: str, conn):
    pa_schema = conn.sql(f"SELECT * FROM {name} LIMIT 0").arrow().schema
    substrait_schema = (
        pa_substrait.serialize_schema(pa_schema).to_pysubstrait().base_schema
    )
    return read_named_table(name, substrait_schema)


table = read_duckdb_named_table("customer", duckdb)
table = filter(
    table,
    expression=scalar_function(
        "extension:io.substrait:functions_comparison",
        "equal",
        expressions=[column("c_nationkey"), literal(3, i32())],
    ),
)
table = select(
    table, expressions=[column("c_name"), column("c_address"), column("c_nationkey")]
)
sql = "CALL from_substrait(?)"
print(duckdb.sql(sql, params=[table(registry).SerializeToString()]))
