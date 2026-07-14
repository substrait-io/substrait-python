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
import substrait.dataframe as sub

people = sub.read_named_table(
    "people", {"id": sub.i64.non_null, "name": sub.string, "age": sub.i64}
)
```

A multi-part name (catalog / schema / table) is given as a list:

```python
sub.read_named_table(["main", "public", "people"], {"id": sub.i64})
```

## Inline rows (VALUES)

`from_records` builds a `VirtualTable` — rows embedded directly in the plan,
like SQL `VALUES`. Rows may be dicts keyed by column name or positional
sequences aligned to the schema; `None` becomes a typed null:

```python
df = sub.from_records(
    [
        {"id": 1, "name": "Ada"},
        {"id": 2, "name": "Alan"},
        (3, None),  # positional; name is a typed null
    ],
    {"id": sub.i64.non_null, "name": sub.string},
)
```

Each value is typed according to its schema column, so `from_records` is handy
for tests and small lookup tables.

## Files

Read local files by path (or a list of paths) plus a schema. These build a
`ReadRel` over `LocalFiles`, one entry per path:

```python
sub.read_parquet("data/events.parquet", {"ts": sub.i64, "kind": sub.string})
sub.read_orc(["a.orc", "b.orc"], {"x": sub.i64})
sub.read_arrow("table.arrow", {"x": sub.i64})
```

CSV/TSV reads take a couple of extra knobs:

```python
sub.read_csv(
    "data/people.csv",
    {"id": sub.i64, "name": sub.string},
    delimiter=",",          # use "\t" for TSV
    header_lines_to_skip=1,  # skip the header row
)
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
  sub.read_extension_table({"x": sub.i64}, my_any_detail)
  ```

- **`extension_leaf(detail)`** — a fully custom leaf relation
  (`ExtensionLeafRel`). Here `detail` is an
  [`ExtensionLeafDetail`](custom-extensions.md#extension-relations) whose
  `derive_schema()` defines the output columns, so no separate schema argument
  is needed.

  ```python
  sub.extension_leaf(MyLeafDetail(...))
  ```

## Next

You have a `DataFrame` — now shape it. Continue with
[Types & schemas](types-and-schemas.md) or jump to
[Transformations](transformations.md).
