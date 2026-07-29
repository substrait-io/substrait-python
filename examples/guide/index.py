"""Runnable source for the snippets in ``docs/index.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.
"""

# --8<-- [start:first_plan]
import substrait.dataframe as sub

plan = (
    sub.read_named_table("people", {"id": sub.i64, "age": sub.i64, "name": sub.string})
    .filter(sub.col("age") > 25)
    .with_columns(adult=sub.col("age") >= 18)
    .select("id", "name", "adult")
    .to_plan()
)
# --8<-- [end:first_plan]
