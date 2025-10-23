"""
Tests to verify that plan builders always output both URI and URN extensions.

This ensures backward compatibility during the URI → URN migration period.
All plans produced by the builders should contain both SimpleExtensionURI
and SimpleExtensionURN entries, along with both extension_uri_reference
and extension_urn_reference in function declarations.
"""

import yaml

import substrait.gen.proto.type_pb2 as stt
from substrait.builders.type import i64
from substrait.builders.plan import read_named_table, aggregate, project, filter
from substrait.builders.extended_expression import (
    column,
    aggregate_function,
    scalar_function,
    literal,
)
from substrait.extension_registry import ExtensionRegistry


def test_plan_with_scalar_function_has_both_uri_and_urn():
    """Test that plans with scalar functions output both URI and URN."""
    content = """%YAML 1.2
---
urn: extension:test:functions
scalar_functions:
  - name: "add"
    description: ""
    impls:
      - args:
          - value: i64
          - value: i64
        return: i64
"""
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(
        yaml.safe_load(content), uri="https://test.example.com/functions.yaml"
    )

    struct = stt.Type.Struct(types=[i64(nullable=False), i64(nullable=False)])
    named_struct = stt.NamedStruct(names=["a", "b"], struct=struct)

    table = read_named_table("table", named_struct)
    add_expr = scalar_function(
        "extension:test:functions",
        "add",
        expressions=[column("a"), column("b")],
    )

    plan = project(table, [add_expr])(registry)

    # Verify both URI and URN are present
    assert len(plan.extension_uris) > 0, "Plan should have extension URIs"
    assert len(plan.extension_urns) > 0, "Plan should have extension URNs"

    # Verify they match
    assert (
        plan.extension_uris[0].uri == "https://test.example.com/functions.yaml"
    ), "URI should match"
    assert (
        plan.extension_urns[0].urn == "extension:test:functions"
    ), "URN should match"

    # Verify URI and URN use the SAME anchor
    assert (
        plan.extension_uris[0].extension_uri_anchor
        == plan.extension_urns[0].extension_urn_anchor
    ), "URI and URN should share the same anchor"

    # Verify extension declarations have both references (also the same)
    assert len(plan.extensions) > 0, "Plan should have extension declarations"
    ext_func = plan.extensions[0].extension_function
    assert (
        ext_func.extension_uri_reference > 0
    ), "Extension function should reference URI"
    assert (
        ext_func.extension_urn_reference > 0
    ), "Extension function should reference URN"
    assert (
        ext_func.extension_uri_reference == ext_func.extension_urn_reference
    ), "URI and URN references should be the same"


def test_plan_with_aggregate_function_has_both_uri_and_urn():
    """Test that plans with aggregate functions output both URI and URN."""
    content = """%YAML 1.2
---
urn: extension:test:aggregate
aggregate_functions:
  - name: "sum"
    description: ""
    impls:
      - args:
          - value: i64
        nullability: DECLARED_OUTPUT
        decomposable: MANY
        intermediate: i64
        return: i64
"""
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(
        yaml.safe_load(content), uri="https://test.example.com/aggregate.yaml"
    )

    struct = stt.Type.Struct(types=[i64(nullable=False), i64(nullable=False)])
    named_struct = stt.NamedStruct(names=["id", "value"], struct=struct)

    table = read_named_table("table", named_struct)
    sum_expr = aggregate_function(
        "extension:test:aggregate", "sum", expressions=[column("value")]
    )

    plan = aggregate(table, grouping_expressions=[column("id")], measures=[sum_expr])(
        registry
    )

    # Verify both URI and URN are present
    assert len(plan.extension_uris) > 0, "Plan should have extension URIs"
    assert len(plan.extension_urns) > 0, "Plan should have extension URNs"

    # Verify they match
    assert (
        plan.extension_uris[0].uri == "https://test.example.com/aggregate.yaml"
    ), "URI should match"
    assert (
        plan.extension_urns[0].urn == "extension:test:aggregate"
    ), "URN should match"

    # Verify extension declarations have both references
    assert len(plan.extensions) > 0, "Plan should have extension declarations"
    ext_func = plan.extensions[0].extension_function
    assert (
        ext_func.extension_uri_reference > 0
    ), "Extension function should reference URI"
    assert (
        ext_func.extension_urn_reference > 0
    ), "Extension function should reference URN"


def test_plan_with_multiple_extensions_has_all_uris_and_urns():
    """Test that plans with multiple extensions output all URIs and URNs."""
    content1 = """%YAML 1.2
---
urn: extension:test:math
scalar_functions:
  - name: "multiply"
    description: ""
    impls:
      - args:
          - value: i64
          - value: i64
        return: i64
"""

    content2 = """%YAML 1.2
---
urn: extension:test:comparison
scalar_functions:
  - name: "greater_than"
    description: ""
    impls:
      - args:
          - value: i64
          - value: i64
        return: boolean
"""

    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_dict(
        yaml.safe_load(content1), uri="https://test.example.com/math.yaml"
    )
    registry.register_extension_dict(
        yaml.safe_load(content2), uri="https://test.example.com/comparison.yaml"
    )

    struct = stt.Type.Struct(types=[i64(nullable=False), i64(nullable=False)])
    named_struct = stt.NamedStruct(names=["a", "b"], struct=struct)

    table = read_named_table("table", named_struct)

    # Use both extensions
    multiply_expr = scalar_function(
        "extension:test:math",
        "multiply",
        expressions=[column("a"), column("b")],
    )
    gt_expr = scalar_function(
        "extension:test:comparison",
        "greater_than",
        expressions=[multiply_expr, literal(100, i64(nullable=False))],
    )

    plan = filter(table, gt_expr)(registry)

    # Verify both extensions have URIs and URNs
    assert len(plan.extension_uris) == 2, "Plan should have 2 extension URIs"
    assert len(plan.extension_urns) == 2, "Plan should have 2 extension URNs"

    # Collect URIs and URNs
    uris = {ext.uri for ext in plan.extension_uris}
    urns = {ext.urn for ext in plan.extension_urns}

    assert "https://test.example.com/math.yaml" in uris
    assert "https://test.example.com/comparison.yaml" in uris
    assert "extension:test:math" in urns
    assert "extension:test:comparison" in urns

    # Verify all extension declarations have both references
    assert len(plan.extensions) == 2, "Plan should have 2 extension declarations"
    for ext_decl in plan.extensions:
        ext_func = ext_decl.extension_function
        assert (
            ext_func.extension_uri_reference > 0
        ), "Extension function should reference URI"
        assert (
            ext_func.extension_urn_reference > 0
        ), "Extension function should reference URN"


def test_plan_with_default_extensions_has_both_uri_and_urn():
    """Test that plans using default extensions output both URI and URN."""
    # Use default registry with built-in extensions
    registry = ExtensionRegistry(load_default_extensions=True)

    struct = stt.Type.Struct(types=[i64(nullable=False), i64(nullable=False)])
    named_struct = stt.NamedStruct(names=["a", "b"], struct=struct)

    table = read_named_table("table", named_struct)

    # Use a function from the default extensions
    add_expr = scalar_function(
        "extension:io.substrait:functions_arithmetic",
        "add",
        expressions=[column("a"), column("b")],
    )

    plan = project(table, [add_expr])(registry)

    # Verify both URI and URN are present
    assert len(plan.extension_uris) > 0, "Plan should have extension URIs"
    assert len(plan.extension_urns) > 0, "Plan should have extension URNs"

    # Verify URN matches
    assert any(
        ext.urn == "extension:io.substrait:functions_arithmetic"
        for ext in plan.extension_urns
    ), "Should have arithmetic functions URN"

    # Verify URI is present and matches the GitHub URL pattern
    assert any(
        "functions_arithmetic.yaml" in ext.uri for ext in plan.extension_uris
    ), "Should have arithmetic functions URI"

    # Verify extension declarations have both references
    assert len(plan.extensions) > 0, "Plan should have extension declarations"
    ext_func = plan.extensions[0].extension_function
    assert (
        ext_func.extension_uri_reference > 0
    ), "Extension function should reference URI"
    assert (
        ext_func.extension_urn_reference > 0
    ), "Extension function should reference URN"
