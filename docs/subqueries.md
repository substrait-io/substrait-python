# Subqueries

A subquery is another `DataFrame` used *inside an expression*. substrait-python
supports the full range of Substrait subquery forms — scalar, `IN`, `EXISTS`,
quantified comparisons, and correlated references.

## Scalar subquery

`scalar_subquery` yields the single value of a one-row, one-column subquery — use
it anywhere a scalar expression is expected:

```python
import substrait.dataframe as sub

orders = sub.read_named_table("orders", {"id": sub.i64, "amount": sub.fp64})
avg_amount = orders.aggregate((), sub.f.avg(sub.col("amount")).alias("avg"))

# rows above the overall average
orders.filter(sub.col("amount") > sub.scalar_subquery(avg_amount))
```

## IN a subquery

`Expr.in_subquery` tests membership against a subquery producing a single
column (`x IN (SELECT ...)`):

```python
customers = sub.read_named_table("customers", {"id": sub.i64})
recent = sub.read_named_table("recent_orders", {"cust_id": sub.i64})

customers.filter(sub.col("id").in_subquery(recent))
```

For membership against a fixed set of literals, use
[`is_in`](expressions.md#null-and-membership-tests) instead.

## EXISTS and UNIQUE

`exists` is true when the subquery returns any row; `unique` is true when it has
no duplicate rows:

```python
customers.filter(sub.exists(recent))
customers.filter(sub.unique(recent))
```

These are most useful *correlated* — see below.

## Quantified comparisons (ANY / ALL)

Compare a value against every row of a subquery with `any_` / `all_`, used on
the right-hand side of a comparison operator:

```python
# amount greater than ANY row of the subquery (i.e. greater than the minimum)
orders.filter(sub.col("amount") > sub.any_(threshold_df))

# amount greater than ALL rows (i.e. greater than the maximum)
orders.filter(sub.col("amount") > sub.all_(threshold_df))
```

## Correlated subqueries

A correlated subquery references a column from the **enclosing** query. Use
`outer(name)` for that reference. `steps_out` counts nesting levels outward
(`0` = the immediately enclosing query, the default):

```python
outer_df = sub.read_named_table("customers", {"id": sub.i64, "region": sub.string})
inner_df = sub.read_named_table("orders", {"cust_id": sub.i64})

# customers who have at least one order (correlated EXISTS)
outer_df.filter(
    sub.exists(inner_df.filter(sub.col("cust_id") == sub.outer("id")))
)
```

Inside the inner frame, `sub.col("cust_id")` refers to the inner schema and
`sub.outer("id")` refers to the correlated `id` column from `outer_df`.

## Next

- [Expressions](expressions.md) — the non-subquery expression forms.
- [Aggregations](aggregations.md) — build the scalar subqueries you compare against.
