"""Runnable source for the snippets in ``docs/getting-started.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.
"""

# --8<-- [start:import]
import substrait.dataframe as sub

# --8<-- [end:import]

# --8<-- [start:first_plan]
import substrait.dataframe as sub

plan = (
    sub.read_named_table("people", {"id": sub.i64, "age": sub.i64, "name": sub.string})
    .filter(sub.col("age") > 25)
    .with_columns(next_year=sub.col("age") + 1)
    .select("id", "name", "next_year")
    .to_plan()
)
# --8<-- [end:first_plan]

# --8<-- [start:pretty_print]
from substrait.utils.display import pretty_print_plan

pretty_print_plan(plan, use_colors=True)
# --8<-- [end:pretty_print]

# --8<-- [start:serialize]
payload = plan.SerializeToString()
# --8<-- [end:serialize]

# --8<-- [start:nullability]
sub.read_named_table("sales", {"region": sub.string.non_null, "amount": sub.fp64})
# --8<-- [end:nullability]
