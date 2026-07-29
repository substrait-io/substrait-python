# Aggregations

Summarize rows with `group_by(...).agg(...)`. Aggregate functions come from the
[`f` namespace](functions.md); name each measure with `.alias(...)`.

## Group by and aggregate

```python
--8<-- "examples/guide/aggregations.py:group_agg"
```

Group by multiple keys by passing several, and group the whole frame (a grand
total) by passing none:

```python
--8<-- "examples/guide/aggregations.py:multi_key_and_grand_total"
```

`group_by` keys may be column names or expressions.

## One-shot form

`aggregate` does the same thing in a single call — the grouping keys first, then
the measures:

```python
--8<-- "examples/guide/aggregations.py:one_shot"
```

## Modifying a measure

Aggregate measures support several modifiers, which chain:

```python
--8<-- "examples/guide/aggregations.py:measure_modifiers"
```

- **`.distinct()`** — operate on distinct inputs (`COUNT(DISTINCT x)`).
- **`.filter(predicate)`** — restrict this aggregate to matching rows
  (SQL `agg(x) FILTER (WHERE ...)`). Returns a `Measure`, only meaningful inside
  `agg(...)`.
- **`.order_by(*keys, descending=, nulls_last=)`** — order the inputs to an
  order-sensitive aggregate.
- **`.alias(name)`** — name the output column.

## Grouping sets, rollup, and cube

For multiple grouping levels in one aggregation, pass explicit `grouping_sets`
(lists of key names or positions into the keys), or use the `rollup` / `cube`
shortcuts:

```python
--8<-- "examples/guide/aggregations.py:grouping_sets"
```

## Next

- [Window functions](window-functions.md) — aggregate without collapsing rows.
- [The function namespace](functions.md) — the full set of aggregate functions.
