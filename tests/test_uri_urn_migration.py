"""
Comprehensive test suite for URI <-> URN migration.

Tests registry integration, dual URI/URN output, and round-trip conversions
during the migration period from URI to URN-based extension identifiers.

NOTE: This file is temporary and can be removed once the URI -> URN migration
is complete across all Substrait implementations. At that point, only URN-based
extension references will be used, and the UriUrnBiDiMap will no longer be needed.

Note: Tests for the UriUrnBiDiMap class itself are in test_bimap.py
"""

import pytest
import yaml

import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.extended_expression_pb2 as stee
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.builders.extended_expression import scalar_function, literal
from substrait.extension_registry import ExtensionRegistry


# ============================================================================
# ExtensionRegistry URI/URN Bimap Tests
# ============================================================================


class TestExtensionRegistryBimap:
    """Tests for ExtensionRegistry URI/URN bimap functionality."""

    def test_register_with_uri(self):
        """Test registering an extension with both URN and URI."""
        content = """%YAML 1.2
---
urn: extension:example:test
scalar_functions:
  - name: "test_func"
    description: ""
    impls:
      - args:
          - value: i8
        return: i8
"""
        uri = "https://example.com/test.yaml"
        registry = ExtensionRegistry(load_default_extensions=False)
        registry.register_extension_dict(yaml.safe_load(content), uri=uri)

        # Test URN lookup
        assert registry.lookup_urn("extension:example:test") is not None

        # Test URI lookup
        assert registry.lookup_uri_anchor(uri) is not None

        # Test bimap conversions
        assert registry.uri_to_urn(uri) == "extension:example:test"
        assert registry.urn_to_uri("extension:example:test") == uri

    def test_register_requires_uri(self):
        """Test that registering an extension requires a URI during migration."""
        content = """%YAML 1.2
---
urn: extension:example:test
scalar_functions: []
"""
        registry = ExtensionRegistry(load_default_extensions=False)

        # During migration, URI is required - this should fail with TypeError
        with pytest.raises(TypeError):
            registry.register_extension_dict(yaml.safe_load(content))

    def test_default_extensions_have_uris(self):
        """Test that default extensions are registered with URIs."""
        registry = ExtensionRegistry(load_default_extensions=True)

        # Check one of the default extensions
        urn = "extension:io.substrait:functions_comparison"
        uri_from_bimap = registry.urn_to_uri(urn)

        # Should have a URI derived from DEFAULT_URN_PREFIX
        assert uri_from_bimap is not None
        assert "https://github.com/substrait-io/substrait/blob/main/extensions" in uri_from_bimap
        assert "functions_comparison.yaml" in uri_from_bimap


# ============================================================================
# Extension Output Tests (Both URI and URN)
# ============================================================================


class TestExtensionOutput:
    """Tests that extension outputs include both URI and URN."""

    def test_scalar_function_outputs_both_uri_and_urn(self):
        """Test that scalar_function outputs both SimpleExtensionURI and SimpleExtensionURN."""
        content = """%YAML 1.2
---
urn: extension:test:functions
scalar_functions:
  - name: "test_func"
    description: ""
    impls:
      - args:
          - value: i8
        return: i8
"""
        uri = "https://test.example.com/functions.yaml"
        registry = ExtensionRegistry(load_default_extensions=False)
        registry.register_extension_dict(yaml.safe_load(content), uri=uri)

        struct = stt.Type.Struct(
            types=[stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED))]
        )
        named_struct = stt.NamedStruct(names=["value"], struct=struct)

        expr = scalar_function(
            "extension:test:functions",
            "test_func",
            expressions=[
                literal(
                    10,
                    type=stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)),
                )
            ],
        )(named_struct, registry)

        # Check that both URI and URN extensions are present
        assert len(expr.extension_urns) > 0
        assert len(expr.extension_uris) > 0

        # Check URN details
        urn_ext = expr.extension_urns[0]
        assert urn_ext.urn == "extension:test:functions"
        assert urn_ext.extension_urn_anchor > 0

        # Check URI details
        uri_ext = expr.extension_uris[0]
        assert uri_ext.uri == uri
        assert uri_ext.extension_uri_anchor > 0

        # Check that extension function declaration has both references
        ext_func = expr.extensions[0].extension_function
        assert ext_func.extension_urn_reference > 0
        assert ext_func.extension_uri_reference > 0

    def test_uri_and_urn_always_paired(self):
        """Test that during migration, URI and URN are always registered together."""
        content = """%YAML 1.2
---
urn: extension:test:functions_paired
scalar_functions:
  - name: "test_func"
    description: ""
    impls:
      - args:
          - value: i8
        return: i8
"""
        uri = "https://test.example.com/functions_paired.yaml"
        registry = ExtensionRegistry(load_default_extensions=False)
        registry.register_extension_dict(yaml.safe_load(content), uri=uri)

        # Verify both URN and URI were registered
        assert registry.lookup_urn("extension:test:functions_paired") is not None
        assert registry.lookup_uri_anchor(uri) is not None

        # Verify bimap has both directions
        assert registry.uri_to_urn(uri) == "extension:test:functions_paired"
        assert registry.urn_to_uri("extension:test:functions_paired") == uri


# ============================================================================
# Round-Trip Tests
# ============================================================================


class TestRoundTrip:
    """Tests for round-trip conversion and semantic equivalence."""

    def test_expression_with_both_uri_and_urn_round_trips(self):
        """Test that an expression with both URI and URN round-trips correctly."""
        content = """%YAML 1.2
---
urn: extension:test:roundtrip
scalar_functions:
  - name: "add"
    description: ""
    impls:
      - args:
          - value: i8
          - value: i8
        return: i8
"""
        uri = "https://test.example.com/roundtrip.yaml"
        registry = ExtensionRegistry(load_default_extensions=False)
        registry.register_extension_dict(yaml.safe_load(content), uri=uri)

        struct = stt.Type.Struct(
            types=[
                stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)),
                stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)),
            ]
        )
        named_struct = stt.NamedStruct(names=["a", "b"], struct=struct)

        # Create expression
        expr = scalar_function(
            "extension:test:roundtrip",
            "add",
            expressions=[
                literal(
                    10,
                    type=stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)),
                ),
                literal(
                    20,
                    type=stt.Type(i8=stt.Type.I8(nullability=stt.Type.NULLABILITY_REQUIRED)),
                ),
            ],
        )(named_struct, registry)

        # Verify both URI and URN are present
        assert len(expr.extension_urns) == 1
        assert len(expr.extension_uris) == 1
        assert expr.extension_urns[0].urn == "extension:test:roundtrip"
        assert expr.extension_uris[0].uri == uri

        # Serialize to bytes and deserialize (proto round-trip)
        serialized = expr.SerializeToString()
        deserialized = stee.ExtendedExpression()
        deserialized.ParseFromString(serialized)

        # Verify both URI and URN survived round-trip
        assert len(deserialized.extension_urns) == 1
        assert len(deserialized.extension_uris) == 1
        assert deserialized.extension_urns[0].urn == "extension:test:roundtrip"
        assert deserialized.extension_uris[0].uri == uri

    def test_merge_extensions_deduplicates(self):
        """Test that merging extensions with duplicate URIs/URNs deduplicates correctly."""
        from substrait.utils import merge_extension_uris, merge_extension_urns

        # Create duplicate URI extensions
        uri1 = ste.SimpleExtensionURI(extension_uri_anchor=1, uri="https://example.com/test.yaml")
        uri2 = ste.SimpleExtensionURI(extension_uri_anchor=1, uri="https://example.com/test.yaml")
        uri3 = ste.SimpleExtensionURI(extension_uri_anchor=2, uri="https://example.com/other.yaml")

        merged_uris = merge_extension_uris([uri1], [uri2, uri3])

        # Should have 2 unique URIs
        assert len(merged_uris) == 2
        assert merged_uris[0].uri == "https://example.com/test.yaml"
        assert merged_uris[1].uri == "https://example.com/other.yaml"

        # Create duplicate URN extensions
        urn1 = ste.SimpleExtensionURN(extension_urn_anchor=1, urn="extension:example:test")
        urn2 = ste.SimpleExtensionURN(extension_urn_anchor=1, urn="extension:example:test")
        urn3 = ste.SimpleExtensionURN(extension_urn_anchor=2, urn="extension:example:other")

        merged_urns = merge_extension_urns([urn1], [urn2, urn3])

        # Should have 2 unique URNs
        assert len(merged_urns) == 2
        assert merged_urns[0].urn == "extension:example:test"
        assert merged_urns[1].urn == "extension:example:other"
