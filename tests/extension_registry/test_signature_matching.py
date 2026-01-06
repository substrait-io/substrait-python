"""Tests for function signature matching (decimal, enum, options)."""

from substrait.builders.type import decimal, i8


def test_decimal_happy_path(registry):
    """Test decimal signature matching with constraints."""
    f, _ = registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal",
        signature=[
            decimal(precision=10, scale=2, nullable=False),
            decimal(precision=2, scale=3, nullable=False),
        ],
    )
    assert f.name == "test_decimal"


def test_decimal_violates_constraint(registry):
    """Test decimal signature fails when constraints violated."""
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_decimal",
            signature=[
                decimal(precision=10, scale=2, nullable=False),
                decimal(precision=3, scale=3, nullable=False),
            ],
        )
        is None
    )


def test_decimal_happy_path_discrete(registry):
    """Test decimal signature with discrete nullability."""
    f, _ = registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal_discrete",
        signature=[
            decimal(precision=10, scale=2, nullable=True),
            decimal(precision=2, scale=3, nullable=False),
        ],
    )
    assert f.name == "test_decimal_discrete"


def test_enum_with_valid_option(registry):
    """Test function lookup with valid enum option."""
    f, _ = registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_enum",
        signature=["FLIP", i8(nullable=False)],
    )
    assert f.name == "test_enum"


def test_enum_with_nonexistent_option(registry):
    """Test function lookup fails with invalid enum option."""
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_enum",
            signature=["NONEXISTENT", i8(nullable=False)],
        )
        is None
    )
