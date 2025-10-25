"""
Tests for the UriUrnBiDiMap class.

This bidirectional map is temporary and used during the URI -> URN migration period.
"""

import pytest

from substrait.bimap import UriUrnBiDiMap


class TestUriUrnBiDiMap:
    """Tests for the UriUrnBiDiMap class."""

    def test_put_and_get(self):
        """Test basic put and get operations."""
        bimap = UriUrnBiDiMap()
        uri = "https://github.com/substrait-io/substrait/blob/main/extensions/functions_arithmetic.yaml"
        urn = "extension:io.substrait:functions_arithmetic"

        bimap.put(uri, urn)

        assert bimap.get_urn(uri) == urn
        assert bimap.get_uri(urn) == uri

    def test_get_nonexistent(self):
        """Test getting a non-existent mapping returns None."""
        bimap = UriUrnBiDiMap()

        assert bimap.get_urn("nonexistent") is None
        assert bimap.get_uri("nonexistent") is None

    def test_duplicate_uri_same_urn(self):
        """Test adding the same URI-URN mapping twice is idempotent."""
        bimap = UriUrnBiDiMap()
        uri = "https://example.com/test.yaml"
        urn = "extension:example:test"

        bimap.put(uri, urn)
        bimap.put(uri, urn)  # Should not raise

        assert bimap.get_urn(uri) == urn

    def test_duplicate_uri_different_urn(self):
        """Test adding the same URI with different URN raises ValueError."""
        bimap = UriUrnBiDiMap()
        uri = "https://example.com/test.yaml"
        urn1 = "extension:example:test1"
        urn2 = "extension:example:test2"

        bimap.put(uri, urn1)

        with pytest.raises(ValueError, match="already mapped"):
            bimap.put(uri, urn2)

    def test_duplicate_urn_different_uri(self):
        """Test adding the same URN with different URI raises ValueError."""
        bimap = UriUrnBiDiMap()
        uri1 = "https://example.com/test1.yaml"
        uri2 = "https://example.com/test2.yaml"
        urn = "extension:example:test"

        bimap.put(uri1, urn)

        with pytest.raises(ValueError, match="already mapped"):
            bimap.put(uri2, urn)

    def test_contains(self):
        """Test contains_uri and contains_urn methods."""
        bimap = UriUrnBiDiMap()
        uri = "https://example.com/test.yaml"
        urn = "extension:example:test"

        assert not bimap.contains_uri(uri)
        assert not bimap.contains_urn(urn)

        bimap.put(uri, urn)

        assert bimap.contains_uri(uri)
        assert bimap.contains_urn(urn)
