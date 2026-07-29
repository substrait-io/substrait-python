"""Runnable source for the snippets in ``docs/set-operations.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.

Fixtures defined outside the section markers (``q3``/``q4``, ``active``/
``subscribed``, ``all_users``/``banned_users``) stand in for the illustrative
names the prose references without defining; each shares the schema of the
frame it is combined with, as set operations require.
"""

# --8<-- [start:union]
import substrait.dataframe as sub

q1 = sub.read_named_table("sales_q1", {"region": sub.string, "amount": sub.fp64})
q2 = sub.read_named_table("sales_q2", {"region": sub.string, "amount": sub.fp64})

q1.union(q2).to_plan()  # UNION ALL (keeps duplicates)
q1.union(q2, distinct=True).to_plan()  # UNION (deduplicated)
# --8<-- [end:union]

# Illustrative frames the "more than one other" example unions with q1/q2.
q3 = sub.read_named_table("sales_q3", {"region": sub.string, "amount": sub.fp64})
q4 = sub.read_named_table("sales_q4", {"region": sub.string, "amount": sub.fp64})

# --8<-- [start:union_many]
q1.union(q2, q3, q4).to_plan()
# --8<-- [end:union_many]

# Illustrative frames for the intersect examples.
active = sub.read_named_table("active_users", {"user_id": sub.i64})
subscribed = sub.read_named_table("subscribed_users", {"user_id": sub.i64})

# --8<-- [start:intersect]
active.intersect(subscribed).to_plan()
active.intersect(subscribed, distinct=False).to_plan()
# --8<-- [end:intersect]

# Illustrative frames for the except examples.
all_users = sub.read_named_table("all_users", {"user_id": sub.i64})
banned_users = sub.read_named_table("banned_users", {"user_id": sub.i64})

# --8<-- [start:except_op]
all_users.except_(banned_users).to_plan()
all_users.except_(banned_users, distinct=False).to_plan()
# --8<-- [end:except_op]
