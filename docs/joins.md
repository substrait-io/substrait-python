# Joins

Combine two `DataFrame`s. The logical `join` is what you want most of the time;
the physical variants (`hash_join`, `merge_join`, `nested_loop_join`) exist for
when you need to pin a specific algorithm.

## Logical join

`join` takes another DataFrame, an `on` expression, and a `how` string:

```python
--8<-- "examples/guide/joins.py:logical_join"
```

The `on` expression is evaluated against the **concatenation** of the left and
right schemas — columns from both inputs are referenced by name. An optional
`post_filter` predicate is applied to the join output:

```python
--8<-- "examples/guide/joins.py:post_filter"
```

### Join types

`how` accepts all twelve `JoinRel` variants:

| `how` | Meaning |
|-------|---------|
| `inner` | rows with a match on both sides |
| `outer` | all rows from both sides |
| `left` / `right` | all rows from one side, matched where possible |
| `left_semi` / `right_semi` | rows from one side that have a match (no right columns) |
| `left_anti` / `right_anti` | rows from one side that have **no** match |
| `left_single` / `right_single` | at most one match per row (runtime error on multiple) |
| `left_mark` / `right_mark` | append a nullable-boolean column flagging whether a partner exists |

## Cross join

The Cartesian product — every left row paired with every right row:

```python
--8<-- "examples/guide/joins.py:cross_join"
```

## Column disambiguation

Substrait references columns positionally, so overlapping column names across
the two inputs are kept as-is; nothing is auto-suffixed. Disambiguate explicitly
with [`rename`](transformations.md#renaming-and-dropping) / `drop` on either
input before joining, or on the result:

```python
--8<-- "examples/guide/joins.py:disambiguation"
```

## Physical joins

When you want to dictate the execution strategy rather than leave it to the
consumer, use the physical variants. All of them accept the same `how` values as
`join`.

**Nested-loop join** evaluates an arbitrary predicate over the Cartesian product
(the only physical join that supports non-equi conditions):

```python
--8<-- "examples/guide/joins.py:nested_loop_join"
```

**Hash join** and **merge join** are equi-joins on key columns. `left_on` /
`right_on` are column names or indices; `right_on` defaults to `left_on`. Merge
join assumes its inputs are already sorted on the keys:

```python
--8<-- "examples/guide/joins.py:physical_equi_joins"
```

## Next

- [Aggregations](aggregations.md) — summarize the joined rows.
- [Set operations](set-operations.md) — union / intersect / except.
- [Subqueries](subqueries.md) — correlated and uncorrelated subquery expressions.
