# Aggregations

Summarize rows with `group_by(...).agg(...)`. Aggregate functions come from the
[`f` namespace](functions.md); name each measure with `.alias(...)`.

## Group by and aggregate

```python
import substrait.dataframe as sub

df.group_by("region").agg(
    sub.f.sum(sub.col("amount")).alias("total"),
    sub.f.count(sub.col("amount")).alias("n"),
)
```

Group by multiple keys by passing several, and group the whole frame (a grand
total) by passing none:

```python
df.group_by("region", "product").agg(sub.f.sum(sub.col("amount")).alias("total"))
df.group_by().agg(sub.f.count(sub.col("id")).alias("rows"))
```

`group_by` keys may be column names or expressions.

## One-shot form

`aggregate` does the same thing in a single call — the grouping keys first, then
the measures:

```python
df.aggregate("region", sub.f.sum(sub.col("amount")).alias("total"))
df.aggregate(["region", "product"], sub.f.count(sub.col("id")).alias("n"))
```

## Modifying a measure

Aggregate measures support several modifiers, which chain:

```python
sub.f.count(sub.col("customer")).distinct().alias("unique_customers")
sub.f.sum(sub.col("amount")).filter(sub.col("status") == "paid").alias("paid_total")
sub.f.string_agg(sub.col("name"), sub.lit(", ")).order_by("name").alias("names")
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
# explicit grouping sets: by (region, product), by (region), and the grand total
df.group_by("region", "product", grouping_sets=[["region", "product"], ["region"], []]) \
  .agg(sub.f.sum(sub.col("amount")).alias("total"))

# ROLLUP: (region, product), (region), ()
df.rollup("region", "product").agg(sub.f.sum(sub.col("amount")).alias("total"))

# CUBE: every subset of the keys
df.cube("region", "product").agg(sub.f.sum(sub.col("amount")).alias("total"))
```

## Next

- [Window functions](window-functions.md) — aggregate without collapsing rows.
- [The function namespace](functions.md) — the full set of aggregate functions.
