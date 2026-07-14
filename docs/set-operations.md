# Set operations

Combine the rows of several `DataFrame`s that share a schema. All inputs must
have the same column types as the frame you call the method on.

## Union

Concatenate rows. The default keeps duplicates (`UNION ALL`); pass
`distinct=True` for a set `UNION`:

```python
import substrait.dataframe as sub

q1 = sub.read_named_table("sales_q1", {"region": sub.string, "amount": sub.fp64})
q2 = sub.read_named_table("sales_q2", {"region": sub.string, "amount": sub.fp64})

q1.union(q2)                 # UNION ALL (keeps duplicates)
q1.union(q2, distinct=True)  # UNION (deduplicated)
```

You can pass more than one other frame:

```python
q1.union(q2, q3, q4)
```

## Intersect

Rows present in this frame **and** in every other. Defaults to the deduplicated
`INTERSECT`; pass `distinct=False` for `INTERSECT ALL`:

```python
active.intersect(subscribed)
active.intersect(subscribed, distinct=False)
```

## Except

Rows in this frame that are **not** in any of the others (SQL `EXCEPT`).
Defaults to deduplicated; pass `distinct=False` for `EXCEPT ALL`. The method is
`except_` (with a trailing underscore, since `except` is a Python keyword):

```python
all_users.except_(banned_users)
all_users.except_(banned_users, distinct=False)
```

## Next

- [Joins](joins.md) — combine columns rather than rows.
- [Subqueries](subqueries.md) — set membership as an expression (`is_in`,
  `in_subquery`, `exists`).
