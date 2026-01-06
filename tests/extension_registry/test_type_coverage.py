"""Tests for the covers() function - type coverage and matching."""

from substrait.builders.type import decimal, i8, i16, i32, struct
from substrait.builders.type import list as list_
from substrait.builders.type import map as map_
from substrait.derivation_expression import _parse
from substrait.extension_registry import covers
from substrait.gen.proto.type_pb2 import Type


def test_covers():
    """Basic covers test for i8 type."""
    covered = i8(nullable=False)
    param_ctx = _parse("i8")
    assert covers(covered, param_ctx, {})


def test_covers_nullability():
    """Test nullable type coverage with check_nullability flag."""
    covered = i8(nullable=True)
    param_ctx = _parse("i8?")
    assert covers(covered, param_ctx, {}, check_nullability=True)
    covered = i8(nullable=True)
    param_ctx = _parse("i8")
    assert not covers(covered, param_ctx, {}, check_nullability=True)


def test_covers_decimal():
    """Test decimal precision/scale coverage with multiple assertions."""
    assert not covers(decimal(8, 10), _parse("decimal<11, A>"), {})
    assert covers(decimal(8, 10), _parse("decimal<10, A>"), {})
    assert covers(decimal(8, 10), _parse("decimal<10, 8>"), {})
    assert not covers(decimal(8, 10), _parse("decimal<10, 9>"), {})
    assert not covers(decimal(8, 10), _parse("decimal<11, 8>"), {})
    assert not covers(decimal(8, 10), _parse("decimal<11, 9>"), {})


def test_covers_decimal_happy_path():
    """Test decimal coverage with parameter binding."""
    covered = decimal(precision=10, scale=2, nullable=False)
    param_ctx = _parse("decimal<P, S>")
    params = {}
    assert covers(covered, param_ctx, params)
    assert params["P"] == 10 and params["S"] == 2

def test_covers_decimal_happy_path_2():
    """Test decimal coverage with parameter binding."""
    params = {}
    assert covers(decimal(8, 10), _parse("decimal<10, A>"), params)
    assert params == {"A": 8}


def test_covers_any():
    """Test that any type can be covered by any concrete type."""
    covered = decimal(precision=10, scale=2, nullable=False)
    param_ctx = _parse("any")
    assert covers(covered, param_ctx, {})

def test_covers_any_2():
    """Test that any type can be covered by any concrete type."""
    assert covers(decimal(8, 10), _parse("any"), {})



def test_covers_varchar_length_ok():
    """Test varchar length coverage (success case)."""
    covered = Type(
        varchar=Type.VarChar(nullability=Type.NULLABILITY_REQUIRED, length=10)
    )
    param_ctx = _parse("varchar<10>")
    assert covers(covered, param_ctx, {})


def test_covers_varchar_length_fail():
    """Test varchar length coverage (failure case)."""
    covered = Type(
        varchar=Type.VarChar(nullability=Type.NULLABILITY_REQUIRED, length=10)
    )
    param_ctx = _parse("varchar<20>")
    assert not covers(covered, param_ctx, {})


def test_covers_varchar_nullability():
    """Test varchar with nullability checks."""
    covered = Type(
        varchar=Type.VarChar(nullability=Type.NULLABILITY_NULLABLE, length=10)
    )
    param_ctx = _parse("varchar?<10>")
    assert covers(covered, param_ctx, {})
    assert covers(covered, param_ctx, {}, check_nullability=True)


def test_covers_fixed_char_length_ok():
    """Test fixed char length coverage (success)."""
    covered = Type(
        fixed_char=Type.FixedChar(nullability=Type.NULLABILITY_REQUIRED, length=10)
    )
    param_ctx = _parse("fixedchar<10>")
    assert covers(covered, param_ctx, {})


def test_covers_fixed_char_length_fail():
    """Test fixed char length coverage (failure)."""
    covered = Type(
        fixed_char=Type.FixedChar(nullability=Type.NULLABILITY_REQUIRED, length=10)
    )
    param_ctx = _parse("fixedchar<20>")
    assert not covers(covered, param_ctx, {})


def test_covers_fixed_binary_length_ok():
    """Test fixed binary length coverage (success)."""
    covered = Type(
        fixed_binary=Type.FixedBinary(nullability=Type.NULLABILITY_REQUIRED, length=10)
    )
    param_ctx = _parse("fixedbinary<10>")
    assert covers(covered, param_ctx, {})


def test_covers_fixed_binary_length_fail():
    """Test fixed binary length coverage (failure)."""
    covered = Type(
        fixed_binary=Type.FixedBinary(nullability=Type.NULLABILITY_REQUIRED, length=10)
    )
    param_ctx = _parse("fixedbinary<20>")
    assert not covers(covered, param_ctx, {})


def test_covers_decimal_precision_scale_fail():
    """Test decimal coverage fails with mismatched precision/scale."""
    covered = decimal(precision=10, scale=2, nullable=False)
    param_ctx = _parse("decimal<11, 2>")
    assert not covers(covered, param_ctx, {})


def test_covers_precision_timestamp_ok():
    """Test precision timestamp coverage (success)."""
    covered = Type(
        precision_timestamp=Type.PrecisionTimestamp(
            nullability=Type.NULLABILITY_REQUIRED, precision=6
        )
    )
    param_ctx = _parse("precision_timestamp<6>")
    assert covers(covered, param_ctx, {})
    # Test with parameter binding
    params = {}
    param_ctx_with_param = _parse("precision_timestamp<P>")
    assert covers(covered, param_ctx_with_param, params)
    assert params["P"] == 6


def test_covers_precision_timestamp_fail():
    """Test precision timestamp coverage (failure)."""
    covered = Type(
        precision_timestamp=Type.PrecisionTimestamp(
            nullability=Type.NULLABILITY_REQUIRED, precision=6
        )
    )
    param_ctx = _parse("precision_timestamp<3>")
    assert not covers(covered, param_ctx, {})


def test_covers_precision_timestamp_tz_ok():
    """Test precision timestamp with timezone (success)."""
    covered = Type(
        precision_timestamp_tz=Type.PrecisionTimestampTZ(
            nullability=Type.NULLABILITY_REQUIRED, precision=6
        )
    )
    param_ctx = _parse("precision_timestamp_tz<6>")
    assert covers(covered, param_ctx, {})
    # Test with parameter binding
    params = {}
    param_ctx_with_param = _parse("precision_timestamp_tz<P>")
    assert covers(covered, param_ctx_with_param, params)
    assert params["P"] == 6


def test_covers_precision_timestamp_tz_fail():
    """Test precision timestamp with timezone (failure)."""
    covered = Type(
        precision_timestamp_tz=Type.PrecisionTimestampTZ(
            nullability=Type.NULLABILITY_REQUIRED, precision=4
        )
    )
    param_ctx = _parse("precision_timestamp_tz<3>")
    assert not covers(covered, param_ctx, {})


def test_covers_precision_time_ok():
    """Test precision time coverage (success)."""
    covered = Type(
        precision_time=Type.PrecisionTime(
            nullability=Type.NULLABILITY_REQUIRED, precision=6
        )
    )
    param_ctx = _parse("precision_time<6>")
    assert covers(covered, param_ctx, {})
    # Test with parameter binding
    params = {}
    param_ctx_with_param = _parse("precision_time<P>")
    assert covers(covered, param_ctx_with_param, params)
    assert params["P"] == 6


def test_covers_precision_time_fail():
    """Test precision time coverage (failure)."""
    covered = Type(
        precision_time=Type.PrecisionTime(
            nullability=Type.NULLABILITY_REQUIRED, precision=9
        )
    )
    param_ctx = _parse("precision_time<6>")
    assert not covers(covered, param_ctx, {})


def test_covers_interval_day_ok():
    """Test interval_day coverage (success)."""
    covered = Type(
        interval_day=Type.IntervalDay(
            nullability=Type.NULLABILITY_REQUIRED, precision=6
        )
    )
    param_ctx = _parse("interval_day<6>")
    assert covers(covered, param_ctx, {})
    # Test with parameter binding
    params = {}
    param_ctx_with_param = _parse("interval_day<P>")
    assert covers(covered, param_ctx_with_param, params)
    assert params["P"] == 6


def test_covers_interval_day_fail():
    """Test interval_day coverage (failure)."""
    covered = Type(
        interval_day=Type.IntervalDay(
            nullability=Type.NULLABILITY_REQUIRED, precision=3
        )
    )
    param_ctx = _parse("interval_day<6>")
    assert not covers(covered, param_ctx, {})


def test_covers_map_string_to_i8():
    """Test map type coverage with string keys and i8 values."""
    covered = map_(key=Type(string=Type.String()), value=i8(nullable=False))
    param_ctx = _parse("map<string, i8>")
    assert covers(covered, param_ctx, {})


def test_covers_struct_with_two_fields():
    """Test struct type coverage with two i8 fields."""
    covered = struct([i8(nullable=False), i8(nullable=False)])
    param_ctx = _parse("struct<i8, i8>")
    assert covers(covered, param_ctx, {})


def test_covers_list_of_i16_fails_i8():
    """Test list type coverage failure (i16 vs i8)."""
    covered = list_(i16(nullable=False))
    param_ctx = _parse("list<i8>")
    assert not covers(covered, param_ctx, {})


def test_covers_map_i8_to_i16_fails():
    """Test map type coverage failure (value type mismatch)."""
    covered = map_(key=i8(nullable=False), value=i16(nullable=False))
    param_ctx = _parse("map<i8, i8>")
    assert not covers(covered, param_ctx, {})


def test_covers_struct_mismatched_types_fails():
    """Test struct coverage failure (field type mismatch)."""
    covered = struct([i8(nullable=False), i16(nullable=False)])
    param_ctx = _parse("struct<i8, i8>")
    assert not covers(covered, param_ctx, {})


# Tests for basic Substrait types (non-parameterized)


def test_covers_boolean():
    """Test boolean type coverage."""
    covered = Type(bool=Type.Boolean(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("boolean")
    assert covers(covered, param_ctx, {})


def test_covers_i16():
    """Test i16 type coverage."""
    covered = i16(nullable=False)
    param_ctx = _parse("i16")
    assert covers(covered, param_ctx, {})


def test_covers_i32():
    """Test i32 type coverage."""
    covered = i32(nullable=False)
    param_ctx = _parse("i32")
    assert covers(covered, param_ctx, {})


def test_covers_i64():
    """Test i64 type coverage."""
    covered = Type(i64=Type.I64(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("i64")
    assert covers(covered, param_ctx, {})


def test_covers_fp32():
    """Test fp32 type coverage."""
    covered = Type(fp32=Type.FP32(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("fp32")
    assert covers(covered, param_ctx, {})


def test_covers_fp64():
    """Test fp64 type coverage."""
    covered = Type(fp64=Type.FP64(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("fp64")
    assert covers(covered, param_ctx, {})


def test_covers_string():
    """Test string type coverage."""
    covered = Type(string=Type.String(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("string")
    assert covers(covered, param_ctx, {})


def test_covers_binary():
    """Test binary type coverage."""
    covered = Type(binary=Type.Binary(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("binary")
    assert covers(covered, param_ctx, {})


def test_covers_timestamp():
    """Test timestamp type coverage."""
    covered = Type(timestamp=Type.Timestamp(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("timestamp")
    assert covers(covered, param_ctx, {})


def test_covers_timestamp_tz():
    """Test timestamp_tz type coverage."""
    covered = Type(timestamp_tz=Type.TimestampTZ(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("timestamp_tz")
    assert covers(covered, param_ctx, {})


def test_covers_date():
    """Test date type coverage."""
    covered = Type(date=Type.Date(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("date")
    assert covers(covered, param_ctx, {})


def test_covers_time():
    """Test time type coverage."""
    covered = Type(time=Type.Time(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("time")
    assert covers(covered, param_ctx, {})


def test_covers_interval_year():
    """Test interval_year type coverage."""
    covered = Type(interval_year=Type.IntervalYear(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("interval_year")
    assert covers(covered, param_ctx, {})


def test_covers_interval_compound():
    """Test interval_compound type coverage."""
    covered = Type(
        interval_compound=Type.IntervalCompound(
            nullability=Type.NULLABILITY_REQUIRED, precision=6
        )
    )
    param_ctx = _parse("interval_compound")
    assert covers(covered, param_ctx, {})


def test_covers_uuid():
    """Test uuid type coverage."""
    covered = Type(uuid=Type.UUID(nullability=Type.NULLABILITY_REQUIRED))
    param_ctx = _parse("uuid")
    assert covers(covered, param_ctx, {})


# Additional comprehensive tests for parameterized types


def test_covers_fixedchar_with_parameter():
    """Test fixedchar with length parameter binding."""
    covered = Type(
        fixed_char=Type.FixedChar(nullability=Type.NULLABILITY_REQUIRED, length=20)
    )
    params = {}
    param_ctx = _parse("fixedchar<L>")
    assert covers(covered, param_ctx, params)
    assert params["L"] == 20


def test_covers_varchar_with_parameter():
    """Test varchar with length parameter binding."""
    covered = Type(
        varchar=Type.VarChar(nullability=Type.NULLABILITY_REQUIRED, length=100)
    )
    params = {}
    param_ctx = _parse("varchar<L>")
    assert covers(covered, param_ctx, params)
    assert params["L"] == 100


def test_covers_fixedbinary_with_parameter():
    """Test fixedbinary with length parameter binding."""
    covered = Type(
        fixed_binary=Type.FixedBinary(nullability=Type.NULLABILITY_REQUIRED, length=16)
    )
    params = {}
    param_ctx = _parse("fixedbinary<L>")
    assert covers(covered, param_ctx, params)
    assert params["L"] == 16


def test_covers_decimal_with_both_parameters():
    """Test decimal with precision and scale parameter binding."""
    covered = decimal(precision=38, scale=10, nullable=False)
    params = {}
    param_ctx = _parse("decimal<P, S>")
    assert covers(covered, param_ctx, params)
    assert params["P"] == 38 and params["S"] == 10


def test_covers_list_with_type_parameter():
    """Test list with type parameter."""
    covered = list_(i32(nullable=False))
    param_ctx = _parse("list<i32>")
    assert covers(covered, param_ctx, {})


def test_covers_map_with_both_types():
    """Test map with key and value types."""
    covered = map_(key=i8(nullable=False), value=i32(nullable=False))
    param_ctx = _parse("map<i8, i32>")
    assert covers(covered, param_ctx, {})


def test_covers_struct_with_three_fields():
    """Test struct with three fields of different types."""
    covered = struct([i8(nullable=False), i16(nullable=False), i32(nullable=False)])
    param_ctx = _parse("struct<i8, i16, i32>")
    assert covers(covered, param_ctx, {})


def test_covers_precision_time_with_parameter():
    """Test precision_time with parameter binding."""
    covered = Type(
        precision_time=Type.PrecisionTime(
            nullability=Type.NULLABILITY_REQUIRED, precision=9
        )
    )
    params = {}
    param_ctx = _parse("precision_time<P>")
    assert covers(covered, param_ctx, params)
    assert params["P"] == 9


def test_covers_precision_timestamp_with_parameter():
    """Test precision_timestamp with parameter binding."""
    covered = Type(
        precision_timestamp=Type.PrecisionTimestamp(
            nullability=Type.NULLABILITY_REQUIRED, precision=12
        )
    )
    params = {}
    param_ctx = _parse("precision_timestamp<P>")
    assert covers(covered, param_ctx, params)
    assert params["P"] == 12


def test_covers_precision_timestamp_tz_with_parameter():
    """Test precision_timestamp_tz with parameter binding."""
    covered = Type(
        precision_timestamp_tz=Type.PrecisionTimestampTZ(
            nullability=Type.NULLABILITY_REQUIRED, precision=9
        )
    )
    params = {}
    param_ctx = _parse("precision_timestamp_tz<P>")
    assert covers(covered, param_ctx, params)
    assert params["P"] == 9


def test_covers_interval_day_with_parameter():
    """Test interval_day with parameter binding."""
    covered = Type(
        interval_day=Type.IntervalDay(
            nullability=Type.NULLABILITY_REQUIRED, precision=9
        )
    )
    params = {}
    param_ctx = _parse("interval_day<P>")
    assert covers(covered, param_ctx, params)
    assert params["P"] == 9


def test_covers_interval_compound_with_precision():
    """Test interval_compound with precision parameter."""
    covered = Type(
        interval_compound=Type.IntervalCompound(
            nullability=Type.NULLABILITY_REQUIRED, precision=9
        )
    )
    # Note: interval_compound doesn't have a parameterized syntax in the grammar
    # so we just test the basic type coverage
    param_ctx = _parse("interval_compound")
    assert covers(covered, param_ctx, {})


def test_covers_nested_list():
    """Test nested list type (list of lists)."""
    inner_list = list_(i8(nullable=False))
    covered = list_(inner_list)
    param_ctx = _parse("list<list<i8>>")
    assert covers(covered, param_ctx, {})


def test_covers_map_with_struct_value():
    """Test map with struct as value type."""
    struct_type = struct([i8(nullable=False), i16(nullable=False)])
    covered = map_(key=Type(string=Type.String()), value=struct_type)
    param_ctx = _parse("map<string, struct<i8, i16>>")
    assert covers(covered, param_ctx, {})
