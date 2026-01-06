"""Tests for URN/URI mapping and default extensions."""

import yaml

from substrait.builders.type import i8
from substrait.extension_registry import ExtensionRegistry


def test_registry_uri_urn():
    """Test that URI to URN conversion works via the bimap."""
    urn = "extension:test:bimap"
    content_with_urn = f"""%YAML 1.2
---
urn: {urn}
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

    assert registry._uri_urn_bimap.get_urn(uri) == urn
    assert registry._uri_urn_bimap.get_uri(urn) == uri


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

    anchor = registry.lookup_uri_anchor(uri)
    assert anchor is not None
    assert anchor > 0


def test_registry_default_extensions_have_uri_mappings():
    """Test that default extensions have URI mappings."""
    registry = ExtensionRegistry(load_default_extensions=True)

    # Check that at least one default extension has a URI mapping
    urn = "extension:io.substrait:functions_comparison"
    uri = registry._uri_urn_bimap.get_uri(urn)

    assert uri is not None
    assert "https://github.com/substrait-io/substrait/blob/main/extensions" in uri
    assert "functions_comparison.yaml" in uri

    assert registry._uri_urn_bimap.get_urn(uri) == urn


def test_registry_default_extensions_lookup_function_multiply():
    """Test that default extensions are loaded and functions can be looked up."""
    registry = ExtensionRegistry(load_default_extensions=True)

    # Test looking up a function from the arithmetic extensions
    urn = "extension:io.substrait:functions_arithmetic"

    # Look up a common arithmetic function (e.g., "multiply")
    result = registry.lookup_function(
        urn=urn,
        function_name="multiply",
        signature=[i8(nullable=False), i8(nullable=False)],
    )

    assert (
        result is not None
    ), "Failed to lookup 'multiply' function from default extensions"
    entry, return_type = result

    # Verify the function entry
    assert entry.name == "multiply"
    assert entry.urn == urn
    assert entry.function_type is not None
    assert entry.function_type.value == "scalar"
    assert isinstance(entry.anchor, int)

    # Verify the URI-URN mapping exists
    uri = registry._uri_urn_bimap.get_uri(urn)
    assert uri is not None
    assert "https://github.com/substrait-io/substrait/blob/main/extensions" in uri
    assert "functions_arithmetic.yaml" in uri

    # Test looking up a function across all URNs without specifying URN
    results = registry.list_functions_across_urns(
        function_name="multiply",
        signature=[i8(nullable=False), i8(nullable=False)],
    )

    assert len(results) > 0, "Failed to find 'multiply' function across all URNs"

    # Verify we found the same function
    found_entry = None
    for entry, return_type in results:
        if entry.urn == urn and entry.name == "multiply":
            found_entry = entry
            break

    assert found_entry is not None, "multiply function not found in cross-URN search"
    assert found_entry.function_type.value == "scalar"


def test_registry_default_extensions_lookup_function():
    """Test that default extensions are loaded and functions can be looked up."""
    registry = ExtensionRegistry(load_default_extensions=True)

    # Test looking up a function from the comparison extensions
    urn = "extension:io.substrait:functions_comparison"

    # Look up a common comparison function (e.g., "equal")
    result = registry.lookup_function(
        urn=urn,
        function_name="equal",
        signature=[i8(nullable=False), i8(nullable=False)],
    )

    assert (
        result is not None
    ), "Failed to lookup 'equal' function from default extensions"
    entry, return_type = result

    # Verify the function entry
    assert entry.name == "equal"
    assert entry.urn == urn
    assert entry.function_type is not None
    assert entry.function_type.value == "scalar"
    assert isinstance(entry.anchor, int)

    # Verify the URI-URN mapping exists
    uri = registry._uri_urn_bimap.get_uri(urn)
    assert uri is not None
    assert "https://github.com/substrait-io/substrait/blob/main/extensions" in uri
    assert "functions_comparison.yaml" in uri

    # Test looking up a function across all URNs without specifying URN
    results = registry.list_functions_across_urns(
        function_name="equal",
        signature=[i8(nullable=False), i8(nullable=False)],
    )

    assert len(results) > 0, "Failed to find 'equal' function across all URNs"

    # Verify we found the same function
    found_entry = None
    for entry, return_type in results:
        if entry.urn == urn and entry.name == "equal":
            found_entry = entry
            break

    assert found_entry is not None, "Equal function not found in cross-URN search"
    assert found_entry.function_type.value == "scalar"


def test_register_requires_uri():
    """Test that registering requires URI parameter (migration requirement)."""
    content = """%YAML 1.2
---
urn: extension:test:no_uri
scalar_functions: []
"""
    registry = ExtensionRegistry(load_default_extensions=False)
    # This should work fine - URI is required
    registry.register_extension_dict(
        yaml.safe_load(content), uri="https://test.example.com/test.yaml"
    )
    assert registry.lookup_urn("extension:test:no_uri") is not None
