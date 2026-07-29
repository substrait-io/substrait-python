# Transformations

These verbs reshape a `DataFrame`'s rows and columns. Each returns a new
`DataFrame`, so they chain. They accept [`Expr`](expressions.md) objects, bare
column-name strings, and (where sensible) Python scalars.

## Projecting columns

`select` **replaces** the projection with exactly the columns you name;
`with_columns` **appends** new columns to the existing ones (Polars naming):

```python
--8<-- "examples/guide/transformations.py:project"
```

With `with_columns`, keyword arguments name the new columns; positional
arguments pass expressions through unchanged (alias them yourself if needed).

## Renaming and dropping

```python
--8<-- "examples/guide/transformations.py:rename_drop"
```

Both resolve the input schema, so an unknown column name raises rather than
silently doing nothing.

## Filtering rows

`filter` keeps rows where the predicate is true:

```python
--8<-- "examples/guide/transformations.py:filter_rows"
```

## Sorting

`sort` orders rows by one or more columns. `descending` and `nulls_last` are
each either a single bool (applied to every key) or a per-column list matching
the columns:

```python
--8<-- "examples/guide/transformations.py:sort"
```

## Limiting and paging

```python
--8<-- "examples/guide/transformations.py:limit_paging"
```

`top_n` fuses an order-by and a limit into a single `TopNRel` — the efficient
way to ask for "the N largest/smallest":

```python
--8<-- "examples/guide/transformations.py:top_n"
```

`with_ties` keeps rows tied with the n-th; `offset` is also supported.

## Unpivot (wide to long)

`unpivot` turns a set of columns into `variable`/`value` rows (an `ExpandRel`),
Polars-style. `index` columns are repeated on every output row, and the `on`
columns must share a type:

```python
--8<-- "examples/guide/transformations.py:unpivot"
```

## Hints

`hint` attaches non-semantic annotations to the current relation
(`RelCommon.Hint`) — optimizer statistics and naming. They are purely advisory
and do not change results:

```python
--8<-- "examples/guide/transformations.py:hints"
```

Not every relation can carry one: a `ReferenceRel` (from
[`cache()`](shared-subplans.md)) has no `RelCommon`, so hint *before* caching.

## Physical distribution

For engines that model partitioning, `ExchangeRel` verbs redistribute rows:

```python
--8<-- "examples/guide/transformations.py:distribution"
```

## Next

- [Joins](joins.md) — combine two DataFrames.
- [Aggregations](aggregations.md) — `group_by().agg()` and friends.
- [Set operations](set-operations.md) — union / intersect / except.
