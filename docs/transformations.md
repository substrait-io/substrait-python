# Transformations

These verbs reshape a `DataFrame`'s rows and columns. Each returns a new
`DataFrame`, so they chain. They accept [`Expr`](expressions.md) objects, bare
column-name strings, and (where sensible) Python scalars.

## Projecting columns

`select` **replaces** the projection with exactly the columns you name;
`with_columns` **appends** new columns to the existing ones (Polars naming):

```python
import substrait.dataframe as sub

df.select("id", "name")                       # keep only these two
df.select(sub.col("qty").alias("quantity"))    # rename via alias

df.with_columns(next_year=sub.col("age") + 1)   # append a computed column
df.with_columns(sub.col("a"), doubled=sub.col("a") * 2)  # positional + named
```

With `with_columns`, keyword arguments name the new columns; positional
arguments pass expressions through unchanged (alias them yourself if needed).

## Renaming and dropping

```python
df.rename({"old": "new", "qty": "quantity"})   # rename some; others pass through
df.drop("debug", "internal")                     # keep the rest, in order
```

Both resolve the input schema, so an unknown column name raises rather than
silently doing nothing.

## Filtering rows

`filter` keeps rows where the predicate is true:

```python
df.filter(sub.col("age") > 25)
df.filter((sub.col("age") > 25) & sub.col("name").is_not_null())
```

## Sorting

`sort` orders rows by one or more columns. `descending` and `nulls_last` are
each either a single bool (applied to every key) or a per-column list matching
the columns:

```python
df.sort("amount")                                   # ascending, nulls last
df.sort("amount", descending=True)
df.sort("region", "amount", descending=[False, True])
df.sort("amount", nulls_last=False)
```

## Limiting and paging

```python
df.limit(10)             # first 10 rows
df.limit(10, offset=20)  # 10 rows starting after the first 20
df.head(5)               # alias for limit(5)
df.offset(100)           # skip the first 100, keep the rest
```

`top_n` fuses an order-by and a limit into a single `TopNRel` — the efficient
way to ask for "the N largest/smallest":

```python
df.top_n(10, by="amount", descending=True)
df.top_n(10, by=["region", "amount"], descending=[False, True], with_ties=True)
```

`with_ties` keeps rows tied with the n-th; `offset` is also supported.

## Unpivot (wide to long)

`unpivot` turns a set of columns into `variable`/`value` rows (an `ExpandRel`),
Polars-style. `index` columns are repeated on every output row, and the `on`
columns must share a type:

```python
df.unpivot(
    on=["jan", "feb", "mar"],
    index="region",
    variable_name="month",
    value_name="sales",
)
```

## Hints

`hint` attaches non-semantic annotations to the current relation
(`RelCommon.Hint`) — optimizer statistics and naming. They are purely advisory
and do not change results:

```python
df.hint(row_count=1_000_000, record_size=64, alias="big_scan")
df.hint(output_names=["a", "b", "c"])
```

## Physical distribution

For engines that model partitioning, `ExchangeRel` verbs redistribute rows:

```python
df.repartition(8)   # round-robin into 8 partitions
df.broadcast()       # broadcast every row to all partitions
```

## Next

- [Joins](joins.md) — combine two DataFrames.
- [Aggregations](aggregations.md) — `group_by().agg()` and friends.
- [Set operations](set-operations.md) — union / intersect / except.
