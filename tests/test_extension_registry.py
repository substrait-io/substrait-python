import yaml

from substrait.gen.proto.type_pb2 import Type
from substrait.extension_registry import ExtensionRegistry, covers
from substrait.derivation_expression import _parse

content = """%YAML 1.2
---
scalar_functions:
  - name: "test_fn"
    description: ""
    impls:
      - args:
          - value: i8
        variadic:
          min: 2
        return: i8
  - name: "test_fn_variadic_any"
    description: ""
    impls:
      - args:
          - value: any1
        variadic:
          min: 2
        return: any1
  - name: "add"
    description: "Add two values."
    impls:
      - args:
          - name: x
            value: i8
          - name: y
            value: i8
        options:
          overflow:
            values: [ SILENT, SATURATE, ERROR ]
        return: i8
      - args:
          - name: x
            value: i8
          - name: y
            value: i8
          - name: z
            value: any
        options:
          overflow:
            values: [ SILENT, SATURATE, ERROR ]
        return: i16
      - args:
          - name: x
            value: any1
          - name: y
            value: any1
          - name: z
            value: any2
        options:
          overflow:
            values: [ SILENT, SATURATE, ERROR ]
        return: any2
  - name: "test_decimal"
    impls:
      - args:
          - name: x
            value: decimal<P1,S1>
          - name: y
            value: decimal<S1,S2>
        return: decimal<P1 + 1,S2 + 1>
  - name: "test_enum"
    impls:
      - args:
          - name: op
            options: [ INTACT, FLIP ]
          - name: x
            value: i8
        return: i8
  - name: "add_declared"
    description: "Add two values."
    impls:
      - args:
          - name: x
            value: i8
          - name: y
            value: i8
        nullability: DECLARED_OUTPUT
        return: i8?
  - name: "add_discrete"
    description: "Add two values."
    impls:
      - args:
          - name: x
            value: i8?
          - name: y
            value: i8
        nullability: DISCRETE
        return: i8?
  - name: "test_decimal_discrete"
    impls:
      - args:
          - name: x
            value: decimal?<P1,S1>
          - name: y
            value: decimal<S1,S2>
        nullability: DISCRETE
        return: decimal?<P1 + 1,S2 + 1>
"""


registry = ExtensionRegistry()

registry.register_extension_dict(yaml.safe_load(content), uri="test")


def i8(nullable=False):
    return Type(
        i8=Type.I8(
            nullability=Type.NULLABILITY_REQUIRED
            if not nullable
            else Type.NULLABILITY_NULLABLE
        )
    )


def i16(nullable=False):
    return Type(
        i16=Type.I16(
            nullability=Type.NULLABILITY_REQUIRED
            if not nullable
            else Type.NULLABILITY_NULLABLE
        )
    )


def bool(nullable=False):
    return Type(
        bool=Type.Boolean(
            nullability=Type.NULLABILITY_REQUIRED
            if not nullable
            else Type.NULLABILITY_NULLABLE
        )
    )


def decimal(precision, scale, nullable=False):
    return Type(
        decimal=Type.Decimal(
            scale=scale,
            precision=precision,
            nullability=Type.NULLABILITY_REQUIRED
            if not nullable
            else Type.NULLABILITY_NULLABLE,
        )
    )


def test_non_existing_uri():
    assert (
        registry.lookup_function(
            uri="non_existent", function_name="add", signature=[i8(), i8()]
        )
        is None
    )


def test_non_existing_function():
    assert (
        registry.lookup_function(
            uri="test", function_name="sub", signature=[i8(), i8()]
        )
        is None
    )


def test_non_existing_function_signature():
    assert (
        registry.lookup_function(uri="test", function_name="add", signature=[i8()])
        is None
    )


def test_exact_match():
    assert registry.lookup_function(
        uri="test", function_name="add", signature=[i8(), i8()]
    )[1] == Type(i8=Type.I8(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match():
    assert registry.lookup_function(
        uri="test", function_name="add", signature=[i8(), i8(), bool()]
    )[1] == Type(i16=Type.I16(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match_fails_with_constraits():
    assert (
        registry.lookup_function(
            uri="test", function_name="add", signature=[i8(), i16(), i16()]
        )
        is None
    )


def test_wildcard_match_with_constraits():
    assert (
        registry.lookup_function(
            uri="test", function_name="add", signature=[i16(), i16(), i8()]
        )[1]
        == i8()
    )


def test_variadic():
    assert (
        registry.lookup_function(
            uri="test", function_name="test_fn", signature=[i8(), i8(), i8()]
        )[1]
        == i8()
    )


def test_variadic_any():
    assert (
        registry.lookup_function(
            uri="test",
            function_name="test_fn_variadic_any",
            signature=[i16(), i16(), i16()],
        )[1]
        == i16()
    )


def test_variadic_fails_min_constraint():
    assert (
        registry.lookup_function(uri="test", function_name="test_fn", signature=[i8()])
        is None
    )


def test_decimal_happy_path():
    assert registry.lookup_function(
        uri="test",
        function_name="test_decimal",
        signature=[decimal(10, 8), decimal(8, 6)],
    )[1] == decimal(11, 7)


def test_decimal_violates_constraint():
    assert (
        registry.lookup_function(
            uri="test",
            function_name="test_decimal",
            signature=[decimal(10, 8), decimal(12, 10)],
        )
        is None
    )


def test_decimal_happy_path_discrete():
    assert registry.lookup_function(
        uri="test",
        function_name="test_decimal_discrete",
        signature=[decimal(10, 8, nullable=True), decimal(8, 6)],
    )[1] == decimal(11, 7, nullable=True)


def test_enum_with_valid_option():
    assert (
        registry.lookup_function(
            uri="test",
            function_name="test_enum",
            signature=["FLIP", i8()],
        )[1]
        == i8()
    )


def test_enum_with_nonexistent_option():
    assert (
        registry.lookup_function(
            uri="test",
            function_name="test_enum",
            signature=["NONEXISTENT", i8()],
        )
        is None
    )


def test_function_with_nullable_args():
    assert registry.lookup_function(
        uri="test", function_name="add", signature=[i8(nullable=True), i8()]
    )[1] == i8(nullable=True)


def test_function_with_declared_output_nullability():
    assert registry.lookup_function(
        uri="test", function_name="add_declared", signature=[i8(), i8()]
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability():
    assert registry.lookup_function(
        uri="test", function_name="add_discrete", signature=[i8(nullable=True), i8()]
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability_nonexisting():
    assert (
        registry.lookup_function(
            uri="test", function_name="add_discrete", signature=[i8(), i8()]
        )
        is None
    )


def test_covers():
    params = {}
    assert covers(i8(), _parse("i8"), params)
    assert params == {}


def test_covers_nullability():
    assert not covers(i8(nullable=True), _parse("i8"), {}, check_nullability=True)
    assert covers(i8(nullable=True), _parse("i8?"), {}, check_nullability=True)


def test_covers_decimal():
    assert not covers(decimal(10, 8), _parse("decimal<11, A>"), {})


def test_covers_decimal_happy_path():
    params = {}
    assert covers(decimal(10, 8), _parse("decimal<10, A>"), params)
    assert params == {"A": 8}


def test_covers_any():
    assert covers(decimal(10, 8), _parse("any"), {})
