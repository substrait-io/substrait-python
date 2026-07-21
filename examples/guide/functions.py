"""Runnable source for the snippets in docs/functions.md.

Run from this file's directory so the ``register_extension_yaml("my_functions.yaml")``
snippet resolves the fixture next to this script, matching how a user would keep
the YAML in their working directory.
"""

import os
from pathlib import Path

os.chdir(Path(__file__).parent)

# `df` fixture for the aggregate/window snippet (a frame "you already have").
import substrait.dataframe as sub

df = sub.read_named_table(
    "sales", {"region": sub.string, "amount": sub.fp64, "ts": sub.i64}
)

# --8<-- [start:namespace_intro]
import substrait.dataframe as sub

sub.f.sum(sub.col("amount"))
sub.f.upper(sub.col("name"))
sub.f.coalesce(sub.col("a"), sub.col("b"))
sub.f.row_number()
# --8<-- [end:namespace_intro]

# --8<-- [start:discover]
dir(sub.f)  # sorted list of every function name
"sum" in sub.f  # True
# --8<-- [end:discover]

# --8<-- [start:coercion]
# operator: the 2 is coerced to the column's type
sub.col("price_fp64") * 2

# f.* helper: pass a typed operand so the fp64 overload resolves
sub.f.multiply(sub.col("price_fp64"), 2.0)
sub.f.multiply(sub.col("price_fp64"), sub.lit(2, sub.fp64))
# --8<-- [end:coercion]

# --8<-- [start:substring]
# sub.f.substring(sub.col("name"), 1, 3)          # no substring(string, i64, i64) overload
sub.f.substring(sub.col("name"), sub.lit(1, sub.i32), sub.lit(3, sub.i32))
# --8<-- [end:substring]

# --8<-- [start:agg_and_window]
# aggregate
df.group_by("region").agg(sub.f.sum(sub.col("amount")).alias("total")).to_plan()

# window
df.with_columns(
    rn=sub.f.row_number().over(partition_by="region", order_by="ts")
).to_plan()
# --8<-- [end:agg_and_window]

# --8<-- [start:options]
sub.f.add(sub.col("a"), sub.col("b"), overflow="ERROR")
# --8<-- [end:options]

# --8<-- [start:custom_registry]
reg = sub.ExtensionRegistry(load_default_extensions=True)
reg.register_extension_yaml("my_functions.yaml")

myf = sub.functions_for(reg)
myf.my_double(sub.col("x"))
# --8<-- [end:custom_registry]
