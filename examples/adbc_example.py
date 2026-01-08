# Install pyarrow, adbc-driver-manager and duckdb before running this example
# This example  currently can be run only with duckdb<=1.1.3, later versions of duckdb no longer support substrait in adbc
# /// script
# dependencies = [
#   "pyarrow==20.0.0",
#   "adbc-driver-manager==1.5.0",
#   "duckdb==1.1.3",
#   "substrait[extensions] @ file:///${PROJECT_ROOT}/"
# ]
# ///


import adbc_driver_duckdb.dbapi
import pyarrow
import pyarrow.substrait as pa_substrait

from substrait.builders.extended_expression import column, literal, scalar_function
from substrait.builders.plan import filter, read_named_table
from substrait.builders.type import i64
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry()

data = pyarrow.record_batch(
    [[1, 2, 3, 4], ["a", "b", "c", "d"]],
    names=["ints", "strs"],
)


def read_adbc_named_table(name: str, conn):
    pa_schema = conn.adbc_get_table_schema(name)
    substrait_schema = (
        pa_substrait.serialize_schema(pa_schema).to_pysubstrait().base_schema
    )
    return read_named_table(name, substrait_schema)


with adbc_driver_duckdb.dbapi.connect(":memory:") as conn:
    with conn.cursor() as cur:
        cur.adbc_ingest("AnswerToEverything", data)

        cur.executescript("INSTALL substrait;")
        cur.executescript("LOAD substrait;")

        table = read_adbc_named_table("AnswerToEverything", conn)
        table = filter(
            table,
            expression=scalar_function(
                "extension:io.substrait:functions_comparison",
                "gte",
                expressions=[column("ints"), literal(3, i64())],
            ),
        )

        cur.execute(table(registry).SerializeToString())
        print(cur.fetch_arrow_table())
