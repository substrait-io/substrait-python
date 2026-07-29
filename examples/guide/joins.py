"""Runnable source for the snippets in ``docs/joins.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.

Fixtures defined outside the section markers (``regions``) stand in for the
illustrative names the prose references without defining.
"""

# --8<-- [start:logical_join]
import substrait.dataframe as sub

customers = sub.read_named_table(
    "customers", {"cust_id": sub.i64, "region": sub.string, "name": sub.string}
)
orders = sub.read_named_table(
    "orders",
    {
        "order_id": sub.i64,
        "cust_ref": sub.i64,
        "region": sub.string,
        "amount": sub.fp64,
    },
)

joined = customers.join(
    orders,
    on=sub.col("cust_id") == sub.col("cust_ref"),
    how="inner",
)
# --8<-- [end:logical_join]

joined.to_plan()  # validation (hidden): the assigned `joined` builds a real plan

# --8<-- [start:post_filter]
customers.join(
    orders,
    on=sub.col("cust_id") == sub.col("cust_ref"),
    post_filter=sub.col("amount") > 100,
).to_plan()
# --8<-- [end:post_filter]

# Illustrative table the "Cross join" prose references without defining.
regions = sub.read_named_table("regions", {"region_id": sub.i64, "region": sub.string})

# --8<-- [start:cross_join]
customers.cross_join(regions).to_plan()
# --8<-- [end:cross_join]

# --8<-- [start:lateral_join]
# For each customer, their own orders: the right frame is built as a function of
# a handle to the left row, and `lat.col(...)` is a correlated reference to it.
customers.lateral_join(
    lambda lat: orders.filter(sub.col("cust_ref") == lat.col("cust_id")),
    how="inner",
).to_plan()
# --8<-- [end:lateral_join]

# --8<-- [start:lateral_join_on]
customers.lateral_join(
    lambda lat: orders.filter(sub.col("cust_ref") == lat.col("cust_id")),
    how="left",
    on=sub.col("amount") > 100,
).to_plan()
# --8<-- [end:lateral_join_on]

# Illustrative third table for the nested-lateral example.
shipments = sub.read_named_table(
    "shipments", {"order_ref": sub.i64, "carrier": sub.string}
)

# --8<-- [start:lateral_join_nested]
# Each handle names its own left input, so nesting needs no depth counting: the
# innermost filter correlates on both the order (`o`) and the customer (`c`).
customers.lateral_join(
    lambda c: orders.lateral_join(
        lambda o: shipments.filter(sub.col("order_ref") == o.col("order_id")),
        how="inner",
    ).filter(sub.col("cust_ref") == c.col("cust_id")),
    how="inner",
).to_plan()
# --8<-- [end:lateral_join_nested]

# --8<-- [start:disambiguation]
left = customers.rename({"region": "cust_region"})
right = orders.rename({"region": "order_region"})
left.join(right, on=sub.col("cust_id") == sub.col("cust_ref")).to_plan()
# --8<-- [end:disambiguation]

# --8<-- [start:nested_loop_join]
customers.nested_loop_join(
    orders, on=sub.col("cust_id") == sub.col("cust_ref"), how="inner"
).to_plan()
# --8<-- [end:nested_loop_join]

# --8<-- [start:physical_equi_joins]
customers.hash_join(orders, left_on="cust_id", right_on="cust_ref").to_plan()
customers.merge_join(
    orders, left_on=["cust_id", "region"], right_on=["cust_ref", "region"], how="left"
).to_plan()
# --8<-- [end:physical_equi_joins]

# --8<-- [start:equi_join_predicates]
customers.hash_join(
    orders,
    left_on="cust_id",
    right_on="cust_ref",
    # evaluated alongside the key equalities, as part of the match
    residual=sub.col("amount") > 50,
    # applied to the join output, after matching
    post_filter=sub.col("region") == "EMEA",
).to_plan()
# --8<-- [end:equi_join_predicates]
