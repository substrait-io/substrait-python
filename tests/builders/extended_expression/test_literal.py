from datetime import date
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.extended_expression import literal
from substrait.builders import type as sttb


def extract_literal(builder):
    return builder(None, None).referred_expr[0].expression.literal


def test_boolean():
    assert extract_literal(literal(True, sttb.boolean())) == stalg.Expression.Literal(
        boolean=True, nullable=True
    )
    assert extract_literal(literal(False, sttb.boolean())) == stalg.Expression.Literal(
        boolean=False, nullable=True
    )


def test_integer():
    assert extract_literal(literal(100, sttb.i16())) == stalg.Expression.Literal(
        i16=100, nullable=True
    )


def test_string():
    assert extract_literal(literal("Hello", sttb.string())) == stalg.Expression.Literal(
        string="Hello", nullable=True
    )


def test_binary():
    assert extract_literal(
        literal(b"Hello", sttb.binary())
    ) == stalg.Expression.Literal(binary=b"Hello", nullable=True)


def test_date():
    assert extract_literal(literal(1000, sttb.date())) == stalg.Expression.Literal(
        date=1000, nullable=True
    )
    assert extract_literal(
        literal(date(1970, 1, 11), sttb.date())
    ) == stalg.Expression.Literal(date=10, nullable=True)


def test_fixed_char():
    assert extract_literal(
        literal("Hello", sttb.fixed_char(length=5))
    ) == stalg.Expression.Literal(fixed_char="Hello", nullable=True)


def test_var_char():
    assert extract_literal(
        literal("Hello", sttb.var_char(length=5))
    ) == stalg.Expression.Literal(
        var_char=stalg.Expression.Literal.VarChar(value="Hello", length=5),
        nullable=True,
    )


def test_fixed_binary():
    assert extract_literal(
        literal(b"Hello", sttb.fixed_binary(length=5))
    ) == stalg.Expression.Literal(fixed_binary=b"Hello", nullable=True)
