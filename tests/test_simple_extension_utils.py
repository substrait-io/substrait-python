"""Tests for parsing simple extension YAML dicts into schema objects."""

from substrait.simple_extension_utils import build_simple_extensions


def test_metadata_is_exposed_at_all_levels():
    """Metadata should be carried through from the YAML dict at every level
    where the simple-extension schema supports it (file, function, type)."""
    definitions = {
        "urn": "extension:test:metadata",
        "metadata": {"author": "me", "version": 1},
        "types": [
            {"name": "point", "metadata": {"kind": "geometry"}},
        ],
        "scalar_functions": [
            {
                "name": "f",
                "impls": [{"return": "i64"}],
                "metadata": {"category": "math"},
            },
        ],
        "aggregate_functions": [
            {
                "name": "g",
                "impls": [{"return": "i64"}],
                "metadata": {"category": "stats"},
            },
        ],
        "window_functions": [
            {
                "name": "h",
                "impls": [{"return": "i64"}],
                "metadata": {"category": "window"},
            },
        ],
    }

    extensions = build_simple_extensions(definitions)

    assert extensions.metadata == {"author": "me", "version": 1}
    assert extensions.types[0].metadata == {"kind": "geometry"}
    assert extensions.scalar_functions[0].metadata == {"category": "math"}
    assert extensions.aggregate_functions[0].metadata == {"category": "stats"}
    assert extensions.window_functions[0].metadata == {"category": "window"}


def test_metadata_defaults_to_none_when_absent():
    """Metadata is optional and should default to None when not present."""
    extensions = build_simple_extensions({"urn": "extension:test:no-metadata"})

    assert extensions.metadata is None
