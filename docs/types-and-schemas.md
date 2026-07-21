# Types & schemas

## Schemas

Every source takes a schema. The ergonomic form is a plain dict mapping column
names to types:

```python
--8<-- "examples/guide/types_and_schemas.py:schema_dict"
```

Anywhere a schema is accepted you may also pass a `proto.NamedStruct` built with
`sub.named_struct(...)` / `sub.struct(...)`, which is what the dict is converted
into under the hood. The dict form preserves insertion order, so column order is
exactly what you write.

## Nullability is explicit

The no-argument type shortcuts (`sub.i64`, `sub.string`, …) are `DataType`
objects, not bare builder functions. This makes nullability a visible choice
rather than a silent default (inspired by substrait-java's `N`/`R`
`TypeCreator` constants):

| Form | Nullability |
|------|-------------|
| `sub.i64` | nullable (the safe default when used bare in a schema) |
| `sub.i64.nullable` | explicitly nullable |
| `sub.i64.non_null` | required / non-nullable |
| `sub.i64()` | callable, nullable — parity with the builder layer |
| `sub.i64(nullable=False)` | callable, required |

A `DataType` is callable and yields a `proto.Type`, so a bare `sub.i64` works
anywhere a zero-argument type builder is expected (schema dicts,
[`lit`](expressions.md), [`cast`](expressions.md), [`parameter`](parameters-and-context.md)):

```python
--8<-- "examples/guide/types_and_schemas.py:bare_datatypes"
```

## The type catalogue

Every concrete Substrait data type is reachable from `sub`.

### No-argument types (`DataType` shortcuts)

`boolean`, `i8`, `i16`, `i32`, `i64`, `fp32`, `fp64`, `string`, `binary`,
`date`, `uuid`, `interval_year`.

Each supports `.nullable` / `.non_null` / call syntax as above.

### Parametrized types (builder functions)

These take their parameters plus a `nullable` keyword (defaulting to `True`):

```python
--8<-- "examples/guide/types_and_schemas.py:parametrized_types"
```

!!! warning "`decimal` takes `scale` before `precision`"
    The signature is `decimal(scale, precision, nullable=True)`, matching the
    lower-level builder. So `sub.decimal(2, 10)` is `decimal(10, 2)` in
    SQL notation (precision 10, scale 2).

!!! note "Nesting nullable parametrized types"
    Pass the *inner* types with their own nullability, e.g.
    `sub.list_(sub.i64.non_null, nullable=False)` for a required list of
    required `i64`. Bare `DataType` shortcuts default to nullable when called.

Deprecated kinds (`timestamp` / `time` / `timestamp_tz`, superseded by the
`precision_*` family) and non-data-type kinds (function, alias) are intentionally
not surfaced.

## Types vs. literals

A schema declares column *types*. To build a typed *value* — a constant in an
expression — use [`lit`](expressions.md), which infers the type from the Python
value or takes one explicitly:

```python
--8<-- "examples/guide/types_and_schemas.py:literals"
```

See [Expressions](expressions.md) for how literal types interact with operators
and overload resolution.
