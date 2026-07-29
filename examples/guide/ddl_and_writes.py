"""Runnable source for the snippets in ``docs/ddl-and-writes.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.
"""

# --8<-- [start:write_named_table]
import substrait.dataframe as sub

summary = (
    sub.read_named_table("orders", {"region": sub.string, "amount": sub.fp64})
    .group_by("region")
    .agg(sub.f.sum(sub.col("amount")).alias("total"))
)

plan = summary.write_named_table("region_totals", op="ctas", mode="replace").to_plan()
# --8<-- [end:write_named_table]

# --8<-- [start:create_table_view]
# CREATE TABLE region_totals (region string, total fp64)
sub.create_table("region_totals", {"region": sub.string, "total": sub.fp64})

# CREATE OR REPLACE
sub.create_table("region_totals", {"region": sub.string}, replace=True)

# CREATE VIEW backed by a query (a DataFrame)
big_orders = sub.read_named_table("orders", {"amount": sub.fp64}).filter(
    sub.col("amount") > 1000
)
sub.create_view("big_orders", big_orders)
# --8<-- [end:create_table_view]

# --8<-- [start:drop]
sub.drop_table("region_totals")
sub.drop_table("region_totals", if_exists=True)
sub.drop_view("big_orders", if_exists=True)
# --8<-- [end:drop]

# --8<-- [start:update]
sub.update_table(
    "orders",
    {"id": sub.i64, "amount": sub.fp64, "status": sub.string},
    assignments={"amount": sub.col("amount") * 1.1},
    where=sub.col("status") == "pending",
)
# --8<-- [end:update]
