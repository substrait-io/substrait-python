"""Ergonomic front door for substrait-python.

A single, shallow import that gets you productive::

    import substrait.api as sub

    plan = (
        sub.read_named_table("people", {"id": sub.i64, "age": sub.i64, "name": sub.string})
        .filter(sub.col("age") > 25)
        .with_columns(adult=sub.col("age") >= 18)
        .select("id", "name")
        .to_plan()
    )

This lives as a *submodule* (``substrait.api``) rather than the package root on
purpose: ``substrait`` is a PEP 420 namespace package shared with the
``substrait-protobuf`` distribution, so adding ``substrait/__init__.py`` would
shadow ``substrait.algebra_pb2`` and friends.

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
)
from substrait.builders.type import list as list_  # `list`/`map` shadow builtins
from substrait.builders.type import map as map_
from substrait.builders.type import var_char as varchar  # spec spelling

# Primitive / no-argument type shortcuts as nullability-aware DataType objects
# (sub.i64 -> nullable; sub.i64.non_null -> required; sub.i64() still callable).
from substrait.dtypes import (
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
from substrait.expr import Expr, col, infer_literal_type, lit
from substrait.extension_registry import ExtensionRegistry
from substrait.frame import DataFrame, default_registry, read_named_table
from substrait.functions import f, functions_for

__all__ = [
    # entry points
    "read_named_table",
    "DataFrame",
    "col",
    "lit",
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
    "DataType",
    "infer_literal_type",
]
