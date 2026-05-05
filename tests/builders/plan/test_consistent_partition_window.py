"""Tests for ConsistentPartitionWindowRel plan builder.

Mirrors the Java test coverage from
ConsistentPartitionWindowRelRoundtripTest.java
"""

import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt
import yaml
from google.protobuf import json_format

from substrait.builders.extended_expression import column, window_function
from substrait.builders.plan import (
    consistent_partition_window,
    default_version,
    read_named_table,
)
from substrait.builders.type import i16, i32, i64
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema

content = """%YAML 1.2
---
urn: extension:test:urn
window_functions:
  - name: "lead"
    description: Lead window function
    impls:
      - args:
          - name: x
            value: i64
        nullability: DECLARED_OUTPUT
        decomposable: NONE
        return: i64

  - name: "lag"
    description: Lag window function
    impls:
      - args:
          - name: x
            value: i64
        nullability: DECLARED_OUTPUT
        decomposable: NONE
        return: i64

  - name: "row_number"
    description: Row number window function
    impls:
      - args: []
        nullability: DECLARED_OUTPUT
        decomposable: NONE
        return: i64
"""

registry = ExtensionRegistry(load_default_extensions=False)
registry.register_extension_dict(
    yaml.safe_load(content), uri="https://test.example.com/test.yaml"
)

struct = stt.Type.Struct(
    types=[i64(nullable=False), i16(nullable=False), i32(nullable=False)],
    nullability=stt.Type.NULLABILITY_REQUIRED,
)

named_struct = stt.NamedStruct(names=["a", "b", "c"], struct=struct)


def _ref_expr(field: int):
    """Helper: build a field reference expression for a struct field index."""
    return stalg.Expression(
        selection=stalg.Expression.FieldReference(
            direct_reference=stalg.Expression.ReferenceSegment(
                struct_field=stalg.Expression.ReferenceSegment.StructField(field=field)
            ),
            root_reference=stalg.Expression.FieldReference.RootReference(),
        )
    )


def test_consistent_partition_window_single():
    """Single window function with partition and sort.

    Mirrors Java's consistentPartitionWindowRoundtripSingle.
    """
    table = read_named_table("test", named_struct)

    lead_fn = window_function(
        "extension:test:urn",
        "lead",
        expressions=[column("a")],
        partitions=[column("b")],
        alias="lead_a",
    )

    actual = consistent_partition_window(
        table,
        window_functions=[lead_fn],
        partition_expressions=[column("b")],
        sorts=[(column("c"), stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST)],
    )(registry)

    ns = infer_plan_schema(table(None))
    lead_ee = lead_fn(ns, registry)

    expected = stp.Plan(
        version=default_version,
        extension_urns=list(lead_ee.extension_urns),
        extension_uris=list(lead_ee.extension_uris),
        extensions=list(lead_ee.extensions),
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        window=stalg.ConsistentPartitionWindowRel(
                            input=table(None).relations[-1].root.input,
                            window_functions=[
                                stalg.ConsistentPartitionWindowRel.WindowRelFunction(
                                    function_reference=lead_ee.referred_expr[
                                        0
                                    ].expression.window_function.function_reference,
                                    arguments=list(
                                        lead_ee.referred_expr[
                                            0
                                        ].expression.window_function.arguments
                                    ),
                                    output_type=lead_ee.referred_expr[
                                        0
                                    ].expression.window_function.output_type,
                                )
                            ],
                            partition_expressions=[_ref_expr(1)],
                            sorts=[
                                stalg.SortField(
                                    direction=stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST,
                                    expr=_ref_expr(2),
                                )
                            ],
                        )
                    ),
                    names=["a", "b", "c", "lead_a"],
                )
            )
        ],
    )

    assert actual == expected


def test_consistent_partition_window_multi():
    """Multiple window functions sharing the same partition/sort.

    Mirrors Java's consistentPartitionWindowRoundtripMulti.
    """
    table = read_named_table("test", named_struct)

    lead_fn = window_function(
        "extension:test:urn",
        "lead",
        expressions=[column("a")],
        partitions=[column("b")],
        alias="lead_a",
    )
    lag_fn = window_function(
        "extension:test:urn",
        "lag",
        expressions=[column("a")],
        partitions=[column("b")],
        alias="lag_a",
    )

    actual = consistent_partition_window(
        table,
        window_functions=[lead_fn, lag_fn],
        partition_expressions=[column("b")],
        sorts=[(column("c"), stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST)],
    )(registry)

    rel = actual.relations[0].root.input
    assert rel.HasField("window")
    window = rel.window

    assert len(window.window_functions) == 2
    assert len(window.partition_expressions) == 1
    assert len(window.sorts) == 1

    assert list(actual.relations[0].root.names) == ["a", "b", "c", "lead_a", "lag_a"]


def test_consistent_partition_window_sort_default_direction():
    """Sort without explicit direction defaults to ASC_NULLS_LAST."""
    table = read_named_table("test", named_struct)

    lead_fn = window_function(
        "extension:test:urn",
        "lead",
        expressions=[column("a")],
        partitions=[column("b")],
        alias="lead_a",
    )

    actual = consistent_partition_window(
        table,
        window_functions=[lead_fn],
        partition_expressions=[column("b")],
        sorts=[column("c")],
    )(registry)

    window = actual.relations[0].root.input.window
    assert window.sorts[0].direction == stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST


def test_consistent_partition_window_no_partitions_no_sorts():
    """Window with no partitions or sorts — entire input is one partition."""
    table = read_named_table("test", named_struct)

    lead_fn = window_function(
        "extension:test:urn",
        "lead",
        expressions=[column("a")],
        alias="lead_a",
    )

    actual = consistent_partition_window(
        table,
        window_functions=[lead_fn],
    )(registry)

    window = actual.relations[0].root.input.window
    assert len(window.window_functions) == 1
    assert len(window.partition_expressions) == 0
    assert len(window.sorts) == 0

    assert list(actual.relations[0].root.names) == ["a", "b", "c", "lead_a"]


def test_consistent_partition_window_schema_inference():
    """Output schema = input types + window function output types."""
    table = read_named_table("test", named_struct)

    lead_fn = window_function(
        "extension:test:urn",
        "lead",
        expressions=[column("a")],
        partitions=[column("b")],
        alias="lead_a",
    )
    lag_fn = window_function(
        "extension:test:urn",
        "lag",
        expressions=[column("a")],
        partitions=[column("b")],
        alias="lag_a",
    )

    actual = consistent_partition_window(
        table,
        window_functions=[lead_fn, lag_fn],
        partition_expressions=[column("b")],
        sorts=[(column("c"), stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST)],
    )(registry)

    ns = infer_plan_schema(actual)

    # 3 original + 2 window = 5
    assert len(ns.struct.types) == 5
    assert list(ns.names) == ["a", "b", "c", "lead_a", "lag_a"]

    # Original types preserved
    assert ns.struct.types[0].HasField("i64")
    assert ns.struct.types[1].HasField("i16")
    assert ns.struct.types[2].HasField("i32")

    # Window output types appended
    assert ns.struct.types[3].HasField("i64")
    assert ns.struct.types[4].HasField("i64")


def test_consistent_partition_window_roundtrip():
    """Proto serialization roundtrip — binary and JSON."""
    table = read_named_table("test", named_struct)

    lead_fn = window_function(
        "extension:test:urn",
        "lead",
        expressions=[column("a")],
        partitions=[column("b")],
        alias="lead_a",
    )

    plan = consistent_partition_window(
        table,
        window_functions=[lead_fn],
        partition_expressions=[column("b")],
        sorts=[(column("c"), stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST)],
    )(registry)

    # Binary roundtrip
    serialized = plan.SerializeToString()
    deserialized = stp.Plan()
    deserialized.ParseFromString(serialized)
    assert plan == deserialized

    # JSON roundtrip
    json_str = json_format.MessageToJson(plan)
    json_plan = json_format.Parse(json_str, stp.Plan())
    assert plan == json_plan


def test_consistent_partition_window_extension_references():
    """Extension URIs/URNs/declarations are properly propagated."""
    table = read_named_table("test", named_struct)

    lead_fn = window_function(
        "extension:test:urn",
        "lead",
        expressions=[column("a")],
        alias="lead_a",
    )

    actual = consistent_partition_window(
        table,
        window_functions=[lead_fn],
    )(registry)

    assert len(actual.extension_urns) > 0
    assert len(actual.extensions) > 0

    func_ext = actual.extensions[0].extension_function
    assert "lead" in func_ext.name


def test_consistent_partition_window_chained_with_project():
    """Window rel can be used as input to a project rel."""
    from substrait.builders.plan import project

    table = read_named_table("test", named_struct)

    lead_fn = window_function(
        "extension:test:urn",
        "lead",
        expressions=[column("a")],
        alias="lead_a",
    )

    windowed = consistent_partition_window(
        table,
        window_functions=[lead_fn],
        partition_expressions=[column("b")],
    )

    actual = project(windowed, expressions=[column("a")])(registry)

    assert isinstance(actual, stp.Plan)
    rel = actual.relations[0].root.input
    assert rel.HasField("project")
    assert rel.project.input.HasField("window")
