"""
Bidirectional map for URI <-> URN conversion during the migration period.

This module provides a UriUrnBiDiMap class that maintains a bidirectional mapping
between URIs and URNs.

NOTE: This file is temporary and can be removed once the URI -> URN migration
is complete across all Substrait implementations. At that point, only URN-based
extension references will be used.
"""

from typing import Optional


class UriUrnBiDiMap:
    """Bidirectional map for URI <-> URN mappings.

    Maintains two internal dictionaries to enable O(1) lookups in both directions.
    Enforces that each URI maps to exactly one URN and vice versa.
    """

    def __init__(self):
        self._uri_to_urn: dict[str, str] = {}
        self._urn_to_uri: dict[str, str] = {}

    def put(self, uri: str, urn: str) -> None:
        """Add a bidirectional URI <-> URN mapping.

        Args:
            uri: The extension URI (e.g., "https://github.com/.../functions_arithmetic.yaml")
            urn: The extension URN (e.g., "extension:io.substrait:functions_arithmetic")

        Raises:
            ValueError: If the URI or URN already exists with a different mapping
        """
        # Check for conflicts
        if self.contains_uri(uri):
            existing_urn = self.get_urn(uri)
            if existing_urn != urn:
                raise ValueError(
                    f"URI '{uri}' is already mapped to URN '{existing_urn}', "
                    f"cannot remap to '{urn}'"
                )
            # Already have this exact mapping, nothing to do
            return

        if self.contains_urn(urn):
            existing_uri = self.get_uri(urn)
            if existing_uri != uri:
                raise ValueError(
                    f"URN '{urn}' is already mapped to URI '{existing_uri}', "
                    f"cannot remap to '{uri}'"
                )
            # Already have this exact mapping, nothing to do
            return

        self._uri_to_urn[uri] = urn
        self._urn_to_uri[urn] = uri

    def get_urn(self, uri: str) -> Optional[str]:
        """Convert a URI to its corresponding URN.

        Args:
            uri: The extension URI to look up

        Returns:
            The corresponding URN, or None if the URI is not in the map
        """
        return self._uri_to_urn.get(uri)

    def get_uri(self, urn: str) -> Optional[str]:
        """Convert a URN to its corresponding URI.

        Args:
            urn: The extension URN to look up

        Returns:
            The corresponding URI, or None if the URN is not in the map
        """
        return self._urn_to_uri.get(urn)

    def contains_uri(self, uri: str) -> bool:
        """Check if a URI exists in the map.

        Args:
            uri: The URI to check

        Returns:
            True if the URI is in the map, False otherwise
        """
        return uri in self._uri_to_urn

    def contains_urn(self, urn: str) -> bool:
        """Check if a URN exists in the map.

        Args:
            urn: The URN to check

        Returns:
            True if the URN is in the map, False otherwise
        """
        return urn in self._urn_to_uri
