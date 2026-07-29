"""Runnable source for the snippets in ``docs/expressions.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.
"""

# --8<-- [start:columns_and_literals]
import substrait.dataframe as sub

sub.col("age")  # reference a column by name
sub.col(0)  # ...or by position
sub.lit(25)  # a literal (type inferred: i64)
sub.lit(3.5)  # fp64
sub.lit("draft")  # string
sub.lit(None, sub.i64)  # a typed null — the type is required for None
# --8<-- [end:columns_and_literals]

# Fixture: a frame the CASE / naming snippets below project against. Defined
# outside the snippet markers, so it runs but is not shown in the docs.
df = sub.read_named_table(
    "events",
    {"score": sub.i64, "qty": sub.fp64, "price": sub.fp64},
)

# --8<-- [start:operators]
(sub.col("age") > 25) & sub.col("name").is_not_null()
(sub.col("x") + sub.col("y")) * 2
-sub.col("balance")
~sub.col("is_active")
# --8<-- [end:operators]

# --8<-- [start:numeric_coercion]
sub.col("price_fp64") * 2  # the 2 is typed fp64, so multiply resolves
sub.col("count_i32") > 25  # the 25 is typed i32, so gt resolves
# --8<-- [end:numeric_coercion]

# --8<-- [start:cast_bridge]
sub.col("small_i32").cast(sub.i64) + sub.col("big_i64")
# --8<-- [end:cast_bridge]

# --8<-- [start:null_membership]
sub.col("x").is_null()
sub.col("x").is_not_null()
sub.col("x").is_nan()
sub.col("x").is_in(["active", "pending"])  # SQL IN
sub.col("x").between(1, 10)  # inclusive low <= x <= high
sub.col("x").is_distinct_from(sub.col("y"))  # null-safe !=
sub.col("x").is_not_distinct_from(sub.col("y"))  # null-safe ==
# --8<-- [end:null_membership]

# --8<-- [start:coalesce]
sub.coalesce(sub.col("preferred"), sub.col("fallback"), sub.lit("n/a"))
# --8<-- [end:coalesce]

# --8<-- [start:case_when]
tier = (
    sub.when(sub.col("score") >= 90)
    .then("A")
    .when(sub.col("score") >= 80)
    .then("B")
    .otherwise("C")
)
df.with_columns(tier=tier)
# --8<-- [end:case_when]

# --8<-- [start:switch]
sub.col("code").switch({1: "one", 2: "two"}, default="other")
# --8<-- [end:switch]

# --8<-- [start:casting]
sub.col("small_i32").cast(sub.i64)
sub.col("amount").cast(sub.decimal(2, 12))
# --8<-- [end:casting]

# --8<-- [start:nested_access]
sub.col("address").struct_field(0)  # struct field by position
sub.col("tags").list_element(2)  # list element by offset
sub.col("tags")[2]  # same, via []  (integer offset only)
sub.col("attrs").map_key("color")  # map value by key
# --8<-- [end:nested_access]

# --8<-- [start:higher_order]
sub.col("xs").list_transform(lambda x: x + 1)  # map over elements
sub.col("xs").list_filter(lambda x: x > 0)  # keep matching elements
# --8<-- [end:higher_order]

# --8<-- [start:naming]
df.with_columns(total=sub.col("qty") * sub.col("price"))
df.select(sub.col("qty").alias("quantity"))
# --8<-- [end:naming]
