"""Runnable source for the snippets in docs/consuming-plans.md.

The two engine-handoff snippets (the DuckDB / ADBC tabs) need network access and
an external engine, so they stay inline in the page and are exercised end to end
by ``examples/duckdb_example.py`` / ``examples/adbc_example.py`` (run by
``example.yml``) rather than here.
"""

# --8<-- [start:materialize]
import substrait.dataframe as sub

plan = (
    sub.read_named_table("customer", {"c_name": sub.string, "c_nationkey": sub.i32})
    .filter(sub.col("c_nationkey") == 3)
    .select("c_name")
    .to_plan()
)

payload = plan.SerializeToString()
# --8<-- [end:materialize]

# --8<-- [start:pretty_print]
from substrait.utils.display import pretty_print_plan

pretty_print_plan(plan, use_colors=True)
# --8<-- [end:pretty_print]

# --8<-- [start:roundtrip]
from substrait.proto import Plan

restored = Plan()
restored.ParseFromString(payload)
# --8<-- [end:roundtrip]
