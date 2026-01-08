"""Tests for URN format validation."""

import pytest
import yaml

from substrait.extension_registry import ExtensionRegistry


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

    registry.register_extension_dict(
        yaml.safe_load(content), uri="https://test.example.com/functions_test.yaml"
    )  # Should not raise


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
            yaml.safe_load(content), uri="https://test.example.com/invalid.yaml"
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
            yaml.safe_load(content), uri="https://test.example.com/invalid.yaml"
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
            yaml.safe_load(content), uri="https://test.example.com/missing_urn.yaml"
        )
