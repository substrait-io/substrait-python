from typing import Iterable
import substrait.gen.proto.type_pb2 as stt


def boolean(nullable=True) -> stt.Type:
    return stt.Type(
        bool=stt.Type.Boolean(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def i8(nullable=True) -> stt.Type:
    return stt.Type(
        i8=stt.Type.I8(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def i16(nullable=True) -> stt.Type:
    return stt.Type(
        i16=stt.Type.I16(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def i32(nullable=True) -> stt.Type:
    return stt.Type(
        i32=stt.Type.I32(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def i64(nullable=True) -> stt.Type:
    return stt.Type(
        i64=stt.Type.I64(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def fp32(nullable=True) -> stt.Type:
    return stt.Type(
        fp32=stt.Type.FP32(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def fp64(nullable=True) -> stt.Type:
    return stt.Type(
        fp64=stt.Type.FP64(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def string(nullable=True) -> stt.Type:
    return stt.Type(
        string=stt.Type.String(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def binary(nullable=True) -> stt.Type:
    return stt.Type(
        binary=stt.Type.Binary(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def date(nullable=True) -> stt.Type:
    return stt.Type(
        date=stt.Type.Date(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def interval_year(nullable=True) -> stt.Type:
    return stt.Type(
        interval_year=stt.Type.IntervalYear(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def interval_day(precision: int, nullable=True) -> stt.Type:
    return stt.Type(
        interval_day=stt.Type.IntervalDay(
            precision=precision,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def interval_compound(precision: int, nullable=True) -> stt.Type:
    return stt.Type(
        interval_compound=stt.Type.IntervalCompound(
            precision=precision,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def uuid(nullable=True) -> stt.Type:
    return stt.Type(
        uuid=stt.Type.UUID(
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED
        )
    )


def fixed_char(length: int, nullable=True) -> stt.Type:
    return stt.Type(
        fixed_char=stt.Type.FixedChar(
            length=length,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def var_char(length: int, nullable=True) -> stt.Type:
    return stt.Type(
        varchar=stt.Type.VarChar(
            length=length,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def fixed_binary(length: int, nullable=True) -> stt.Type:
    return stt.Type(
        fixed_binary=stt.Type.FixedBinary(
            length=length,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def decimal(scale: int, precision: int, nullable=True) -> stt.Type:
    return stt.Type(
        decimal=stt.Type.Decimal(
            scale=scale,
            precision=precision,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def precision_time(precision: int, nullable=True) -> stt.Type:
    return stt.Type(
        precision_time=stt.Type.PrecisionTime(
            precision=precision,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def precision_timestamp(precision: int, nullable=True) -> stt.Type:
    return stt.Type(
        precision_timestamp=stt.Type.PrecisionTimestamp(
            precision=precision,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def precision_timestamp_tz(precision: int, nullable=True) -> stt.Type:
    return stt.Type(
        precision_timestamp_tz=stt.Type.PrecisionTimestampTZ(
            precision=precision,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def struct(types: Iterable[stt.Type], nullable=True) -> stt.Type:
    return stt.Type(
        struct=stt.Type.Struct(
            types=types,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def list(type: stt.Type, nullable=True) -> stt.Type:
    return stt.Type(
        list=stt.Type.List(
            type=type,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def map(key: stt.Type, value: stt.Type, nullable=True) -> stt.Type:
    return stt.Type(
        map=stt.Type.Map(
            key=key,
            value=value,
            nullability=stt.Type.NULLABILITY_NULLABLE
            if nullable
            else stt.Type.NULLABILITY_REQUIRED,
        )
    )


def named_struct(names: Iterable[str], struct: stt.Type) -> stt.NamedStruct:
    return stt.NamedStruct(names=names, struct=struct.struct)
