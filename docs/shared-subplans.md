# Shared subplans (CTEs)

A `DataFrame` is a plan *builder*, so reusing one in two places normally inlines
its subtree twice — the consumer then has no way to know the two copies are the
same computation. `cache()` marks a frame as a **shared subplan**: it is emitted
once and referenced wherever it is used, which is how Substrait models a CTE.

## `cache()`

Call `cache()` on the frame you want to share, then keep building from it as
usual:

```python
--8<-- "examples/guide/shared_subplans.py:cache"
```

The cached subtree becomes a leading `rel` entry in the plan, and every use of it
is a `ReferenceRel` pointing at that entry:

```python
--8<-- "examples/guide/shared_subplans.py:inspect"
```

Without `cache()`, the same code inlines the read into both branches:

```python
--8<-- "examples/guide/shared_subplans.py:without_cache"
```

Both plans compute the same result — the cached one just states the sharing
explicitly, so a consumer can scan `events` once.

!!! note "When sharing actually collapses"
    The subtree is emitted once when the repeated uses meet again at a
    multi-input relation (`union`, `join`, `intersect`, …), as above. That is the
    case where inlining would otherwise duplicate work.

## Chaining from a cached frame

A cached frame is an ordinary `DataFrame`; every verb still applies:

```python
--8<-- "examples/guide/shared_subplans.py:cache_chain"
```

## Hint before cache, not after

A `ReferenceRel` carries no `RelCommon`, so it has nowhere to store a
[hint](transformations.md#hints). Apply `hint` (and any other node-level
annotation) *before* `cache()`:

```python
--8<-- "examples/guide/shared_subplans.py:hint_order"
```

The other order raises rather than silently dropping the annotation:

```python
--8<-- "examples/guide/shared_subplans.py:hint_order_wrong"
```

## Next

- [Set operations](set-operations.md) — where shared branches typically meet.
- [Subqueries](subqueries.md) — the other way to reuse a frame inside a plan.
- [Consuming plans](consuming-plans.md) — inspect the plan you just built.
