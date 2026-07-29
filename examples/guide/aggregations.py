"""Runnable source for the snippets in ``docs/aggregations.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.

The page summarizes a DataFrame ``df`` the prose assumes you "already have". We
define a realistic ``df`` fixture here -- outside the snippet markers, so it
runs but is not shown -- whose schema covers every column the page references.
"""

import substrait.dataframe as sub

# Fixture standing in for the ``df`` the prose assumes. Its schema covers every
# column referenced anywhere on the page (defined outside the markers, so it is
# not part of any shown snippet).
df = sub.read_named_table(
    "sales",
    {
        "region": sub.string.non_null,
        "product": sub.string.non_null,
        "amount": sub.fp64,
        "id": sub.i64,
        "customer": sub.string,
        "status": sub.string,
        "name": sub.string,
    },
)

# --8<-- [start:group_agg]
import substrait.dataframe as sub

df.group_by("region").agg(
    sub.f.sum(sub.col("amount")).alias("total"),
    sub.f.count(sub.col("amount")).alias("n"),
).to_plan()
# --8<-- [end:group_agg]

# --8<-- [start:multi_key_and_grand_total]
df.group_by("region", "product").agg(
    sub.f.sum(sub.col("amount")).alias("total")
).to_plan()
df.group_by().agg(sub.f.count(sub.col("id")).alias("rows")).to_plan()
# --8<-- [end:multi_key_and_grand_total]

# --8<-- [start:one_shot]
df.aggregate("region", sub.f.sum(sub.col("amount")).alias("total")).to_plan()
df.aggregate(["region", "product"], sub.f.count(sub.col("id")).alias("n")).to_plan()
# --8<-- [end:one_shot]

# --8<-- [start:measure_modifiers]
sub.f.count(sub.col("customer")).distinct().alias("unique_customers")
sub.f.sum(sub.col("amount")).filter(sub.col("status") == "paid").alias("paid_total")
sub.f.string_agg(sub.col("name"), sub.lit(", ")).order_by("name").alias("names")
# --8<-- [end:measure_modifiers]

# --8<-- [start:grouping_sets]
# explicit grouping sets: by (region, product), by (region), and the grand total
df.group_by(
    "region", "product", grouping_sets=[["region", "product"], ["region"], []]
).agg(sub.f.sum(sub.col("amount")).alias("total")).to_plan()

# ROLLUP: (region, product), (region), ()
df.rollup("region", "product").agg(
    sub.f.sum(sub.col("amount")).alias("total")
).to_plan()

# CUBE: every subset of the keys
df.cube("region", "product").agg(sub.f.sum(sub.col("amount")).alias("total")).to_plan()
# --8<-- [end:grouping_sets]
