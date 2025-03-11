import pytest
import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.type_pb2 as stt
from substrait.type_inference import infer_literal_type

testcases = [
    (
        stalg.Expression.Literal(boolean=True, nullable=True),
        stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(i8=100, nullable=True),
        stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(i16=100, nullable=True),
        stt.Type(i16=stt.Type.I16(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(i32=100, nullable=True),
        stt.Type(i32=stt.Type.I32(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(i64=100, nullable=True),
        stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(fp32=100.5, nullable=True),
        stt.Type(fp32=stt.Type.FP32(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(fp64=100.5, nullable=True),
        stt.Type(fp64=stt.Type.FP64(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(string="substrait", nullable=True),
        stt.Type(string=stt.Type.String(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(binary=b"\xde", nullable=True),
        stt.Type(binary=stt.Type.Binary(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(timestamp=1000000, nullable=True),
        stt.Type(
            timestamp=stt.Type.Timestamp(nullability=stt.Type.NULLABILITY_NULLABLE)
        ),
    ),
    (
        stalg.Expression.Literal(date=1000, nullable=True),
        stt.Type(date=stt.Type.Date(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(time=1000, nullable=True),
        stt.Type(time=stt.Type.Time(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(
            interval_year_to_month=stalg.Expression.Literal.IntervalYearToMonth(
                years=1, months=5
            ),
            nullable=True,
        ),
        stt.Type(
            interval_year=stt.Type.IntervalYear(
                nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            interval_day_to_second=stalg.Expression.Literal.IntervalDayToSecond(
                days=1, seconds=100
            ),
            nullable=True,
        ),
        stt.Type(
            interval_day=stt.Type.IntervalDay(
                precision=0, nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            interval_day_to_second=stalg.Expression.Literal.IntervalDayToSecond(
                days=1, seconds=100, precision=3, subseconds=10
            ),
            nullable=True,
        ),
        stt.Type(
            interval_day=stt.Type.IntervalDay(
                precision=3, nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            interval_compound=stalg.Expression.Literal.IntervalCompound(
                interval_year_to_month=stalg.Expression.Literal.IntervalYearToMonth(
                    years=1, months=5
                ),
                interval_day_to_second=stalg.Expression.Literal.IntervalDayToSecond(
                    days=1, seconds=100
                ),
            ),
            nullable=True,
        ),
        stt.Type(
            interval_compound=stt.Type.IntervalCompound(
                precision=0, nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            fixed_char="substrait",
            nullable=True,
        ),
        stt.Type(
            fixed_char=stt.Type.FixedChar(
                length=9, nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            var_char=stalg.Expression.Literal.VarChar(value="substrait", length=10),
            nullable=True,
        ),
        stt.Type(
            varchar=stt.Type.VarChar(
                length=10, nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            fixed_binary=b"substrait",
            nullable=True,
        ),
        stt.Type(
            fixed_binary=stt.Type.FixedBinary(
                length=9, nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            decimal=stalg.Expression.Literal.Decimal(
                value=b"somenumber", precision=10, scale=2
            ),
            nullable=True,
        ),
        stt.Type(
            decimal=stt.Type.Decimal(
                precision=10, scale=2, nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            precision_timestamp=stalg.Expression.Literal.PrecisionTimestamp(
                precision=3, value=1000
            ),
            nullable=True,
        ),
        stt.Type(
            precision_timestamp=stt.Type.PrecisionTimestamp(
                precision=3, nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            precision_timestamp_tz=stalg.Expression.Literal.PrecisionTimestamp(
                precision=3, value=1000
            ),
            nullable=True,
        ),
        stt.Type(
            precision_timestamp_tz=stt.Type.PrecisionTimestampTZ(
                precision=3, nullability=stt.Type.NULLABILITY_NULLABLE
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            struct=stalg.Expression.Literal.Struct(
                fields=[
                    stalg.Expression.Literal(boolean=True, nullable=False),
                    stalg.Expression.Literal(i8=100, nullable=False),
                ]
            ),
            nullable=True,
        ),
        stt.Type(
            struct=stt.Type.Struct(
                types=[
                    stt.Type(
                        bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)
                    ),
                    stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)),
                ],
                nullability=stt.Type.NULLABILITY_NULLABLE,
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            map=stalg.Expression.Literal.Map(
                key_values=[
                    stalg.Expression.Literal.Map.KeyValue(
                        key=stalg.Expression.Literal(boolean=True, nullable=False),
                        value=stalg.Expression.Literal(i8=100, nullable=False),
                    )
                ],
            ),
            nullable=True,
        ),
        stt.Type(
            map=stt.Type.Map(
                key=stt.Type(
                    bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
                value=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
                nullability=stt.Type.NULLABILITY_NULLABLE,
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            uuid=b"uuid",
            nullable=True,
        ),
        stt.Type(uuid=stt.Type.UUID(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(
            null=stt.Type(
                bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)
            ),
            nullable=False,  # this should be ignored
        ),
        stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE)),
    ),
    (
        stalg.Expression.Literal(
            list=stalg.Expression.Literal.List(
                values=[stalg.Expression.Literal(i8=100, nullable=False)],
            ),
            nullable=True,
        ),
        stt.Type(
            list=stt.Type.List(
                type=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
                nullability=stt.Type.NULLABILITY_NULLABLE,
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            empty_list=stt.Type.List(
                type=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
                nullability=stt.Type.NULLABILITY_REQUIRED,
            ),
            nullable=True,
        ),
        stt.Type(
            list=stt.Type.List(
                type=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
                nullability=stt.Type.NULLABILITY_REQUIRED,
            )
        ),
    ),
    (
        stalg.Expression.Literal(
            empty_map=stt.Type.Map(
                key=stt.Type(
                    bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
                value=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
                nullability=stt.Type.NULLABILITY_NULLABLE,
            ),
            nullable=False,
        ),
        stt.Type(
            map=stt.Type.Map(
                key=stt.Type(
                    bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
                value=stt.Type(
                    i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)
                ),
                nullability=stt.Type.NULLABILITY_NULLABLE,
            )
        ),
    ),
]


@pytest.mark.parametrize("testcase", testcases)
def test_inference_literal_bool(testcase):
    assert infer_literal_type(testcase[0]) == testcase[1]
