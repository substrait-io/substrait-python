"""Tests for the fluent DataFrame facade (substrait.frame / substrait.api).

Each fluent chain is checked against the equivalent raw builder pipeline for
byte-identical protobuf output.
"""

import pytest
import substrait.algebra_pb2 as stalg

import substrait.api as sub
from substrait.builders.extended_expression import (
    aggregate_function,
    column,
    literal,
    scalar_function,
)
from substrait.builders.plan import aggregate as b_aggregate
from substrait.builders.plan import fetch as b_fetch
from substrait.builders.plan import filter as b_filter
from substrait.builders.plan import join as b_join
from substrait.builders.plan import read_named_table as b_read
from substrait.builders.plan import select as b_select
from substrait.builders.plan import sort as b_sort
from substrait.builders.type import fp64, i64, named_struct, string, struct
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=True)

COMPARISON = "extension:io.substrait:functions_comparison"
ARITHMETIC = "extension:io.substrait:functions_arithmetic"


def people_ns():
    # Matches the {name: sub.<type>} dict form, whose columns default to nullable.
    return named_struct(
        names=["id", "age", "name"],
        struct=struct(types=[i64(), i64(), string()], nullable=False),
    )


def people_df():
    return sub.read_named_table(
        "people", {"id": sub.i64, "age": sub.i64, "name": sub.string}
    )


def test_schema_dict_matches_named_struct():
    # A {name: type} dict must build the same NamedStruct as the explicit form.
    from_dict = sub.read_named_table(
        "people", {"id": sub.i64, "age": sub.i64, "name": sub.string}
    ).to_plan()
    explicit = b_read("people", people_ns())(registry)
    assert from_dict.SerializeToString() == explicit.SerializeToString()


def test_filter_select_matches_builder():
    fluent = people_df().filter(sub.col("age") > 25).select("id").to_plan()

    raw = b_select(
        b_filter(
            b_read("people", people_ns()),
            expression=scalar_function(
                COMPARISON, "gt", expressions=[column("age"), literal(25, i64())]
            ),
        ),
        expressions=[column("id")],
    )(registry)

    assert fluent.SerializeToString() == raw.SerializeToString()


def test_with_columns_named_appends_projection():
    fluent = people_df().with_columns(bonus=sub.col("age") + 1).to_plan()
    # ProjectRel appends: output has original columns + the new one.
    root = fluent.relations[-1].root.input
    assert root.HasField("project")
    assert len(root.project.expressions) == 1  # the appended bonus expression


def test_sort_descending_matches_builder():
    fluent = people_df().sort("age", descending=True).to_plan()
    raw = b_sort(
        b_read("people", people_ns()),
        expressions=[(column("age"), stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST)],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_limit_matches_builder_fetch():
    fluent = people_df().limit(5).to_plan()
    raw = b_fetch(
        b_read("people", people_ns()),
        offset=literal(0, i64()),
        count=literal(5, i64()),
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_join_matches_builder():
    left_ns = named_struct(
        names=["cust_id", "name"],
        struct=struct(types=[i64(), string()], nullable=False),
    )
    right_ns = named_struct(
        names=["order_id", "cust_ref", "amount"],
        struct=struct(types=[i64(), i64(), fp64()], nullable=False),
    )

    left = sub.read_named_table("customers", {"cust_id": sub.i64, "name": sub.string})
    right = sub.read_named_table(
        "orders", {"order_id": sub.i64, "cust_ref": sub.i64, "amount": sub.fp64}
    )
    fluent = left.join(
        right, on=sub.col("cust_id") == sub.col("cust_ref"), how="inner"
    ).to_plan()

    raw = b_join(
        b_read("customers", left_ns),
        b_read("orders", right_ns),
        expression=scalar_function(
            COMPARISON, "equal", expressions=[column("cust_id"), column("cust_ref")]
        ),
        type=stalg.JoinRel.JOIN_TYPE_INNER,
    )(registry)

    assert fluent.SerializeToString() == raw.SerializeToString()


def test_join_unknown_type_raises():
    left = sub.read_named_table("a", {"x": sub.i64})
    right = sub.read_named_table("b", {"x": sub.i64})
    with pytest.raises(ValueError, match="unknown join type"):
        left.join(right, on=sub.col("x") == sub.col("x"), how="banana")


def test_group_by_agg_matches_builder():
    ns = named_struct(
        names=["region", "amount"],
        struct=struct(types=[string(), fp64()], nullable=False),
    )
    fluent = (
        sub.read_named_table("sales", {"region": sub.string, "amount": sub.fp64})
        .group_by("region")
        .agg(sub.f.sum(sub.col("amount")).alias("total"))
        .to_plan()
    )
    raw = b_aggregate(
        b_read("sales", ns),
        grouping_expressions=[column("region")],
        measures=[
            aggregate_function(
                ARITHMETIC, "sum", expressions=[column("amount")], alias="total"
            )
        ],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_group_by_agg_equals_aggregate_oneshot():
    df = sub.read_named_table("sales", {"region": sub.string, "amount": sub.fp64})
    via_groupby = (
        df.group_by("region").agg(sub.f.sum(sub.col("amount")).alias("t")).to_plan()
    )
    via_aggregate = df.aggregate(
        "region", sub.f.sum(sub.col("amount")).alias("t")
    ).to_plan()
    assert via_groupby.SerializeToString() == via_aggregate.SerializeToString()


def test_default_registry_is_reused():
    assert sub.default_registry() is sub.default_registry()


def test_to_substrait_registry_override():
    df = people_df()
    custom = ExtensionRegistry(load_default_extensions=True)
    # Should not raise and should honor the explicit registry.
    plan = df.filter(sub.col("age") > 25).to_substrait(registry=custom)
    assert plan.relations
