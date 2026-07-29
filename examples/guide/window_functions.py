"""Runnable source for the snippets in ``docs/window-functions.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.

The page windows over a DataFrame ``df`` the prose assumes you "already have".
We define a realistic ``df`` fixture here -- outside the snippet markers, so it
runs but is not shown -- whose schema covers every column the page references.
"""

import substrait.dataframe as sub

# Fixture standing in for the ``df`` the prose assumes. Its schema covers every
# column referenced anywhere on the page (defined outside the markers, so it is
# not part of any shown snippet).
df = sub.read_named_table(
    "events",
    {
        "region": sub.string.non_null,
        "product": sub.string.non_null,
        "amount": sub.fp64,
        "ts": sub.i64,
    },
)

# --8<-- [start:basic]
import substrait.dataframe as sub

df.with_columns(
    rn=sub.f.row_number().over(partition_by="region", order_by="ts"),
).to_plan()
# --8<-- [end:basic]

# --8<-- [start:partition_order]
sub.f.rank().over(
    partition_by=["region", "product"],
    order_by="amount",
    descending=True,
)
# --8<-- [end:partition_order]

# --8<-- [start:frames]
# the latest amount seen so far: start of partition through the current row
sub.f.last_value(sub.col("amount")).over(order_by="ts", rows=(None, 0))

# value from the immediately preceding row within a 3-row window
sub.f.first_value(sub.col("amount")).over(order_by="ts", rows=(-1, 1))

# the final amount in the partition: current row onward
sub.f.last_value(sub.col("amount")).over(order_by="ts", rows=(0, None))
# --8<-- [end:frames]
