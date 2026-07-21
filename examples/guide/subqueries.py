"""Runnable source for the snippets in ``docs/subqueries.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.

The ``threshold_df`` fixture (a single-column frame the ANY/ALL prose references
without defining) is created outside the section markers before use.
"""

# --8<-- [start:scalar_subquery]
import substrait.dataframe as sub

orders = sub.read_named_table("orders", {"id": sub.i64, "amount": sub.fp64})
avg_amount = orders.aggregate((), sub.f.avg(sub.col("amount")).alias("avg"))

# rows above the overall average
orders.filter(sub.col("amount") > sub.scalar_subquery(avg_amount)).to_plan()
# --8<-- [end:scalar_subquery]

# --8<-- [start:in_subquery]
customers = sub.read_named_table("customers", {"id": sub.i64})
recent = sub.read_named_table("recent_orders", {"cust_id": sub.i64})

customers.filter(sub.col("id").in_subquery(recent)).to_plan()
# --8<-- [end:in_subquery]

# --8<-- [start:exists_unique]
customers.filter(sub.exists(recent)).to_plan()
customers.filter(sub.unique(recent)).to_plan()
# --8<-- [end:exists_unique]

# Illustrative single-column frame the ANY/ALL comparisons draw thresholds from.
threshold_df = sub.read_named_table("thresholds", {"threshold": sub.fp64})

# --8<-- [start:any_all]
# amount greater than ANY row of the subquery (i.e. greater than the minimum)
orders.filter(sub.col("amount") > sub.any_(threshold_df)).to_plan()

# amount greater than ALL rows (i.e. greater than the maximum)
orders.filter(sub.col("amount") > sub.all_(threshold_df)).to_plan()
# --8<-- [end:any_all]

# --8<-- [start:correlated]
outer_df = sub.read_named_table("customers", {"id": sub.i64, "region": sub.string})
inner_df = sub.read_named_table("orders", {"cust_id": sub.i64})

# customers who have at least one order (correlated EXISTS)
outer_df.filter(
    sub.exists(inner_df.filter(sub.col("cust_id") == sub.outer("id")))
).to_plan()
# --8<-- [end:correlated]
