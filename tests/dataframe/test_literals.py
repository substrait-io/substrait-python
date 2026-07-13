"""Tests for literal construction across every Substrait literal kind.

The builder ``literal()`` must be able to construct a literal for every type,
and each built literal must round-trip through ``infer_literal_type`` back to the
requested type kind.
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
import substrait.type_pb2 as stt

import substrait.dataframe as sub
from substrait.builders import type as t
from substrait.builders.extended_expression import _make_literal
from substrait.type_inference import infer_literal_type

# ---------------------------------------------------------------------------
# Round-trip: built literal -> inferred type kind matches the requested kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, typ",
    [
        (True, t.boolean()),
        (5, t.i64()),
        (1.5, t.fp64()),
        ("hi", t.string()),
        (b"\x00\x01", t.binary()),
        (dt.date(2021, 1, 1), t.date()),
        (Decimal("12.34"), t.decimal(2, 10)),
        (uuid.uuid4(), t.uuid()),
        (dt.datetime(2021, 1, 1, 12), t.precision_timestamp(6)),
        (1_600_000_000_000_000, t.precision_timestamp(6)),
        (dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc), t.precision_timestamp_tz(6)),
        (dt.time(12, 30), t.precision_time(6)),
        ("fixedchars", t.fixed_char(10)),
        ("abc", t.var_char(8)),
        (b"1234", t.fixed_binary(4)),
        ((2, 6), t.interval_year()),
        (dt.timedelta(days=1, seconds=30), t.interval_day(6)),
        ((1, 30, 500), t.interval_day(6)),
        (((1, 2), (3, 4, 5)), t.interval_compound(6)),
        ([1, 2, 3], t.list(t.i64(nullable=False))),
        ({"a": 1}, t.map(t.string(nullable=False), t.i64(nullable=False))),
        ([1, "x"], t.struct([t.i64(nullable=False), t.string(nullable=False)])),
    ],
)
def test_literal_kind_round_trips(value, typ):
    lit = _make_literal(value, typ)
    assert infer_literal_type(lit).WhichOneof("kind") == typ.WhichOneof("kind")


def test_every_concrete_type_kind_can_build_a_literal():
    # A guard that no concrete type is left unsupported by literal().
    samples = {
        "bool": (True, t.boolean()),
        "i8": (1, t.i8()),
        "i16": (1, t.i16()),
        "i32": (1, t.i32()),
        "i64": (1, t.i64()),
        "fp32": (1.0, t.fp32()),
        "fp64": (1.0, t.fp64()),
        "string": ("x", t.string()),
        "binary": (b"x", t.binary()),
        "date": (dt.date(2021, 1, 1), t.date()),
        "interval_year": ((1, 0), t.interval_year()),
        "interval_day": ((1, 0), t.interval_day(6)),
        "interval_compound": (((1, 0), (1, 0)), t.interval_compound(6)),
        "fixed_char": ("x", t.fixed_char(1)),
        "varchar": ("x", t.var_char(1)),
        "fixed_binary": (b"x", t.fixed_binary(1)),
        "decimal": (Decimal("1"), t.decimal(0, 10)),
        "precision_time": (0, t.precision_time(6)),
        "precision_timestamp": (0, t.precision_timestamp(6)),
        "precision_timestamp_tz": (0, t.precision_timestamp_tz(6)),
        "uuid": (uuid.uuid4(), t.uuid()),
        "struct": ([1], t.struct([t.i64(nullable=False)])),
        "list": ([1], t.list(t.i64(nullable=False))),
        "map": ({"a": 1}, t.map(t.string(nullable=False), t.i64(nullable=False))),
    }
    for kind, (value, typ) in samples.items():
        assert typ.WhichOneof("kind") == kind
        lit = _make_literal(value, typ)
        assert lit.WhichOneof("literal_type") is not None


# ---------------------------------------------------------------------------
# Value encodings
# ---------------------------------------------------------------------------


def test_decimal_encoding_is_16_byte_little_endian_unscaled():
    lit = _make_literal(Decimal("-12.34"), t.decimal(2, 10))
    assert len(lit.decimal.value) == 16
    assert int.from_bytes(lit.decimal.value, "little", signed=True) == -1234
    assert lit.decimal.scale == 2
    assert lit.decimal.precision == 10


def test_decimal_encoding_is_exact_beyond_context_precision():
    # A value with more significant digits than the default decimal context (28)
    # must still encode exactly -- scaling is pure-integer, not context-bound.
    big = 10**38 - 1  # 38 nines, fits precision 38
    lit = _make_literal(Decimal(big), t.decimal(0, 38))
    assert int.from_bytes(lit.decimal.value, "little", signed=True) == big


def test_decimal_encoding_rounds_half_even_below_target_scale():
    # A value finer than the target scale is rounded half-even during encoding.
    assert (
        int.from_bytes(
            _make_literal(Decimal("2.5"), t.decimal(0, 10)).decimal.value,
            "little",
            signed=True,
        )
        == 2
    )
    assert (
        int.from_bytes(
            _make_literal(Decimal("3.5"), t.decimal(0, 10)).decimal.value,
            "little",
            signed=True,
        )
        == 4
    )


def test_uuid_encoding_16_bytes():
    u = uuid.uuid4()
    assert _make_literal(u, t.uuid()).uuid == u.bytes
    # hex string and raw bytes accepted too
    assert _make_literal(str(u), t.uuid()).uuid == u.bytes
    assert _make_literal(u.bytes, t.uuid()).uuid == u.bytes


def test_precision_timestamp_from_datetime_microseconds():
    lit = _make_literal(dt.datetime(1970, 1, 1, 0, 0, 1), t.precision_timestamp(6))
    assert lit.precision_timestamp.value == 1_000_000  # 1s in microseconds
    assert lit.precision_timestamp.precision == 6


def test_precision_timestamp_tz_normalizes_to_utc():
    naive_utc = _make_literal(
        dt.datetime(2021, 6, 1, 12, 0), t.precision_timestamp_tz(6)
    )
    aware = _make_literal(
        dt.datetime(2021, 6, 1, 12, 0, tzinfo=dt.timezone.utc),
        t.precision_timestamp_tz(6),
    )
    assert naive_utc.precision_timestamp_tz.value == aware.precision_timestamp_tz.value


def test_interval_year_tuple_and_int():
    assert _make_literal((2, 6), t.interval_year()).interval_year_to_month.months == 6
    assert _make_literal(3, t.interval_year()).interval_year_to_month.years == 3


def test_empty_list_and_map_use_empty_variants():
    assert _make_literal([], t.list(t.i64())).WhichOneof("literal_type") == "empty_list"
    assert (
        _make_literal({}, t.map(t.string(), t.i64())).WhichOneof("literal_type")
        == "empty_map"
    )


def test_nested_struct_recurses():
    lit = _make_literal(
        [1, [2, 3]],
        t.struct(
            [t.i64(nullable=False), t.list(t.i64(nullable=False))],
        ),
    )
    assert lit.struct.fields[0].i64 == 1
    assert [v.i64 for v in lit.struct.fields[1].list.values] == [2, 3]


def test_typed_null():
    lit = _make_literal(None, t.i64())
    assert lit.WhichOneof("literal_type") == "null"
    assert lit.null.WhichOneof("kind") == "i64"
    assert lit.nullable is True


# ---------------------------------------------------------------------------
# Ergonomic lit() inference
# ---------------------------------------------------------------------------


def _lit_kind(expr):
    ee = expr.unbound(stt.NamedStruct(), sub.default_registry())
    return ee.referred_expr[0].expression.literal.WhichOneof("literal_type")


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("12.34"), "decimal"),
        (uuid.uuid4(), "uuid"),
        (dt.datetime(2021, 1, 1), "precision_timestamp"),
        (dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc), "precision_timestamp_tz"),
        (dt.date(2021, 1, 1), "date"),
        (dt.time(9, 30), "precision_time"),
        (b"\x00", "binary"),
    ],
)
def test_lit_infers_rich_python_types(value, expected):
    assert _lit_kind(sub.lit(value)) == expected


def test_lit_none_requires_type():
    with pytest.raises(TypeError, match="explicit type"):
        sub.lit(None)
    assert _lit_kind(sub.lit(None, sub.i64)) == "null"


def test_lit_decimal_infers_scale_and_precision():
    ee = sub.lit(Decimal("1.250")).unbound(stt.NamedStruct(), sub.default_registry())
    dec_type = infer_literal_type(ee.referred_expr[0].expression.literal).decimal
    assert dec_type.scale == 3  # "1.250" has 3 fractional digits


@pytest.mark.parametrize(
    "value, scale, precision",
    [
        (Decimal("1E3"), 0, 4),  # unscaled 1000 -> needs precision 4, not 1
        (Decimal("5E2"), 0, 3),  # unscaled 500
        (Decimal("2E1"), 0, 2),  # unscaled 20
        (Decimal("123.45"), 2, 5),  # unscaled 12345
        (Decimal("100"), 0, 3),
    ],
)
def test_lit_decimal_precision_covers_unscaled_value(value, scale, precision):
    # Positive-exponent Decimals (scientific notation) have trailing zeros that
    # are absent from as_tuple().digits; the inferred precision must still count
    # them so it is not smaller than the encoded unscaled value.
    ee = sub.lit(value).unbound(stt.NamedStruct(), sub.default_registry())
    dec_type = infer_literal_type(ee.referred_expr[0].expression.literal).decimal
    assert dec_type.scale == scale
    assert dec_type.precision == precision


def test_lit_struct_requires_matching_arity():
    struct_t = t.struct([t.i64(nullable=False), t.i64(nullable=False)])
    # Right arity is fine.
    _make_literal((1, 2), struct_t)
    # Too few / too many values must raise rather than silently truncate.
    with pytest.raises(ValueError, match="declares 2 field"):
        _make_literal((1,), struct_t)
    with pytest.raises(ValueError, match="declares 2 field"):
        _make_literal((1, 2, 3), struct_t)
