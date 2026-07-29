"""Runnable source for the snippets in ``docs/shared-subplans.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.

The ``assert``s inside the sections are part of the documented output: they pin
the plan shape the prose describes (one shared subtree, referenced twice).
"""

# --8<-- [start:cache]
import substrait.dataframe as sub

events = sub.read_named_table(
    "events", {"id": sub.i64, "user_id": sub.i64, "amount": sub.fp64}
).cache()

recent = events.filter(sub.col("amount") > 100)
older = events.filter(sub.col("amount") <= 100)

plan = recent.union(older).to_plan()
# --8<-- [end:cache]

# --8<-- [start:inspect]
# The cached subtree is a leading `rel` entry; the root references it.
assert [r.WhichOneof("rel_type") for r in plan.relations] == ["rel", "root"]
assert plan.relations[0].rel.HasField("read")

# Both union inputs reach the read through a ReferenceRel, not a second copy.
inputs = plan.relations[-1].root.input.set.inputs
assert all(i.filter.input.HasField("reference") for i in inputs)
# --8<-- [end:inspect]

# --8<-- [start:without_cache]
uncached = sub.read_named_table(
    "events", {"id": sub.i64, "user_id": sub.i64, "amount": sub.fp64}
)
inlined = (
    uncached.filter(sub.col("amount") > 100)
    .union(uncached.filter(sub.col("amount") <= 100))
    .to_plan()
)

# No shared subtree: the read is inlined into each branch.
assert [r.WhichOneof("rel_type") for r in inlined.relations] == ["root"]
# --8<-- [end:without_cache]

# --8<-- [start:hint_order]
# Right: annotate, then cache.
sub.read_named_table("events", {"id": sub.i64}).hint(row_count=1_000_000).cache()
# --8<-- [end:hint_order]

# --8<-- [start:hint_order_wrong]
try:
    sub.read_named_table("events", {"id": sub.i64}).cache().hint(
        row_count=1_000_000
    ).to_plan()
except TypeError as exc:
    print(exc)  # cannot attach a hint to a ReferenceRel ...
# --8<-- [end:hint_order_wrong]

# --8<-- [start:cache_chain]
# A cached frame is an ordinary DataFrame: keep chaining from it.
totals = events.aggregate(
    sub.col("user_id"), sub.f.sum(sub.col("amount")).alias("spend")
)
totals.filter(sub.col("spend") > 500).to_plan()
# --8<-- [end:cache_chain]
