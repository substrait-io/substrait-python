"""Ergonomic front door for substrait-python.

A single, shallow import that gets you productive::

    import substrait.dataframe as sub

    plan = (
        sub.read_named_table("people", {"id": sub.i64, "age": sub.i64, "name": sub.string})
        .filter(sub.col("age") > 25)
        .with_columns(adult=sub.col("age") >= 18)
        .select("id", "name")
        .to_plan()
    )

This is the Substrait-*native* fluent DataFrame/Expr API -- the higher-level
counterpart to the lower-level ``substrait.builders`` layer, and a sibling to
the other entry points (``substrait.sql``, ``substrait.narwhals``). It lives in
its own subpackage rather than at the ``substrait`` package root because
``substrait`` is a PEP 420 namespace package shared with the
``substrait-protobuf`` distribution: an ``substrait/__init__.py`` would shadow
``substrait.algebra_pb2`` and friends, and scattering ``expr`` / ``frame`` /
... at the shared namespace root would risk colliding with the sibling
distributions. Grouping them under ``substrait.dataframe`` keeps a single,
clearly owned import surface.

Everything here is an additive facade over the existing ``substrait.builders``,
``substrait.extension_registry`` and ``substrait.proto`` layers, which remain
available and unchanged.
"""

from __future__ import annotations

# Parametrized type builders (need arguments; kept as plain builder functions).
from substrait.builders.type import (
    decimal,
    fixed_binary,
    fixed_char,
    interval_compound,
    interval_day,
    named_struct,
    precision_time,
    precision_timestamp,
    precision_timestamp_tz,
    struct,
    user_defined,
)
from substrait.builders.type import list as list_  # `list`/`map` shadow builtins
from substrait.builders.type import map as map_
from substrait.builders.type import var_char as varchar  # spec spelling

# Primitive / no-argument type shortcuts as nullability-aware DataType objects
# (sub.i64 -> nullable; sub.i64.non_null -> required; sub.i64() still callable).
from substrait.dataframe.dtypes import (
    DataType,
    binary,
    boolean,
    date,
    fp32,
    fp64,
    i8,
    i16,
    i32,
    i64,
    interval_year,
    string,
    uuid,
)
from substrait.dataframe.expr import (
    Expr,
    all_,
    any_,
    coalesce,
    col,
    current_date,
    current_timestamp,
    current_timezone,
    exists,
    infer_literal_type,
    lit,
    outer,
    parameter,
    scalar_subquery,
    unique,
    when,
)
from substrait.dataframe.extension_relations import (
    ExtensionLeafDetail,
    ExtensionMultiDetail,
    ExtensionSingleDetail,
)
from substrait.dataframe.frame import (
    DataFrame,
    create_table,
    create_view,
    default_registry,
    drop_table,
    drop_view,
    extension_leaf,
    from_records,
    read_arrow,
    read_csv,
    read_extension_table,
    read_named_table,
    read_orc,
    read_parquet,
    update_table,
)
from substrait.dataframe.functions import f, functions_for
from substrait.extension_registry import ExtensionRegistry

__all__ = [
    # entry points
    "read_named_table",
    "from_records",
    "read_parquet",
    "read_csv",
    "read_orc",
    "read_arrow",
    "read_extension_table",
    "extension_leaf",
    "ExtensionLeafDetail",
    "ExtensionSingleDetail",
    "ExtensionMultiDetail",
    "create_table",
    "create_view",
    "drop_table",
    "drop_view",
    "update_table",
    "DataFrame",
    "col",
    "lit",
    "outer",
    "when",
    "coalesce",
    "scalar_subquery",
    "exists",
    "unique",
    "any_",
    "all_",
    "current_timestamp",
    "current_date",
    "current_timezone",
    "f",
    "functions_for",
    "Expr",
    # registry
    "ExtensionRegistry",
    "default_registry",
    # types
    "boolean",
    "i8",
    "i16",
    "i32",
    "i64",
    "fp32",
    "fp64",
    "string",
    "binary",
    "date",
    "uuid",
    "interval_year",
    "interval_day",
    "interval_compound",
    "fixed_char",
    "varchar",
    "fixed_binary",
    "decimal",
    "precision_time",
    "precision_timestamp",
    "precision_timestamp_tz",
    "struct",
    "named_struct",
    "list_",
    "map_",
    "user_defined",
    "DataType",
    "infer_literal_type",
    "parameter",
]
