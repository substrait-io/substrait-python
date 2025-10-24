"""
Comprehensive test suite for URI <-> URN migration.

Tests registry integration, dual URI/URN output, and round-trip conversions
during the migration period from URI to URN-based extension identifiers.

NOTE: This file is temporary and can be removed once the URI -> URN migration
is complete across all Substrait implementations. At that point, only URN-based
extension references will be used, and the UriUrnBiDiMap will no longer be needed.

Note: Tests for the UriUrnBiDiMap class itself are in test_bimap.py
"""

import yaml

import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.extended_expression_pb2 as stee
import substrait.gen.proto.extensions.extensions_pb2 as ste
from substrait.builders.extended_expression import (
    scalar_function,
    literal,
    column,
    aggregate_function,
)
from substrait.builders.type import i64
from substrait.builders.plan import read_named_table, aggregate, project, filter
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema

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
        assert registry._uri_urn_bimap.get_urn(uri) == "extension:test:functions_paired"
        assert registry._uri_urn_bimap.get_uri("extension:test:functions_paired") == uri


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


# ============================================================================
# Plan Builder URI/URN Output Tests
# ============================================================================


class TestPlanOutput:
    """Tests that plan builders output both URI and URN in proto plans."""

    def test_project_with_scalar_function(self):
        """Test that project plans with scalar functions have both URI and URN in proto."""
        content = """%YAML 1.2
---
urn: extension:test:math
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
            yaml.safe_load(content), uri="https://test.example.com/math.yaml"
        )

        struct = stt.Type.Struct(types=[i64(nullable=False), i64(nullable=False)])
        named_struct = stt.NamedStruct(names=["a", "b"], struct=struct)

        table = read_named_table("table", named_struct)
        add_expr = scalar_function(
            "extension:test:math",
            "add",
            expressions=[column("a"), column("b")],
            alias=["add"],
        )

        actual = project(table, [add_expr])(registry)

        ns = infer_plan_schema(table(None))

        expected = stp.Plan(
            extension_urns=[
                ste.SimpleExtensionURN(extension_urn_anchor=1, urn="extension:test:math")
            ],
            extension_uris=[
                ste.SimpleExtensionURI(
                    extension_uri_anchor=1, uri="https://test.example.com/math.yaml"
                )
            ],
            extensions=[
                ste.SimpleExtensionDeclaration(
                    extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                        extension_urn_reference=1,
                        extension_uri_reference=1,
                        function_anchor=1,
                        name="add:i64_i64",
                    )
                )
            ],
            relations=[
                stp.PlanRel(
                    root=stalg.RelRoot(
                        input=stalg.Rel(
                            project=stalg.ProjectRel(
                                common=stalg.RelCommon(emit=stalg.RelCommon.Emit(output_mapping=[2])),
                                input=table(None).relations[-1].root.input,
                                expressions=[add_expr(ns, registry).referred_expr[0].expression],
                            )
                        ),
                        names=["add"],
                    )
                )
            ],
        )

        assert actual == expected

    def test_filter_with_scalar_function(self):
        """Test that filter plans with scalar functions have both URI and URN in proto."""
        content = """%YAML 1.2
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
            yaml.safe_load(content), uri="https://test.example.com/comparison.yaml"
        )

        struct = stt.Type.Struct(types=[i64(nullable=False)])
        named_struct = stt.NamedStruct(names=["value"], struct=struct)

        table = read_named_table("table", named_struct)
        gt_expr = scalar_function(
            "extension:test:comparison",
            "greater_than",
            expressions=[column("value"), literal(100, i64(nullable=False))],
        )

        actual = filter(table, gt_expr)(registry)

        ns = infer_plan_schema(table(None))

        expected = stp.Plan(
            extension_urns=[
                ste.SimpleExtensionURN(
                    extension_urn_anchor=1, urn="extension:test:comparison"
                )
            ],
            extension_uris=[
                ste.SimpleExtensionURI(
                    extension_uri_anchor=1, uri="https://test.example.com/comparison.yaml"
                )
            ],
            extensions=[
                ste.SimpleExtensionDeclaration(
                    extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                        extension_urn_reference=1,
                        extension_uri_reference=1,
                        function_anchor=1,
                        name="greater_than:i64_i64",
                    )
                )
            ],
            relations=[
                stp.PlanRel(
                    root=stalg.RelRoot(
                        input=stalg.Rel(
                            filter=stalg.FilterRel(
                                input=table(None).relations[-1].root.input,
                                condition=gt_expr(ns, registry).referred_expr[0].expression,
                            )
                        ),
                        names=["value"],
                    )
                )
            ],
        )

        assert actual == expected

    def test_aggregate_with_aggregate_function(self):
        """Test that aggregate plans with aggregate functions have both URI and URN in proto."""
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
            "extension:test:aggregate", "sum", expressions=[column("value")], alias=["sum"]
        )

        actual = aggregate(table, grouping_expressions=[column("id")], measures=[sum_expr])(
            registry
        )

        ns = infer_plan_schema(table(None))

        expected = stp.Plan(
            extension_urns=[
                ste.SimpleExtensionURN(
                    extension_urn_anchor=1, urn="extension:test:aggregate"
                )
            ],
            extension_uris=[
                ste.SimpleExtensionURI(
                    extension_uri_anchor=1, uri="https://test.example.com/aggregate.yaml"
                )
            ],
            extensions=[
                ste.SimpleExtensionDeclaration(
                    extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                        extension_urn_reference=1,
                        extension_uri_reference=1,
                        function_anchor=1,
                        name="sum:i64",
                    )
                )
            ],
            relations=[
                stp.PlanRel(
                    root=stalg.RelRoot(
                        input=stalg.Rel(
                            aggregate=stalg.AggregateRel(
                                input=table(None).relations[-1].root.input,
                                grouping_expressions=[
                                    column("id")(ns, registry).referred_expr[0].expression
                                ],
                                groupings=[
                                    stalg.AggregateRel.Grouping(
                                        grouping_expressions=[
                                            column("id")(ns, registry).referred_expr[0].expression
                                        ],
                                        expression_references=[0],
                                    )
                                ],
                                measures=[
                                    stalg.AggregateRel.Measure(
                                        measure=sum_expr(ns, registry).referred_expr[0].measure
                                    )
                                ],
                            )
                        ),
                        names=["id", "sum"],
                    )
                )
            ],
        )

        assert actual == expected
