# Data sources

Every `DataFrame` starts from a source. Each function below returns a
`DataFrame` you can chain verbs onto. All of them accept an optional `registry`
keyword to bind a custom [`ExtensionRegistry`](custom-extensions.md); omit it to
use the shared default.

Sources take a **schema**, given either as a `{name: type}` dict or a
`proto.NamedStruct`. See [Types & schemas](types-and-schemas.md) for the type
system; in short, `sub.i64` is nullable and `sub.i64.non_null` is required.

## Named tables

The most common source — a table the consumer resolves by name (a `ReadRel`
with a `NamedTable`):

```python
--8<-- "examples/guide/data_sources.py:named_table"
```

A multi-part name (catalog / schema / table) is given as a list:

```python
--8<-- "examples/guide/data_sources.py:multipart_name"
```

## Inline rows (VALUES)

`from_records` builds a `VirtualTable` — rows embedded directly in the plan,
like SQL `VALUES`. Rows may be dicts keyed by column name or positional
sequences aligned to the schema; `None` becomes a typed null:

```python
--8<-- "examples/guide/data_sources.py:from_records"
```

Each value is typed according to its schema column, so `from_records` is handy
for tests and small lookup tables.

## Files

Read local files by path (or a list of paths) plus a schema. These build a
`ReadRel` over `LocalFiles`, one entry per path:

```python
--8<-- "examples/guide/data_sources.py:files"
```

CSV/TSV reads take a couple of extra knobs:

```python
--8<-- "examples/guide/data_sources.py:csv"
```

!!! note "Schemas are declared, not inferred"
    substrait-python builds plans; it does not open your files. You always
    supply the schema — the reader in the *consuming* engine is responsible for
    matching it against the actual file contents.

## Custom sources

For a source your engine understands but Substrait has no built-in relation for,
there are two extension entry points. Both are covered in detail under
[Custom extensions](custom-extensions.md):

- **`read_extension_table(schema, detail)`** — a `ReadRel` whose source is an
  opaque `google.protobuf.Any` (`detail`). You still declare the output schema.

  ```python
  --8<-- "examples/guide/data_sources.py:read_extension_table"
  ```

- **`extension_leaf(detail)`** — a fully custom leaf relation
  (`ExtensionLeafRel`). Here `detail` is an
  [`ExtensionLeafDetail`](custom-extensions.md#extension-relations) whose
  `derive_schema()` defines the output columns, so no separate schema argument
  is needed.

  ```python
  --8<-- "examples/guide/data_sources.py:extension_leaf"
  ```

## Next

You have a `DataFrame` — now shape it. Continue with
[Types & schemas](types-and-schemas.md) or jump to
[Transformations](transformations.md).
