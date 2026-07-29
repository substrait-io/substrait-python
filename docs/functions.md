# The function namespace

Operators cover arithmetic, comparison, and boolean logic. Everything else —
`sum`, `substring`, `coalesce`, `row_number`, and the hundreds of other
functions the Substrait extensions define — lives on the **`f` namespace**:

```python
--8<-- "examples/guide/functions.py:namespace_intro"
```

Each helper returns an [`Expr`](expressions.md), so it composes with operators
and other functions freely.

## It is generated from the registry

`f` is not a hand-curated list. It is built lazily on first access by
enumerating every function — scalar, aggregate, and window — defined by the
loaded extension registry. So it always matches the `substrait-extensions`
version you have installed, and it covers all three function kinds.

Discover what's available with `dir` / tab-completion, and membership-test with
`in`:

```python
--8<-- "examples/guide/functions.py:discover"
```

## Hidden plumbing

A raw Substrait scalar function call needs both an extension URN *and* a
signature name. `f` hides both — `sub.f.sum(...)` figures out the extension and
resolves the concrete overload from the argument types at build time.

**Multi-extension names.** Some names appear in more than one extension (e.g.
`add` in `functions_arithmetic`, `functions_arithmetic_decimal`, and
`functions_datetime`). For those, the correct extension is chosen at resolve
time from the actual argument types, preferring the base extension over its
`decimal` / `approx` variants.

**Keyword names.** The three function names that are Python keywords are exposed
with a trailing underscore — `sub.f.and_`, `sub.f.or_`, `sub.f.not_` — and remain
reachable via `getattr(sub.f, "and")`.

## Literals are *not* coerced here

This is the key difference from [operators](expressions.md#numeric-literal-coercion).
Operators coerce a bare Python literal to the peer column's type; the `f.*`
helpers do **not**. Pass typed operands or a `lit(...)` when a specific overload
is required:

```python
--8<-- "examples/guide/functions.py:coercion"
```

This bites most often when a function's overload is typed narrower than the
default `i64`. For example, `substring` expects `i32` offsets, so a bare `1`/`3`
(inferred `i64`) fails to resolve — pass `i32` literals:

```python
--8<-- "examples/guide/functions.py:substring"
```

If no overload matches the argument types, resolution raises an error naming the
function and the signature it tried.

## Aggregate and window functions

The same namespace provides aggregate and window functions. Aggregates are used
inside [`group_by().agg()`](aggregations.md); window functions become windowed
expressions with [`.over(...)`](window-functions.md):

```python
--8<-- "examples/guide/functions.py:agg_and_window"
```

Aggregate measures also support `.alias()`, `.distinct()`, `.order_by(...)`, and
`.filter(...)` — see [Aggregations](aggregations.md).

## Function options

Some functions accept configurable behaviors (e.g. overflow handling). Pass them
as keyword arguments to the helper; they are attached as function options:

```python
--8<-- "examples/guide/functions.py:options"
```

## Custom extensions

The global `sub.f` knows only the *default* extensions. To reach functions from
your own registered extensions, build a namespace bound to a specific registry:

```python
--8<-- "examples/guide/functions.py:custom_registry"
```

A `DataFrame` built with that registry also exposes it as `df.f`, so
`df.f.my_double(...)` just works. See [Custom extensions](custom-extensions.md).
