"""Tests for parsing of a registry yaml and basic registry operations (lookup, registration)."""

from substrait.builders.type import i8, i16
from substrait.builders.type import (
    decimal,
    i8,
    i16,
    i32,
    struct,
)
from substrait.gen.proto.type_pb2 import Type

import pytest
import yaml

from substrait.extension_registry import ExtensionRegistry

# Common test YAML content for testing basic functions
CONTENT = """%YAML 1.2
---
urn: extension:test:functions
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
  - name: "equal_test"
    impls:
      - args:
          - name: x
            value: any
          - name: y
            value: any
        nullability: DISCRETE
        return: any
"""


@pytest.fixture(scope="session")
def registry():
    """Create a registry with test functions loaded."""
    reg = ExtensionRegistry(load_default_extensions=True)
    reg.register_extension_dict(
        yaml.safe_load(CONTENT),
        uri="https://test.example.com/extension_test_functions.yaml",
    )
    return reg




def test_non_existing_urn(registry):
    assert (
        registry.lookup_function(
            urn="non_existent",
            function_name="add",
            signature=[i8(nullable=False), i8(nullable=False)],
        )
        is None
    )


def test_non_existing_function(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="sub",
            signature=[i8(nullable=False), i8(nullable=False)],
        )
        is None
    )


def test_non_existing_function_signature(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="add",
            signature=[i8(nullable=False)],
        )
        is None
    )


def test_exact_match(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i8(nullable=False), i8(nullable=False)],
    )[1] == Type(i8=Type.I8(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i8(nullable=False), i8(nullable=False), bool()],
    )[1] == Type(i16=Type.I16(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match_fails_with_constraits(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="add",
            signature=[i8(nullable=False), i16(nullable=False), i16(nullable=False)],
        )
        is None
    )


def test_wildcard_match_with_constraits(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i16(nullable=False), i16(nullable=False), i8(nullable=False)],
    )[1] == i8(nullable=False)


def test_variadic(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_fn",
        signature=[i8(nullable=False), i8(nullable=False), i8(nullable=False)],
    )[1] == i8(nullable=False)


def test_variadic_any(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_fn_variadic_any",
        signature=[i16(nullable=False), i16(nullable=False), i16(nullable=False)],
    )[1] == i16(nullable=False)


def test_variadic_fails_min_constraint(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_fn",
            signature=[i8(nullable=False)],
        )
        is None
    )


def test_decimal_happy_path(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal",
        signature=[decimal(8, 10, nullable=False), decimal(6, 8, nullable=False)],
    )[1] == decimal(7, 11, nullable=False)


def test_decimal_violates_constraint(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_decimal",
            signature=[decimal(8, 10, nullable=False), decimal(10, 12, nullable=False)],
        )
        is None
    )


def test_decimal_happy_path_discrete(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal_discrete",
        signature=[decimal(8, 10, nullable=True), decimal(6, 8, nullable=False)],
    )[1] == decimal(7, 11, nullable=True)


def test_enum_with_valid_option(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_enum",
        signature=["FLIP", i8(nullable=False)],
    )[1] == i8(nullable=False)


def test_enum_with_nonexistent_option(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_enum",
            signature=["NONEXISTENT", i8(nullable=False)],
        )
        is None
    )


def test_function_with_nullable_args(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i8(nullable=True), i8(nullable=False)],
    )[1] == i8(nullable=True)


def test_function_with_declared_output_nullability(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add_declared",
        signature=[i8(nullable=False), i8(nullable=False)],
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability(registry):
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add_discrete",
        signature=[i8(nullable=True), i8(nullable=False)],
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability_nonexisting(registry):
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="add_discrete",
            signature=[i8(nullable=False), i8(nullable=False)],
        )
        is None
    )
