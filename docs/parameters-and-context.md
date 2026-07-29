# Parameters & context variables

## Dynamic parameters

`parameter` builds a placeholder whose value is supplied at execution time — the
plan-level analog of a SQL bind parameter (`?` / `:name`). `index` is the
0-based position bound via the plan's parameter bindings; `type` is a
`proto.Type` or a bare type builder:

```python
--8<-- "examples/guide/parameters_and_context.py:parameter"
```

Give it a readable name with the optional `alias`:

```python
--8<-- "examples/guide/parameters_and_context.py:parameter_alias"
```

## Execution context variables

These resolve to values from the execution environment, not from the data:

```python
--8<-- "examples/guide/parameters_and_context.py:context_vars"
```

`current_timestamp` takes an optional `precision` (default `6`,
microseconds); all three take an optional `alias`:

```python
--8<-- "examples/guide/parameters_and_context.py:stamp_loaded_at"
```

A typical use is stamping rows or filtering by "today":

```python
--8<-- "examples/guide/parameters_and_context.py:filter_today"
```

## Next

- [Expressions](expressions.md) — combine these with operators and functions.
- [DDL & writes](ddl-and-writes.md) — statements that consume a built plan.
