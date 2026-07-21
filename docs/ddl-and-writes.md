# DDL & writes

Beyond read queries, the API builds plans that **create, drop, update, and write
to** tables and views. Each returns a terminal `DataFrame`; call `.to_plan()` to
materialize it.

## Writing query results to a table

`write_named_table` turns a query into a write sink (`WriteRel`). `op` is the
write operation and `mode` controls what happens when the table already exists:

```python
--8<-- "examples/guide/ddl_and_writes.py:write_named_table"
```

- **`op`** — `ctas` (create-table-as-select, default) or `insert`.
- **`mode`** — behavior if the target exists: `error` (default), `append`,
  `replace`, or `ignore`.

## Create table / view

```python
--8<-- "examples/guide/ddl_and_writes.py:create_table_view"
```

## Drop table / view

Pass `if_exists=True` for the `IF EXISTS` variant:

```python
--8<-- "examples/guide/ddl_and_writes.py:drop"
```

## Update

`update_table` builds an `UPDATE` statement. `assignments` maps a target column
(by name or index) to a new-value expression, applied where `where` holds (all
rows if omitted):

```python
--8<-- "examples/guide/ddl_and_writes.py:update"
```

The schema you pass describes the target table so the assignment targets and
`where` predicate can be resolved against it.

## Next

- [Consuming plans](consuming-plans.md) — hand the built plan to an engine.
- [Custom extensions](custom-extensions.md) — extend beyond the built-in relations.
