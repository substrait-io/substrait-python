"""Runnable source for the snippets in ``docs/parameters-and-context.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.
"""

# --8<-- [start:parameter]
import substrait.dataframe as sub

orders = sub.read_named_table("orders", {"amount": sub.fp64, "region": sub.string})

# keep rows above a threshold provided at runtime
orders.filter(sub.col("amount") > sub.parameter(0, sub.fp64))
# --8<-- [end:parameter]

# --8<-- [start:parameter_alias]
sub.parameter(0, sub.fp64, alias="min_amount")
# --8<-- [end:parameter_alias]

# --8<-- [start:context_vars]
sub.current_timestamp()  # the query's execution timestamp (precision_timestamp_tz)
sub.current_date()  # the query's execution date
sub.current_timezone()  # the query's execution timezone (a string)
# --8<-- [end:context_vars]

# --8<-- [start:stamp_loaded_at]
orders.with_columns(loaded_at=sub.current_timestamp(precision=3, alias="loaded_at"))
# --8<-- [end:stamp_loaded_at]

# --8<-- [start:filter_today]
events = sub.read_named_table("events", {"ts": sub.date, "kind": sub.string})
events.filter(sub.col("ts") == sub.current_date())
# --8<-- [end:filter_today]
