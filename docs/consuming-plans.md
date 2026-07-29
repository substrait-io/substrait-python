# Consuming plans

substrait-python **produces** plans; it does not execute them. Once you have a
`proto.Plan`, hand it to a Substrait consumer to run.

## Materialize and serialize

`.to_plan()` returns a `substrait.proto.Plan`; `SerializeToString()` turns it
into the bytes a consumer accepts:

```python
--8<-- "examples/guide/consuming_plans.py:materialize"
```

`DataFrame.to_substrait(registry=...)` is an alias kept for parity with the
[Narwhals wrapper](#relationship-to-narwhals); it materializes against a given
registry.

## Inspecting a plan

The bundled pretty printer renders the plan as a compact tree — far more
readable than the raw protobuf text:

```python
--8<-- "examples/guide/consuming_plans.py:pretty_print"
```

## Handing off to an engine

The [`examples/`](https://github.com/substrait-io/substrait-python/tree/main/examples)
directory has runnable end-to-end scripts. In short, most engines take the
serialized bytes:

=== "DuckDB"

    ```python
    import duckdb

    duckdb.install_extension("substrait")
    duckdb.load_extension("substrait")
    duckdb.sql("CALL from_substrait(?)", params=[plan.SerializeToString()])
    ```

    See [`examples/duckdb_example.py`](https://github.com/substrait-io/substrait-python/blob/main/examples/duckdb_example.py).

=== "ADBC"

    ```python
    import adbc_driver_duckdb.dbapi

    with adbc_driver_duckdb.dbapi.connect(":memory:") as conn, conn.cursor() as cur:
        cur.executescript("INSTALL substrait;")
        cur.executescript("LOAD substrait;")
        cur.execute(plan.SerializeToString())
        print(cur.fetch_arrow_table())
    ```

    See [`examples/adbc_example.py`](https://github.com/substrait-io/substrait-python/blob/main/examples/adbc_example.py).

!!! tip "Matching a real table's schema"
    The examples read a table's Arrow schema from the engine and convert it via
    `pyarrow.substrait.serialize_schema(...).to_pysubstrait().base_schema`, then
    feed that `NamedStruct` straight into `read_named_table`. That keeps the plan
    schema exactly aligned with what the engine will resolve.

## Round-tripping

A serialized plan loads back with the generated protobuf class — useful for
tests and for consuming plans other producers emit:

```python
--8<-- "examples/guide/consuming_plans.py:roundtrip"
```

## Relationship to Narwhals

`substrait.dataframe` is the **native** fluent frame you call directly.
`substrait.narwhals` is a separate **integration layer**: it implements the
[Narwhals](https://narwhals-project.org) backend protocol and lets
backend-agnostic Narwhals code compile down to a plan, delegating to the native
frame underneath. Reach for it when you want to drive plan construction through
Narwhals (`nw.from_native(...)`); reach for `substrait.dataframe` when you want
to build plans directly. See
[`examples/narwhals_example.py`](https://github.com/substrait-io/substrait-python/blob/main/examples/narwhals_example.py).

## Next

- [Getting started](getting-started.md) — back to the basics.
- [API reference](reference/index.md) — the generated symbol reference.
