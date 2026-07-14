# Parameters & context variables

## Dynamic parameters

`parameter` builds a placeholder whose value is supplied at execution time — the
plan-level analog of a SQL bind parameter (`?` / `:name`). `index` is the
0-based position bound via the plan's parameter bindings; `type` is a
`proto.Type` or a bare type builder:

```python
import substrait.dataframe as sub

orders = sub.read_named_table("orders", {"amount": sub.fp64, "region": sub.string})

# keep rows above a threshold provided at runtime
orders.filter(sub.col("amount") > sub.parameter(0, sub.fp64))
```

Give it a readable name with the optional `alias`:

```python
sub.parameter(0, sub.fp64, alias="min_amount")
```

## Execution context variables

These resolve to values from the execution environment, not from the data:

```python
sub.current_timestamp()   # the query's execution timestamp (precision_timestamp_tz)
sub.current_date()         # the query's execution date
sub.current_timezone()     # the query's execution timezone (a string)
```

`current_timestamp` takes an optional `precision` (default `6`,
microseconds); all three take an optional `alias`:

```python
orders.with_columns(loaded_at=sub.current_timestamp(precision=3, alias="loaded_at"))
```

A typical use is stamping rows or filtering by "today":

```python
events = sub.read_named_table("events", {"ts": sub.date, "kind": sub.string})
events.filter(sub.col("ts") == sub.current_date())
```

## Next

- [Expressions](expressions.md) — combine these with operators and functions.
- [DDL & writes](ddl-and-writes.md) — statements that consume a built plan.
