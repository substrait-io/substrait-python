import pytest
import yaml

from substrait.gen.proto.type_pb2 import Type
from substrait.extension_registry import ExtensionRegistry, covers
from substrait.derivation_expression import _parse

content = """%YAML 1.2
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
"""


registry = ExtensionRegistry()

registry.register_extension_dict(
    yaml.safe_load(content),
    uri="https://test.example.com/extension_test_functions.yaml"
)


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


def test_non_existing_urn():
    assert (
        registry.lookup_function(
            urn="non_existent", function_name="add", signature=[i8(), i8()]
        )
        is None
    )


def test_non_existing_function():
    assert (
        registry.lookup_function(
            urn="extension:test:functions", function_name="sub", signature=[i8(), i8()]
        )
        is None
    )


def test_non_existing_function_signature():
    assert (
        registry.lookup_function(urn="extension:test:functions", function_name="add", signature=[i8()])
        is None
    )


def test_exact_match():
    assert registry.lookup_function(
        urn="extension:test:functions", function_name="add", signature=[i8(), i8()]
    )[1] == Type(i8=Type.I8(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match():
    assert registry.lookup_function(
        urn="extension:test:functions", function_name="add", signature=[i8(), i8(), bool()]
    )[1] == Type(i16=Type.I16(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match_fails_with_constraits():
    assert (
        registry.lookup_function(
            urn="extension:test:functions", function_name="add", signature=[i8(), i16(), i16()]
        )
        is None
    )


def test_wildcard_match_with_constraits():
    assert (
        registry.lookup_function(
            urn="extension:test:functions", function_name="add", signature=[i16(), i16(), i8()]
        )[1]
        == i8()
    )


def test_variadic():
    assert (
        registry.lookup_function(
            urn="extension:test:functions", function_name="test_fn", signature=[i8(), i8(), i8()]
        )[1]
        == i8()
    )


def test_variadic_any():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_fn_variadic_any",
            signature=[i16(), i16(), i16()],
        )[1]
        == i16()
    )


def test_variadic_fails_min_constraint():
    assert (
        registry.lookup_function(urn="extension:test:functions", function_name="test_fn", signature=[i8()])
        is None
    )


def test_decimal_happy_path():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal",
        signature=[decimal(10, 8), decimal(8, 6)],
    )[1] == decimal(11, 7)


def test_decimal_violates_constraint():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_decimal",
            signature=[decimal(10, 8), decimal(12, 10)],
        )
        is None
    )


def test_decimal_happy_path_discrete():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal_discrete",
        signature=[decimal(10, 8, nullable=True), decimal(8, 6)],
    )[1] == decimal(11, 7, nullable=True)


def test_enum_with_valid_option():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_enum",
            signature=["FLIP", i8()],
        )[1]
        == i8()
    )


def test_enum_with_nonexistent_option():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_enum",
            signature=["NONEXISTENT", i8()],
        )
        is None
    )


def test_function_with_nullable_args():
    assert registry.lookup_function(
        urn="extension:test:functions", function_name="add", signature=[i8(nullable=True), i8()]
    )[1] == i8(nullable=True)


def test_function_with_declared_output_nullability():
    assert registry.lookup_function(
        urn="extension:test:functions", function_name="add_declared", signature=[i8(), i8()]
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability():
    assert registry.lookup_function(
        urn="extension:test:functions", function_name="add_discrete", signature=[i8(nullable=True), i8()]
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability_nonexisting():
    assert (
        registry.lookup_function(
            urn="extension:test:functions", function_name="add_discrete", signature=[i8(), i8()]
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


# ============================================================================
# URI/URN Bimap Tests
# ============================================================================


def test_registry_uri_to_urn_conversion():
    """Test that URI to URN conversion works via the bimap."""
    content_with_urn = """%YAML 1.2
---
urn: extension:test:bimap
scalar_functions:
  - name: "test_func"
    description: ""
    impls:
      - args:
          - value: i8
        return: i8
"""
    uri = "https://test.example.com/bimap.yaml"
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(yaml.safe_load(content_with_urn), uri=uri)

    # Test URI to URN conversion
    assert registry.uri_to_urn(uri) == "extension:test:bimap"


def test_registry_urn_to_uri_conversion():
    """Test that URN to URI conversion works via the bimap."""
    content_with_urn = """%YAML 1.2
---
urn: extension:test:bimap2
scalar_functions:
  - name: "test_func"
    description: ""
    impls:
      - args:
          - value: i8
        return: i8
"""
    uri = "https://test.example.com/bimap2.yaml"
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(yaml.safe_load(content_with_urn), uri=uri)

    # Test URN to URI conversion
    assert registry.urn_to_uri("extension:test:bimap2") == uri


def test_registry_uri_anchor_lookup():
    """Test that URI anchor lookup works."""
    content_with_urn = """%YAML 1.2
---
urn: extension:test:anchor
scalar_functions: []
"""
    uri = "https://test.example.com/anchor.yaml"
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(yaml.safe_load(content_with_urn), uri=uri)

    # Test URI anchor lookup
    anchor = registry.lookup_uri_anchor(uri)
    assert anchor is not None
    assert anchor > 0


def test_registry_nonexistent_uri_urn_returns_none():
    """Test that looking up non-existent URI/URN returns None."""
    registry = ExtensionRegistry(load_default_extensions=False)

    assert registry.uri_to_urn("https://nonexistent.com/test.yaml") is None
    assert registry.urn_to_uri("extension:nonexistent:test") is None
    assert registry.lookup_uri_anchor("https://nonexistent.com/test.yaml") is None


def test_registry_default_extensions_have_uri_mappings():
    """Test that default extensions have URI mappings."""
    registry = ExtensionRegistry(load_default_extensions=True)

    # Check that at least one default extension has a URI mapping
    urn = "extension:io.substrait:functions_comparison"
    uri = registry.urn_to_uri(urn)

    assert uri is not None
    assert "https://github.com/substrait-io/substrait/blob/main/extensions" in uri
    assert "functions_comparison.yaml" in uri

    # Verify reverse mapping works
    assert registry.uri_to_urn(uri) == urn


# ============================================================================
# URN Validation Tests
# ============================================================================


def test_valid_urn_format():
    """Test that valid URN formats are accepted."""
    content = """%YAML 1.2
---
urn: extension:io.substrait:functions_test
scalar_functions:
  - name: "test_func"
    description: "Test function"
    impls:
      - args:
          - value: i8
        return: i8
"""
    registry = ExtensionRegistry(load_default_extensions=False)
    # Should not raise
    registry.register_extension_dict(
        yaml.safe_load(content),
        uri="https://test.example.com/functions_test.yaml"
    )


def test_invalid_urn_no_prefix():
    """Test that URN without 'extension:' prefix is rejected."""
    content = """%YAML 1.2
---
urn: io.substrait:functions_test
scalar_functions: []
"""
    registry = ExtensionRegistry(load_default_extensions=False)

    with pytest.raises(ValueError, match="Invalid URN format"):
        registry.register_extension_dict(
            yaml.safe_load(content),
            uri="https://test.example.com/invalid.yaml"
        )


def test_invalid_urn_too_short():
    """Test that URN with insufficient parts is rejected."""
    content = """%YAML 1.2
---
urn: extension:test
scalar_functions: []
"""
    registry = ExtensionRegistry(load_default_extensions=False)

    with pytest.raises(ValueError, match="Invalid URN format"):
        registry.register_extension_dict(
            yaml.safe_load(content),
            uri="https://test.example.com/invalid.yaml"
        )


def test_missing_urn():
    """Test that missing URN field raises ValueError."""
    content = """%YAML 1.2
---
scalar_functions: []
"""
    registry = ExtensionRegistry(load_default_extensions=False)

    with pytest.raises(ValueError, match="must contain a 'urn' field"):
        registry.register_extension_dict(
            yaml.safe_load(content),
            uri="https://test.example.com/missing_urn.yaml"
        )
