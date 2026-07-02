"""Nullability-aware type shortcuts for the ergonomic API.

The lower-level ``substrait.builders.type`` builders take a ``nullable`` keyword
that defaults to ``True``, which is easy to apply silently. ``DataType`` wraps a
primitive builder so nullability is explicit and reads well -- inspired by
substrait-java's ``N`` (nullable) / ``R`` (required) ``TypeCreator`` constants::

    sub.i64            # bare: nullable (the safe default) when used in a schema
    sub.i64.nullable   # explicitly nullable
    sub.i64.non_null   # required / non-nullable
    sub.i64()          # still callable, for parity with the builder layer
    sub.i64(nullable=False)

A ``DataType`` is callable, so anywhere a zero-arg type builder is accepted
(schema dicts, ``lit``) a bare ``sub.i64`` keeps working and yields a nullable
type; ``sub.i64.non_null`` yields a ready-made non-nullable ``proto.Type``.
"""

from __future__ import annotations

import substrait.type_pb2 as stp

from substrait.builders import type as _t


class DataType:
    __slots__ = ("_name", "_builder")

    def __init__(self, name: str, builder):
        self._name = name
        self._builder = builder

    def __call__(self, nullable: bool = True) -> stp.Type:
        return self._builder(nullable)

    @property
    def nullable(self) -> stp.Type:
        return self._builder(True)

    @property
    def non_null(self) -> stp.Type:
        return self._builder(False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<dtype {self._name}>"


boolean = DataType("boolean", _t.boolean)
i8 = DataType("i8", _t.i8)
i16 = DataType("i16", _t.i16)
i32 = DataType("i32", _t.i32)
i64 = DataType("i64", _t.i64)
fp32 = DataType("fp32", _t.fp32)
fp64 = DataType("fp64", _t.fp64)
string = DataType("string", _t.string)
binary = DataType("binary", _t.binary)
date = DataType("date", _t.date)
uuid = DataType("uuid", _t.uuid)
interval_year = DataType("interval_year", _t.interval_year)
