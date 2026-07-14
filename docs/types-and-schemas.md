# Types & schemas

## Schemas

Every source takes a schema. The ergonomic form is a plain dict mapping column
names to types:

```python
import substrait.dataframe as sub

sub.read_named_table("people", {"id": sub.i64.non_null, "name": sub.string})
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
{"a": sub.i64, "b": sub.string.non_null, "c": sub.fp64.nullable}
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
sub.decimal(2, 10)                 # decimal(scale=2, precision=10) — scale first!
sub.varchar(255)                   # variable-length string, max length 255
sub.fixed_char(3)                  # fixed-length string
sub.fixed_binary(16)               # fixed-length binary
sub.precision_timestamp(6)         # microsecond timestamp (no tz)
sub.precision_timestamp_tz(6)      # microsecond timestamp with tz
sub.precision_time(6)              # microsecond time-of-day
sub.interval_day(6)                # day/second interval
sub.interval_compound(6)           # year-month + day-second interval

sub.struct([sub.i64(), sub.string()])           # a struct of two fields
sub.list_(sub.i64())                            # list<i64>  (list_ avoids shadowing built-in list)
sub.map_(sub.string(), sub.i64())               # map<string, i64>  (map_ avoids shadowing built-in map)
sub.named_struct(names=["a", "b"], struct=sub.struct([sub.i64(), sub.string()]))

sub.user_defined(...)              # a user-defined type from an extension
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
sub.lit(42)                # inferred i64
sub.lit(42, sub.i32)       # explicit i32
sub.lit(None, sub.string)  # a typed null (type is required for None)
```

See [Expressions](expressions.md) for how literal types interact with operators
and overload resolution.
