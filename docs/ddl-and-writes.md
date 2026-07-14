# DDL & writes

Beyond read queries, the API builds plans that **create, drop, update, and write
to** tables and views. Each returns a terminal `DataFrame`; call `.to_plan()` to
materialize it.

## Writing query results to a table

`write_named_table` turns a query into a write sink (`WriteRel`). `op` is the
write operation and `mode` controls what happens when the table already exists:

```python
import substrait.dataframe as sub

summary = (
    sub.read_named_table("orders", {"region": sub.string, "amount": sub.fp64})
    .group_by("region")
    .agg(sub.f.sum(sub.col("amount")).alias("total"))
)

plan = summary.write_named_table("region_totals", op="ctas", mode="replace").to_plan()
```

- **`op`** — `ctas` (create-table-as-select, default) or `insert`.
- **`mode`** — behavior if the target exists: `error` (default), `append`,
  `replace`, or `ignore`.

## Create table / view

```python
# CREATE TABLE region_totals (region string, total fp64)
sub.create_table("region_totals", {"region": sub.string, "total": sub.fp64})

# CREATE OR REPLACE
sub.create_table("region_totals", {"region": sub.string}, replace=True)

# CREATE VIEW backed by a query (a DataFrame)
big_orders = sub.read_named_table("orders", {"amount": sub.fp64}) \
    .filter(sub.col("amount") > 1000)
sub.create_view("big_orders", big_orders)
```

## Drop table / view

Pass `if_exists=True` for the `IF EXISTS` variant:

```python
sub.drop_table("region_totals")
sub.drop_table("region_totals", if_exists=True)
sub.drop_view("big_orders", if_exists=True)
```

## Update

`update_table` builds an `UPDATE` statement. `assignments` maps a target column
(by name or index) to a new-value expression, applied where `where` holds (all
rows if omitted):

```python
sub.update_table(
    "orders",
    {"id": sub.i64, "amount": sub.fp64, "status": sub.string},
    assignments={"amount": sub.col("amount") * 1.1},
    where=sub.col("status") == "pending",
)
```

The schema you pass describes the target table so the assignment targets and
`where` predicate can be resolved against it.

## Next

- [Consuming plans](consuming-plans.md) — hand the built plan to an engine.
- [Custom extensions](custom-extensions.md) — extend beyond the built-in relations.
