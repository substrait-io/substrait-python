"""Runnable source for the snippets in ``docs/transformations.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.

The page demonstrates each verb on a DataFrame ``df`` the prose assumes you
"already have". We define a realistic ``df`` fixture here -- outside the snippet
markers, so it runs but is not shown -- whose schema covers every column the
page references. Each shown verb ends in ``.to_plan()`` so the snippet builds a
real plan (which is what the test exercises).
"""

import substrait.dataframe as sub

# Fixture standing in for the ``df`` the prose assumes. Its schema covers every
# column referenced anywhere on the page (defined outside the markers, so it is
# not part of any shown snippet).
df = sub.read_named_table(
    "transactions",
    {
        "id": sub.i64,
        "name": sub.string,
        "qty": sub.i64,
        "age": sub.i64,
        "a": sub.i64,
        "old": sub.string,
        "debug": sub.string,
        "internal": sub.string,
        "region": sub.string.non_null,
        "amount": sub.fp64,
        "jan": sub.fp64,
        "feb": sub.fp64,
        "mar": sub.fp64,
    },
)

# --8<-- [start:project]
import substrait.dataframe as sub

df.select("id", "name").to_plan()  # keep only these two
df.select(sub.col("qty").alias("quantity")).to_plan()  # rename via alias

df.with_columns(next_year=sub.col("age") + 1).to_plan()  # append a computed column
df.with_columns(sub.col("a"), doubled=sub.col("a") * 2).to_plan()  # positional + named
# --8<-- [end:project]

# --8<-- [start:rename_drop]
df.rename(
    {"old": "new", "qty": "quantity"}
).to_plan()  # rename some; others pass through
df.drop("debug", "internal").to_plan()  # keep the rest, in order
# --8<-- [end:rename_drop]

# --8<-- [start:filter_rows]
df.filter(sub.col("age") > 25).to_plan()
df.filter((sub.col("age") > 25) & sub.col("name").is_not_null()).to_plan()
# --8<-- [end:filter_rows]

# --8<-- [start:sort]
df.sort("amount").to_plan()  # ascending, nulls last
df.sort("amount", descending=True).to_plan()
df.sort("region", "amount", descending=[False, True]).to_plan()
df.sort("amount", nulls_last=False).to_plan()
# --8<-- [end:sort]

# --8<-- [start:limit_paging]
df.limit(10).to_plan()  # first 10 rows
df.limit(10, offset=20).to_plan()  # 10 rows starting after the first 20
df.head(5).to_plan()  # alias for limit(5)
df.offset(100).to_plan()  # skip the first 100, keep the rest
# --8<-- [end:limit_paging]

# --8<-- [start:top_n]
df.top_n(10, by="amount", descending=True).to_plan()
df.top_n(
    10, by=["region", "amount"], descending=[False, True], with_ties=True
).to_plan()
# --8<-- [end:top_n]

# --8<-- [start:unpivot]
df.unpivot(
    on=["jan", "feb", "mar"],
    index="region",
    variable_name="month",
    value_name="sales",
).to_plan()
# --8<-- [end:unpivot]

# --8<-- [start:hints]
df.hint(row_count=1_000_000, record_size=64, alias="big_scan").to_plan()
df.hint(output_names=["a", "b", "c"]).to_plan()
# --8<-- [end:hints]

# --8<-- [start:distribution]
df.repartition(8).to_plan()  # round-robin into 8 partitions
df.broadcast().to_plan()  # broadcast every row to all partitions
# --8<-- [end:distribution]
