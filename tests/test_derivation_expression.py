from substrait.type_pb2 import NamedStruct, Type

from substrait.derivation_expression import evaluate


def test_simple_arithmetic():
    assert evaluate("1 + 1") == 2


def test_simple_arithmetic_with_variables():
    assert evaluate("1 + var", {"var": 2}) == 3


def test_simple_arithmetic_parenthesis():
    assert evaluate("(1 + var) * 3", {"var": 2}) == 9


def test_min_max():
    assert evaluate("min(var, 7) + max(var, 7)", {"var": 5}) == 12


def test_ternary():
    assert evaluate("var > 3 ? 1 : 0", {"var": 5}) == 1
    assert evaluate("var > 3 ? 1 : 0", {"var": 2}) == 0


def test_multiline():
    assert evaluate(
        """temp = min(var, 7) + max(var, 7)
decimal<temp + 1, temp - 1>""",
        {"var": 5},
    ) == Type(
        decimal=Type.Decimal(
            precision=13, scale=11, nullability=Type.NULLABILITY_REQUIRED
        )
    )


def test_simple_data_types():
    assert evaluate("i8") == Type(i8=Type.I8(nullability=Type.NULLABILITY_REQUIRED))
    assert evaluate("i16") == Type(i16=Type.I16(nullability=Type.NULLABILITY_REQUIRED))
    assert evaluate("i32") == Type(i32=Type.I32(nullability=Type.NULLABILITY_REQUIRED))
    assert evaluate("i64") == Type(i64=Type.I64(nullability=Type.NULLABILITY_REQUIRED))
    assert evaluate("fp32") == Type(
        fp32=Type.FP32(nullability=Type.NULLABILITY_REQUIRED)
    )
    assert evaluate("fp64") == Type(
        fp64=Type.FP64(nullability=Type.NULLABILITY_REQUIRED)
    )
    assert evaluate("boolean") == Type(
        bool=Type.Boolean(nullability=Type.NULLABILITY_REQUIRED)
    )
    assert evaluate("i8?") == Type(i8=Type.I8(nullability=Type.NULLABILITY_NULLABLE))
    assert evaluate("i16?") == Type(i16=Type.I16(nullability=Type.NULLABILITY_NULLABLE))
    assert evaluate("i32?") == Type(i32=Type.I32(nullability=Type.NULLABILITY_NULLABLE))
    assert evaluate("i64?") == Type(i64=Type.I64(nullability=Type.NULLABILITY_NULLABLE))
    assert evaluate("fp32?") == Type(
        fp32=Type.FP32(nullability=Type.NULLABILITY_NULLABLE)
    )
    assert evaluate("fp64?") == Type(
        fp64=Type.FP64(nullability=Type.NULLABILITY_NULLABLE)
    )
    assert evaluate("boolean?") == Type(
        bool=Type.Boolean(nullability=Type.NULLABILITY_NULLABLE)
    )


def test_data_type():
    assert evaluate("decimal<P + 1, S + 1>", {"S": 10, "P": 20}) == Type(
        decimal=Type.Decimal(
            precision=21, scale=11, nullability=Type.NULLABILITY_REQUIRED
        )
    )


def test_data_type_nullable():
    assert evaluate("decimal?<P + 1, S + 1>", {"S": 10, "P": 20}) == Type(
        decimal=Type.Decimal(
            precision=21, scale=11, nullability=Type.NULLABILITY_NULLABLE
        )
    )


def test_decimal_example():
    def func(P1, S1, P2, S2):
        init_scale = max(S1, S2)
        init_prec = init_scale + max(P1 - S1, P2 - S2) + 1
        min_scale = min(init_scale, 6)
        delta = init_prec - 38
        prec = min(init_prec, 38)
        scale_after_borrow = max(init_scale - delta, min_scale)
        scale = scale_after_borrow if init_prec > 38 else init_scale
        return Type(
            decimal=Type.Decimal(
                precision=prec, scale=scale, nullability=Type.NULLABILITY_REQUIRED
            )
        )

    args = {"P1": 10, "S1": 8, "P2": 14, "S2": 2}

    func_eval = func(**args)

    assert (
        evaluate(
            """init_scale = max(S1,S2)
init_prec = init_scale + max(P1 - S1, P2 - S2) + 1
min_scale = min(init_scale, 6)
delta = init_prec - 38
prec = min(init_prec, 38)
scale_after_borrow = max(init_scale - delta, min_scale)
scale = init_prec > 38 ? scale_after_borrow : init_scale
DECIMAL<prec, scale>""",
            args,
        )
        == func_eval
    )


def test_struct_simple():
    """Test simple struct with two i32 fields."""
    result = evaluate("struct<i32, i32>", {})
    expected = Type(
        struct=Type.Struct(
            types=[
                Type(i32=Type.I32(nullability=Type.NULLABILITY_REQUIRED)),
                Type(i32=Type.I32(nullability=Type.NULLABILITY_REQUIRED)),
            ],
            nullability=Type.NULLABILITY_REQUIRED,
        )
    )
    assert result == expected


def test_nstruct_simple():
    """Test named struct with field names and types."""
    result = evaluate("nStruct<a i32, b i32>", {})
    expected = NamedStruct(
        names=["a", "b"],
        struct=Type.Struct(
            types=[
                Type(i32=Type.I32(nullability=Type.NULLABILITY_REQUIRED)),
                Type(i32=Type.I32(nullability=Type.NULLABILITY_REQUIRED)),
            ],
            nullability=Type.NULLABILITY_REQUIRED,
        ),
    )
    assert result == expected


def test_nstruct_nested():
    """Test named struct with nested struct field."""
    result = evaluate("nStruct<a i32, b i32, c struct<i32, fp32>>", {})
    expected = NamedStruct(
        names=["a", "b", "c"],
        struct=Type.Struct(
            types=[
                Type(i32=Type.I32(nullability=Type.NULLABILITY_REQUIRED)),
                Type(i32=Type.I32(nullability=Type.NULLABILITY_REQUIRED)),
                Type(
                    struct=Type.Struct(
                        types=[
                            Type(i32=Type.I32(nullability=Type.NULLABILITY_REQUIRED)),
                            Type(fp32=Type.FP32(nullability=Type.NULLABILITY_REQUIRED)),
                        ],
                        nullability=Type.NULLABILITY_REQUIRED,
                    )
                ),
            ],
            nullability=Type.NULLABILITY_REQUIRED,
        ),
    )
    assert result == expected
