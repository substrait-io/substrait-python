import pytest
import yaml

from substrait.builders.type import (
    decimal,
    i8,
    i16,
    i32,
    struct,
)
from substrait.builders.type import (
    list as list_,
)
from substrait.builders.type import (
    map as map_,
)
from substrait.derivation_expression import _parse
from substrait.extension_registry import ExtensionRegistry, covers
from substrait.gen.proto.type_pb2 import Type

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


registry = ExtensionRegistry(load_default_extensions=True)

registry.register_extension_dict(
    yaml.safe_load(content),
    uri="https://test.example.com/extension_test_functions.yaml",
)


def test_non_existing_urn():
    assert (
        registry.lookup_function(
            urn="non_existent",
            function_name="add",
            signature=[i8(nullable=False), i8(nullable=False)],
        )
        is None
    )


def test_non_existing_function():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="sub",
            signature=[i8(nullable=False), i8(nullable=False)],
        )
        is None
    )


def test_non_existing_function_signature():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="add",
            signature=[i8(nullable=False)],
        )
        is None
    )


def test_exact_match():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i8(nullable=False), i8(nullable=False)],
    )[1] == Type(i8=Type.I8(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i8(nullable=False), i8(nullable=False), bool()],
    )[1] == Type(i16=Type.I16(nullability=Type.NULLABILITY_REQUIRED))


def test_wildcard_match_fails_with_constraits():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="add",
            signature=[i8(nullable=False), i16(nullable=False), i16(nullable=False)],
        )
        is None
    )


def test_wildcard_match_with_constraits():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i16(nullable=False), i16(nullable=False), i8(nullable=False)],
    )[1] == i8(nullable=False)


def test_variadic():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_fn",
        signature=[i8(nullable=False), i8(nullable=False), i8(nullable=False)],
    )[1] == i8(nullable=False)


def test_variadic_any():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_fn_variadic_any",
        signature=[i16(nullable=False), i16(nullable=False), i16(nullable=False)],
    )[1] == i16(nullable=False)


def test_variadic_fails_min_constraint():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_fn",
            signature=[i8(nullable=False)],
        )
        is None
    )


def test_decimal_happy_path():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal",
        signature=[decimal(8, 10, nullable=False), decimal(6, 8, nullable=False)],
    )[1] == decimal(7, 11, nullable=False)


def test_decimal_violates_constraint():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_decimal",
            signature=[decimal(8, 10, nullable=False), decimal(10, 12, nullable=False)],
        )
        is None
    )


def test_decimal_happy_path_discrete():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_decimal_discrete",
        signature=[decimal(8, 10, nullable=True), decimal(6, 8, nullable=False)],
    )[1] == decimal(7, 11, nullable=True)


def test_enum_with_valid_option():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="test_enum",
        signature=["FLIP", i8(nullable=False)],
    )[1] == i8(nullable=False)


def test_enum_with_nonexistent_option():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="test_enum",
            signature=["NONEXISTENT", i8(nullable=False)],
        )
        is None
    )


def test_function_with_nullable_args():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add",
        signature=[i8(nullable=True), i8(nullable=False)],
    )[1] == i8(nullable=True)


def test_function_with_declared_output_nullability():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add_declared",
        signature=[i8(nullable=False), i8(nullable=False)],
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability():
    assert registry.lookup_function(
        urn="extension:test:functions",
        function_name="add_discrete",
        signature=[i8(nullable=True), i8(nullable=False)],
    )[1] == i8(nullable=True)


def test_function_with_discrete_nullability_nonexisting():
    assert (
        registry.lookup_function(
            urn="extension:test:functions",
            function_name="add_discrete",
            signature=[i8(nullable=False), i8(nullable=False)],
        )
        is None
    )


def test_covers():
    params = {}
    assert covers(i8(nullable=False), _parse("i8"), params)
    assert params == {}


def test_covers_nullability():
    assert not covers(i8(nullable=True), _parse("i8"), {}, check_nullability=True)
    assert covers(i8(nullable=True), _parse("i8?"), {}, check_nullability=True)


def test_covers_decimal(nullable=False):
    assert not covers(decimal(8, 10), _parse("decimal<11, A>"), {})
    assert covers(decimal(8, 10), _parse("decimal<10, A>"), {})
    assert covers(decimal(8, 10), _parse("decimal<10, 8>"), {})
    assert not covers(decimal(8, 10), _parse("decimal<10, 9>"), {})
    assert not covers(decimal(8, 10), _parse("decimal<11, 8>"), {})
    assert not covers(decimal(8, 10), _parse("decimal<11, 9>"), {})


def test_covers_decimal_happy_path():
    params = {}
    assert covers(decimal(8, 10), _parse("decimal<10, A>"), params)
    assert params == {"A": 8}


def test_covers_any():
    assert covers(decimal(8, 10), _parse("any"), {})


def test_covers_varchar_length_ok():
    covered = Type(
        varchar=Type.VarChar(nullability=Type.NULLABILITY_REQUIRED, length=15)
    )
    param_ctx = _parse("varchar<15>")
    assert covers(covered, param_ctx, {}, check_nullability=True)


def test_covers_varchar_length_fail():
    covered = Type(
        varchar=Type.VarChar(nullability=Type.NULLABILITY_REQUIRED, length=10)
    )
    param_ctx = _parse("varchar<5>")
    assert not covers(covered, param_ctx, {})


def test_covers_varchar_nullability():
    covered = Type(
        varchar=Type.VarChar(nullability=Type.NULLABILITY_REQUIRED, length=10)
    )
    param_tx = _parse("varchar?<10>")
    assert covers(covered, param_tx, {})
    assert not covers(covered, param_tx, {}, True)
    param_ctx2 = _parse("varchar<10>")
    assert covers(covered, param_ctx2, {}, True)


def test_covers_fixed_char_length_ok():
    covered = Type(
        fixed_char=Type.FixedChar(nullability=Type.NULLABILITY_REQUIRED, length=8)
    )
    param_ctx = _parse("fixedchar<8>")
    assert covers(covered, param_ctx, {})


def test_covers_fixed_char_length_fail():
    covered = Type(
        fixed_char=Type.FixedChar(nullability=Type.NULLABILITY_REQUIRED, length=8)
    )
    param_ctx = _parse("fixedchar<4>")
    assert not covers(covered, param_ctx, {})


def test_covers_fixed_binary_length_ok():
    covered = Type(
        fixed_binary=Type.FixedBinary(nullability=Type.NULLABILITY_REQUIRED, length=16)
    )
    param_ctx = _parse("fixedbinary<16>")
    assert covers(covered, param_ctx, {})


def test_covers_fixed_binary_length_fail():
    covered = Type(
        fixed_binary=Type.FixedBinary(nullability=Type.NULLABILITY_REQUIRED, length=16)
    )
    param_ctx = _parse("fixedbinary<10>")
    assert not covers(covered, param_ctx, {})


def test_covers_decimal_precision_scale_fail():
    covered = decimal(8, 10, nullable=False)
    param_ctx = _parse("decimal<6, 5>")
    assert not covers(covered, param_ctx, {})


def test_covers_precision_timestamp_ok():
    covered = Type(
        precision_timestamp=Type.PrecisionTimestamp(
            nullability=Type.NULLABILITY_REQUIRED, precision=5
        )
    )
    param_ctx = _parse("precision_timestamp<5>")
    assert covers(covered, param_ctx, {})
    param_ctx = _parse("precision_timestamp<L1>")
    assert covers(covered, param_ctx, {})


def test_covers_precision_timestamp_fail():
    covered = Type(
        precision_timestamp=Type.PrecisionTimestamp(
            nullability=Type.NULLABILITY_REQUIRED, precision=3
        )
    )
    param_ctx = _parse("precision_timestamp<2>")
    assert not covers(covered, param_ctx, {})


def test_covers_precision_timestamp_tz_ok():
    covered = Type(
        precision_timestamp_tz=Type.PrecisionTimestampTZ(
            nullability=Type.NULLABILITY_REQUIRED, precision=4
        )
    )
    param_ctx = _parse("precision_timestamp_tz<4>")
    assert covers(covered, param_ctx, {})
    param_ctx = _parse("precision_timestamp_tz<L>")
    assert covers(covered, param_ctx, {})


def test_covers_precision_timestamp_tz_fail():
    covered = Type(
        precision_timestamp_tz=Type.PrecisionTimestampTZ(
            nullability=Type.NULLABILITY_REQUIRED, precision=4
        )
    )
    param_ctx = _parse("precision_timestamp_tz<3>")
    assert not covers(covered, param_ctx, {})


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


def test_register_requires_uri():
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


def test_covers_map_string_to_i8():
    """Test that a map with string keys and i8 values covers map<string,i8>."""
    covered = map_(
        key=Type(string=Type.String(nullability=Type.NULLABILITY_REQUIRED)),
        value=i8(nullable=False),
        nullable=False,
    )
    param_ctx = _parse("map<string,i8>")
    assert covers(covered, param_ctx, {})


def test_covers_struct_with_two_fields():
    """Test that a struct with two i8 fields covers struct<i8,i8>."""
    covered = struct([i8(nullable=False), i8(nullable=False)], nullable=False)
    param_ctx = _parse("struct<i8,i8>")
    assert covers(covered, param_ctx, {})


def test_covers_list_of_i16_fails_i8():
    """Test that a list of i16 does not cover list<i8>."""
    covered = list_(i16(nullable=False), nullable=False)
    param_ctx = _parse("list<i8>")
    assert not covers(covered, param_ctx, {})


def test_covers_map_i8_to_i16_fails():
    """Test that a map with i8 keys and i16 values does not cover map<i8,i8>."""
    covered = map_(
        key=i8(nullable=False),
        value=i16(nullable=False),
        nullable=False,
    )
    param_ctx = _parse("map<i8,i8>")
    assert not covers(covered, param_ctx, {})


def test_covers_struct_mismatched_types_fails():
    """Test that a struct with mismatched field types does not cover struct<i8,i8>."""
    covered = struct([i32(nullable=False), i8(nullable=False)], nullable=False)
    param_ctx = _parse("struct<i8,i8>")
    assert not covers(covered, param_ctx, {})


def test_all_function_types_from_yaml():
    """Test that all functions in YAML are registered with correct function_type.value."""
    # Test data with all function types
    test_cases = [
        (
            """%YAML 1.2
---
urn: extension:test:scalar_funcs
scalar_functions:
  - name: "add"
    description: "Add two numbers"
    impls:
      - args:
          - value: i8
          - value: i8
        return: i8
  - name: "test_fn"
    description: ""
    impls:
      - args:
          - value: i8
        variadic:
          min: 2
        return: i8
""",
            "extension:test:scalar_funcs",
            [
                ("add", [i8(nullable=False), i8(nullable=False)]),
                ("test_fn", [i8(nullable=False), i8(nullable=False)]),
            ],
            "scalar",
        ),
        (
            """%YAML 1.2
---
urn: extension:test:agg_funcs
aggregate_functions:
  - name: "count"
    description: "Count non-null values"
    impls:
      - args:
          - value: i8
        return: i64
  - name: "sum"
    description: "Sum values"
    impls:
      - args:
          - value: i8
        return: i64
""",
            "extension:test:agg_funcs",
            [("count", [i8(nullable=False)]), ("sum", [i8(nullable=False)])],
            "aggregate",
        ),
        (
            """%YAML 1.2
---
urn: extension:test:window_funcs
window_functions:
  - name: "row_number"
    description: "Assign row numbers"
    impls:
      - args: []
        return: i64
  - name: "rank"
    description: "Assign ranks"
    impls:
      - args: []
        return: i64
""",
            "extension:test:window_funcs",
            [("row_number", []), ("rank", [])],
            "window",
        ),
    ]

    for yaml_content, urn, functions, expected_type in test_cases:
        test_registry = ExtensionRegistry(load_default_extensions=False)
        test_registry.register_extension_dict(
            yaml.safe_load(yaml_content),
            uri=f"https://test.example.com/{urn.replace(':', '_')}.yaml",
        )

        for func_name, signature in functions:
            result = test_registry.lookup_function(
                urn=urn, function_name=func_name, signature=signature
            )
            assert result is not None, f"Failed to lookup {func_name} in {urn}"
            entry, _ = result
            assert hasattr(entry, "function_type"), (
                f"Entry for {func_name} missing function_type attribute"
            )
            assert entry.function_type is not None, (
                f"function_type is None for {func_name}"
            )
            assert isinstance(entry.function_type.value, str), (
                f"function_type.value is not a string for {func_name}"
            )
            assert entry.function_type.value == expected_type, (
                f"Expected function_type.value '{expected_type}' for {func_name}, "
                f"got '{entry.function_type.value}'"
            )
