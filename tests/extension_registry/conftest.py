"""Tests for parsing of a registry yaml and basic registry operations (lookup, registration)."""

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
