# Expressions

An **`Expr`** is a composable, unbound column expression. You build them with
`sub.col`, `sub.lit`, Python operators, and the [`f` function
namespace](functions.md), then pass them to verbs like `.filter`,
`.with_columns`, and `.select`. Nothing resolves immediately — an `Expr` is
resolved lazily against the schema and registry when the plan is materialized.

## Columns and literals

```python
--8<-- "examples/guide/expressions.py:columns_and_literals"
```

`lit` infers the Substrait type from the Python value (see the table under
[Literal type inference](#literal-type-inference)); pass a second argument to
override it (`sub.lit(25, sub.i32)`).

## Operators

`Expr` overloads the Python operators every pandas / Polars / PySpark user
expects. Each maps to a fixed standard function-extension and is resolved
against the registry at build time.

| Operator | Substrait function |
|----------|--------------------|
| `<` `<=` `>` `>=` | `lt` `lte` `gt` `gte` (comparison) |
| `==` `!=` | `equal` `not_equal` (comparison) |
| `+` `-` `*` `/` `%` `**` | `add` `subtract` `multiply` `divide` `modulus` `power` (arithmetic) |
| `-x` (unary) | `negate` |
| `&` `\|` `~` | `and` `or` `not` (boolean) |

```python
--8<-- "examples/guide/expressions.py:operators"
```

!!! warning "Use `&` `|` `~`, not `and` `or` `not`"
    Python's `and`/`or`/`not` keywords cannot be overloaded and would coerce the
    expression to a bool. Use the bitwise operators `&`, `|`, `~` — and mind
    their higher precedence, so parenthesize comparisons:
    `(a > 1) & (b < 2)`.

!!! note "`Expr` is intentionally unhashable"
    Because `==` builds an expression rather than comparing, `Expr` sets
    `__hash__ = None` (exactly as pandas/Polars do). An `Expr` cannot be used as
    a dict key or set member.

### Numeric literal coercion

Substrait does not implicitly coerce mixed numeric operands. To keep the common
cases working, a **bare Python number** on one side of an operator is typed to
match the **column** on the other side at resolve time:

```python
--8<-- "examples/guide/expressions.py:numeric_coercion"
```

A `float` literal always stays floating point (it is never narrowed into an
integer column). Coercion applies **only to literals** — a genuine
column-to-column type mismatch must be bridged explicitly with
[`cast`](#casting):

```python
--8<-- "examples/guide/expressions.py:cast_bridge"
```

Decimal operands are handled too: arithmetic keeps a decimal literal's natural
type, while a comparison requires the literal to fit the column's
`decimal(precision, scale)` exactly (otherwise it raises rather than silently
rounding — wrap it with `sub.lit(value, <decimal type>)` or cast the column).

## Null and membership tests

```python
--8<-- "examples/guide/expressions.py:null_membership"
```

`coalesce` returns the first non-null argument:

```python
--8<-- "examples/guide/expressions.py:coalesce"
```

!!! note "`between` / `is_in` bounds are not coerced"
    Like the [`f.*` helpers](functions.md), these do not coerce bare Python
    numbers to the column's type. Pass matching literals or
    `sub.lit(..., type)` when the types differ.

## Conditionals (CASE)

Chain `when().then()` and finish with `.otherwise()`, PySpark/Polars-style:

```python
--8<-- "examples/guide/expressions.py:case_when"
```

For a value-match against literal keys, `Expr.switch` is more compact:

```python
--8<-- "examples/guide/expressions.py:switch"
```

## Casting

`cast` is the explicit escape hatch when automatic literal coercion is not
enough — most often between two columns of different numeric types:

```python
--8<-- "examples/guide/expressions.py:casting"
```

It accepts a `proto.Type` or a bare type builder / `DataType`.

## Nested field access

Reach into struct, list, and map columns:

```python
--8<-- "examples/guide/expressions.py:nested_access"
```

These chain, so `sub.col("a").struct_field(1).list_element(0)` walks a nested
path.

## Higher-order list functions

Apply a lambda over the elements of a `list` column. The callback receives an
`Expr` bound to the current element:

```python
--8<-- "examples/guide/expressions.py:higher_order"
```

## Naming

`.alias(name)` sets the output column name of an expression — essential when a
projection would otherwise produce a generated name:

```python
--8<-- "examples/guide/expressions.py:naming"
```

## Literal type inference

`sub.lit(value)` (and bare Python scalars passed to expressions) map to Substrait
types as follows:

| Python | Substrait type |
|--------|----------------|
| `bool` | `boolean` |
| `int` | `i64` |
| `float` | `fp64` |
| `decimal.Decimal` | `decimal` (scale/precision from the value) |
| `str` | `string` |
| `bytes` / `bytearray` | `binary` |
| `datetime` (naive) | `precision_timestamp(6)` |
| `datetime` (tz-aware) | `precision_timestamp_tz(6)` |
| `date` | `date` |
| `time` | `precision_time(6)` |
| `uuid.UUID` | `uuid` |

Anything else raises — wrap it with `sub.lit(value, <type>)`. `bool` is checked
before `int` (since `True` is an `int`), and `datetime` before `date` (since
`datetime` subclasses `date`).

## Next

- [The function namespace](functions.md) — everything operators can't express.
- [Transformations](transformations.md) — where expressions are used.
- [Aggregations](aggregations.md) and [Window functions](window-functions.md) —
  measures and windowed expressions.
