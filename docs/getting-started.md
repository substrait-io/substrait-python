---
icon: lucide/rocket
---

# Getting started

## Install

```sh
pip install "substrait[extensions]"
```

The `extensions` extra pulls in the pieces needed to resolve function overloads
against the standard Substrait extensions (the ANTLR-based type-derivation
parser and `pyyaml`). The ergonomic API leans on this for its
[function namespace](functions.md) and operator resolution, so install it unless
you have a reason not to.

With conda/mamba:

```sh
conda install -c conda-forge python-substrait
```

## Your first plan

Everything is reachable from a single import. The convention used throughout
this guide is:

```python
import substrait.dataframe as sub
```

Build a plan by chaining verbs off a data source and finishing with `.to_plan()`:

```python
import substrait.dataframe as sub

plan = (
    sub.read_named_table("people", {"id": sub.i64, "age": sub.i64, "name": sub.string})
    .filter(sub.col("age") > 25)
    .with_columns(next_year=sub.col("age") + 1)
    .select("id", "name", "next_year")
    .to_plan()
)
```

`plan` is a `substrait.proto.Plan` — the same protobuf message you would get from
the raw builders, just built far more concisely. This one describes:

1. a **read** of the `people` table with a three-column schema,
2. a **filter** keeping rows where `age > 25`,
3. a **projection** adding `next_year = age + 1`, then
4. a **select** narrowing the output to three columns.

## Inspecting the result

A `proto.Plan` prints as protobuf text, which is verbose. For a compact,
readable tree, use the bundled pretty printer:

```python
from substrait.utils.display import pretty_print_plan

pretty_print_plan(plan, use_colors=True)
```

You can also serialize it to bytes to hand to a consumer (see
[Consuming plans](consuming-plans.md)):

```python
payload = plan.SerializeToString()
```

## Two things to know up front

### Nullability is explicit

Schema types are [`DataType`](types-and-schemas.md) objects. A bare `sub.i64` is
**nullable** (the safe default); `sub.i64.non_null` is required:

```python
sub.read_named_table("sales", {"region": sub.string.non_null, "amount": sub.fp64})
```

### The registry is handled for you

A `DataFrame` carries an [`ExtensionRegistry`](custom-extensions.md) — by default
a shared one preloaded with the standard extensions
(`sub.default_registry()`). That is why you never pass a registry to
`.filter(...)` or `sub.f.sum(...)`; it is threaded through automatically and
applied when you call `.to_plan()`. To use custom extensions, construct a
registry yourself and pass it to the source function — see
[Custom extensions](custom-extensions.md).

## Where next

- [Data sources](data-sources.md) — every way to start a `DataFrame`.
- [Types & schemas](types-and-schemas.md) — the type system and nullability.
- [Expressions](expressions.md) — operators, literals, and column expressions.
- [Transformations](transformations.md) — `select`, `filter`, `sort`, and friends.
