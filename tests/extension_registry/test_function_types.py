"""Tests for function types (scalar, aggregate, window)."""

import textwrap

import pytest
import yaml

from substrait.builders.type import i8
from substrait.extension_registry import ExtensionRegistry


@pytest.mark.parametrize(
    "test_case",
    [
        # Scalar functions
        pytest.param(
            {
                "yaml_content": textwrap.dedent("""\
                    %YAML 1.2
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
                    """),
                "urn": "extension:test:scalar_funcs",
                "func_name": "add",
                "signature": [i8(nullable=False), i8(nullable=False)],
                "expected_type": "scalar",
            },
            id="scalar-add",
        ),
        pytest.param(
            {
                "yaml_content": textwrap.dedent("""\
                    %YAML 1.2
                    ---
                    urn: extension:test:scalar_funcs
                    scalar_functions:
                      - name: "test_fn"
                        description: ""
                        impls:
                          - args:
                              - value: i8
                            variadic:
                              min: 2
                            return: i8
                    """),
                "urn": "extension:test:scalar_funcs",
                "func_name": "test_fn",
                "signature": [i8(nullable=False), i8(nullable=False)],
                "expected_type": "scalar",
            },
            id="scalar-test_fn",
        ),
        # Aggregate functions
        pytest.param(
            {
                "yaml_content": textwrap.dedent("""\
                    %YAML 1.2
                    ---
                    urn: extension:test:agg_funcs
                    aggregate_functions:
                      - name: "count"
                        description: "Count non-null values"
                        impls:
                          - args:
                              - value: i8
                            return: i64
                    """),
                "urn": "extension:test:agg_funcs",
                "func_name": "count",
                "signature": [i8(nullable=False)],
                "expected_type": "aggregate",
            },
            id="aggregate-count",
        ),
        pytest.param(
            {
                "yaml_content": textwrap.dedent("""\
                    %YAML 1.2
                    ---
                    urn: extension:test:agg_funcs
                    aggregate_functions:
                      - name: "sum"
                        description: "Sum values"
                        impls:
                          - args:
                              - value: i8
                            return: i64
                    """),
                "urn": "extension:test:agg_funcs",
                "func_name": "sum",
                "signature": [i8(nullable=False)],
                "expected_type": "aggregate",
            },
            id="aggregate-sum",
        ),
        # Window functions
        pytest.param(
            {
                "yaml_content": textwrap.dedent("""\
                    %YAML 1.2
                    ---
                    urn: extension:test:window_funcs
                    window_functions:
                      - name: "row_number"
                        description: "Assign row numbers"
                        impls:
                          - args: []
                            return: i64
                    """),
                "urn": "extension:test:window_funcs",
                "func_name": "row_number",
                "signature": [],
                "expected_type": "window",
            },
            id="window-row_number",
        ),
        pytest.param(
            {
                "yaml_content": textwrap.dedent("""\
                    %YAML 1.2
                    ---
                    urn: extension:test:window_funcs
                    window_functions:
                      - name: "rank"
                        description: "Assign ranks"
                        impls:
                          - args: []
                            return: i64
                    """),
                "urn": "extension:test:window_funcs",
                "func_name": "rank",
                "signature": [],
                "expected_type": "window",
            },
            id="window-rank",
        ),
    ],
)
def test_all_function_types_from_yaml(test_case):
    """Test that all functions in YAML are registered with correct function_type.value."""
    test_registry = ExtensionRegistry(load_default_extensions=False)
    test_registry.register_extension_dict(
        yaml.safe_load(test_case["yaml_content"]),
        uri=f"https://test.example.com/{test_case['urn'].replace(':', '_')}.yaml",
    )

    result = test_registry.lookup_function(
        urn=test_case["urn"],
        function_name=test_case["func_name"],
        signature=test_case["signature"],
    )
    assert result is not None, (
        f"Failed to lookup {test_case['func_name']} in {test_case['urn']}"
    )
    entry, _ = result
    assert hasattr(entry, "function_type"), (
        f"Entry for {test_case['func_name']} missing function_type attribute"
    )
    assert entry.function_type is not None, (
        f"function_type is None for {test_case['func_name']}"
    )
    assert isinstance(entry.function_type.value, str), (
        f"function_type.value is not a string for {test_case['func_name']}"
    )
    assert entry.function_type.value == test_case["expected_type"], (
        f"Expected function_type.value '{test_case['expected_type']}' "
        f"for {test_case['func_name']}, got '{entry.function_type.value}'"
    )
