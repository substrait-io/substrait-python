---
icon: lucide/home
---

# substrait-python

Python bindings for [Substrait](https://substrait.io) — the cross-language
specification for data compute operations. This site documents the **ergonomic
DataFrame API** (`substrait.dataframe`) for authoring Substrait plans in Python.

```python
import substrait.dataframe as sub

plan = (
    sub.read_named_table("people", {"id": sub.i64, "age": sub.i64, "name": sub.string})
    .filter(sub.col("age") > 25)
    .with_columns(adult=sub.col("age") >= 18)
    .select("id", "name", "adult")
    .to_plan()
)
```

That expression builds a complete `substrait.proto.Plan` — a read, a filter, a
projection and an output mapping — that any Substrait consumer (DuckDB,
DataFusion, …) can execute. No engine is bundled here: substrait-python
*produces and manipulates* plans; it does not run them.

## The three layers

substrait-python offers three ways to build a plan, from lowest- to
highest-level. They compose — the higher layers are thin, faithful facades over
the lower ones and can be freely mixed.

| Layer | Import | What it is |
|-------|--------|------------|
| **Raw protobuf** | `substrait.proto` | Construct `proto.Plan(...)` field by field. Complete but verbose. |
| **Builders** | `substrait.builders.{plan,extended_expression,type}` | Free functions returning "unbound" callables you materialize with `plan(registry)`. |
| **DataFrame** | `substrait.dataframe` | A fluent, Polars/PySpark-style frame + operator-overloaded expressions. **This guide.** |

There is also `substrait.narwhals`, a [Narwhals](https://narwhals-project.org)
integration layer that lets backend-agnostic Narwhals code compile to a plan by
driving the native DataFrame underneath. See
[Consuming plans](consuming-plans.md) for how the pieces relate.

!!! note "Why `substrait.dataframe` and not `substrait`?"
    `substrait` is a [PEP 420 namespace package](https://peps.python.org/pep-0420/)
    shared with the `substrait-protobuf` distribution. A top-level
    `substrait/__init__.py` would shadow `substrait.algebra_pb2` and friends, so
    the ergonomic API lives in its own clearly-owned submodule,
    `substrait.dataframe`, alongside `substrait.builders`, `substrait.sql`, and
    `substrait.narwhals`.

## Mental model

- **A `DataFrame` is a lazy, immutable plan builder.** Every verb
  (`.filter`, `.select`, `.join`, …) returns a *new* `DataFrame` wrapping a
  larger plan; nothing is evaluated until you call `.to_plan()`.
- **An `Expr` is an unbound expression.** `sub.col("age") > 25` does not resolve
  a function overload immediately — it is resolved lazily, against the schema and
  an [`ExtensionRegistry`](custom-extensions.md), when the plan is materialized.
- **The registry is carried for you.** A `DataFrame` holds an `ExtensionRegistry`
  (a shared default preloaded with the standard extensions) so you never thread
  it through calls. `.to_plan()` binds everything and returns a `proto.Plan`.

## Where to go next

- :material-rocket-launch: **[Getting started](getting-started.md)** — install and
  build your first plan.
- :material-table: **[Data sources](data-sources.md)** — tables, files, inline
  rows, custom sources.
- :material-function-variant: **[Expressions](expressions.md)** and
  **[the function namespace](functions.md)** — build column expressions.
- :material-set-merge: **[Joins](joins.md)**,
  **[Aggregations](aggregations.md)**, **[Window functions](window-functions.md)** —
  the relational verbs.
- :material-book-open-variant: **[API reference](reference/index.md)** — generated
  from the docstrings.
