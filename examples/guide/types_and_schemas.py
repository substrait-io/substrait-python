"""Runnable source for the snippets in ``docs/types-and-schemas.md``.

Each ``# --8<-- [start:NAME] ... # --8<-- [end:NAME]`` region below is included
into the page via ``pymdownx.snippets`` (``--8<-- "examples/guide/...:NAME"``),
so the documented code is exactly this code, and the docs-snippet test runs it.
"""

# --8<-- [start:schema_dict]
import substrait.dataframe as sub

sub.read_named_table("people", {"id": sub.i64.non_null, "name": sub.string})
# --8<-- [end:schema_dict]

# --8<-- [start:bare_datatypes]
{"a": sub.i64, "b": sub.string.non_null, "c": sub.fp64.nullable}
# --8<-- [end:bare_datatypes]

# --8<-- [start:parametrized_types]
sub.decimal(2, 10)  # decimal(scale=2, precision=10) — scale first!
sub.varchar(255)  # variable-length string, max length 255
sub.fixed_char(3)  # fixed-length string
sub.fixed_binary(16)  # fixed-length binary
sub.precision_timestamp(6)  # microsecond timestamp (no tz)
sub.precision_timestamp_tz(6)  # microsecond timestamp with tz
sub.precision_time(6)  # microsecond time-of-day
sub.interval_day(6)  # day/second interval
sub.interval_compound(6)  # year-month + day-second interval

sub.struct([sub.i64(), sub.string()])  # a struct of two fields
sub.list_(sub.i64())  # list<i64>  (list_ avoids shadowing built-in list)
sub.map_(
    sub.string(), sub.i64()
)  # map<string, i64>  (map_ avoids shadowing built-in map)
sub.named_struct(
    names=["a", "b"], struct=sub.struct([sub.i64(), sub.string()], nullable=False)
)

sub.user_defined(0)  # a user-defined type from an extension
# --8<-- [end:parametrized_types]

# --8<-- [start:literals]
sub.lit(42)  # inferred i64
sub.lit(42, sub.i32)  # explicit i32
sub.lit(None, sub.string)  # a typed null (type is required for None)
# --8<-- [end:literals]
