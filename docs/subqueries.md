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
`outer(name)` for that reference. `steps_out` counts nesting levels outward
(`0` = the immediately enclosing query, the default):

```python
--8<-- "examples/guide/subqueries.py:correlated"
```

Inside the inner frame, `sub.col("cust_id")` refers to the inner schema and
`sub.outer("id")` refers to the correlated `id` column from `outer_df`.

## Next

- [Expressions](expressions.md) — the non-subquery expression forms.
- [Aggregations](aggregations.md) — build the scalar subqueries you compare against.
