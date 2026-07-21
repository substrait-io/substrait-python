# Set operations

Combine the rows of several `DataFrame`s that share a schema. All inputs must
have the same column types as the frame you call the method on.

## Union

Concatenate rows. The default keeps duplicates (`UNION ALL`); pass
`distinct=True` for a set `UNION`:

```python
--8<-- "examples/guide/set_operations.py:union"
```

You can pass more than one other frame:

```python
--8<-- "examples/guide/set_operations.py:union_many"
```

## Intersect

Rows present in this frame **and** in every other. Defaults to the deduplicated
`INTERSECT`; pass `distinct=False` for `INTERSECT ALL`:

```python
--8<-- "examples/guide/set_operations.py:intersect"
```

## Except

Rows in this frame that are **not** in any of the others (SQL `EXCEPT`).
Defaults to deduplicated; pass `distinct=False` for `EXCEPT ALL`. The method is
`except_` (with a trailing underscore, since `except` is a Python keyword):

```python
--8<-- "examples/guide/set_operations.py:except_op"
```

## Next

- [Joins](joins.md) — combine columns rather than rows.
- [Subqueries](subqueries.md) — set membership as an expression (`is_in`,
  `in_subquery`, `exists`).
