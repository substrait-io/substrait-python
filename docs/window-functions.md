# Window functions

A window function computes an aggregate-like value **without collapsing rows** —
each row gets a result computed over a related set of rows. Take a window
function from the [`f` namespace](functions.md) and turn it into a windowed
expression with `.over(...)`:

```python
--8<-- "examples/guide/window_functions.py:basic"
```

This is the SQL `OVER (PARTITION BY region ORDER BY ts)`.

!!! note "`.over()` needs a *window* function"
    `.over(...)` applies to the functions the registry classifies as window
    functions — `row_number`, `rank`, `dense_rank`, `percent_rank`, `cume_dist`,
    `ntile`, `lag`, `lead`, `first_value`, `last_value`, `nth_value`. Plain
    aggregates like `sum`/`avg` are *not* window functions here, so
    `sub.f.sum(...).over(...)` raises. To get a running/moving aggregate over a
    frame, use `first_value` / `last_value` / `nth_value` as shown below.

## Partitioning and ordering

`partition_by` and `order_by` each take a single column name/expression or a
list of them. `descending` / `nulls_last` control the ordering:

```python
--8<-- "examples/guide/window_functions.py:partition_order"
```

Both are optional — omit `partition_by` for a single window over all rows, and
omit `order_by` for an unordered window.

## Frames

A frame narrows the set of rows the function sees within each partition. Give it
as `rows=(start, end)` (physical row offsets) or `range=(start, end)` (value
offsets); specify at most one. Each endpoint is:

- `None` — unbounded (to the start/end of the partition),
- `0` — the current row,
- a negative int — that many rows **preceding**,
- a positive int — that many rows **following**.

```python
--8<-- "examples/guide/window_functions.py:frames"
```

## Next

- [Aggregations](aggregations.md) — collapse groups into one row each.
- [The function namespace](functions.md) — the available window functions.
