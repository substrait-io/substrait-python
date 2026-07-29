# Subqueries

A subquery is another `DataFrame` used *inside an expression*. substrait-python
supports the full range of Substrait subquery forms — scalar, `IN`, `EXISTS`,
quantified comparisons, and correlated references.

## Scalar subquery

`scalar_subquery` yields the single value of a one-row, one-column subquery — use
it anywhere a scalar expression is expected:

```python
--8<-- "examples/guide/subqueries.py:scalar_subquery"
```

## IN a subquery

`Expr.in_subquery` tests membership against a subquery producing a single
column (`x IN (SELECT ...)`):

```python
--8<-- "examples/guide/subqueries.py:in_subquery"
```

For membership against a fixed set of literals, use
[`is_in`](expressions.md#null-and-membership-tests) instead.

## EXISTS and UNIQUE

`exists` is true when the subquery returns any row; `unique` is true when it has
no duplicate rows:

```python
--8<-- "examples/guide/subqueries.py:exists_unique"
```

These are most useful *correlated* — see below.

## Quantified comparisons (ANY / ALL)

Compare a value against every row of a subquery with `any_` / `all_`, used on
the right-hand side of a comparison operator:

```python
--8<-- "examples/guide/subqueries.py:any_all"
```

## Correlated subqueries

A correlated subquery references a column from the **enclosing** query. Use
`outer(name)` for that reference:

```python
--8<-- "examples/guide/subqueries.py:correlated"
```

Inside the inner frame, `sub.col("cust_id")` refers to the inner schema and
`sub.outer("id")` refers to the correlated `id` column from `outer_df`.

`steps_out` counts query-nesting levels outward and is **1-based**: `1` (the
default) is the immediately enclosing query, `2` the one outside that, and so on.
Substrait requires `steps_out >= 1`, so `0` raises:

```python
--8<-- "examples/guide/subqueries.py:nested_correlated"
```

!!! note "How correlated references are encoded"
    Where it can, the DataFrame layer emits correlated references **id-based** —
    as an `OuterReference.rel_reference` naming the enclosing relation's anchor
    rather than a `steps_out` hop count — which is robust to a plan being
    rewritten or re-nested. A reducing join's condition scope cannot be expressed
    that way and still uses `steps_out`. Both forms are read back by the builders
    and by schema inference, so plans from either convention round-trip.

    [Lateral joins](joins.md#lateral-join) take this further: their left handle
    removes the need to count levels at all.

## Next

- [Expressions](expressions.md) — the non-subquery expression forms.
- [Aggregations](aggregations.md) — build the scalar subqueries you compare against.
- [Joins](joins.md#lateral-join) — lateral joins, the row-by-row alternative to a
  correlated subquery.
