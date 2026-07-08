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
from substrait.builders.plan import cross as b_cross
from substrait.builders.plan import extension_table as b_extension_table
from substrait.builders.plan import fetch as b_fetch
from substrait.builders.plan import filter as b_filter
from substrait.builders.plan import join as b_join
from substrait.builders.plan import local_files as b_local_files
from substrait.builders.plan import read_named_table as b_read
from substrait.builders.plan import select as b_select
from substrait.builders.plan import set as b_set
from substrait.builders.plan import sort as b_sort
from substrait.builders.plan import virtual_table as b_virtual_table
from substrait.builders.plan import write_named_table as b_write
from substrait.builders.type import fp64, i64, named_struct, string, struct
from substrait.extension_registry import ExtensionRegistry
from substrait.frame import _JOIN_TYPES

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


@pytest.mark.parametrize(
    "descending, nulls_last, direction",
    [
        (False, False, stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST),
        (False, True, stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST),
        (True, False, stalg.SortField.SORT_DIRECTION_DESC_NULLS_FIRST),
        (True, True, stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST),
    ],
)
def test_sort_direction_combinations_match_builder(descending, nulls_last, direction):
    fluent = (
        people_df().sort("age", descending=descending, nulls_last=nulls_last).to_plan()
    )
    raw = b_sort(
        b_read("people", people_ns()),
        expressions=[(column("age"), direction)],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_sort_per_column_directions_match_builder():
    fluent = (
        people_df()
        .sort("age", "id", descending=[True, False], nulls_last=[True, False])
        .to_plan()
    )
    raw = b_sort(
        b_read("people", people_ns()),
        expressions=[
            (column("age"), stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST),
            (column("id"), stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST),
        ],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_sort_per_column_length_mismatch_raises():
    with pytest.raises(ValueError, match="but 2 sort columns"):
        people_df().sort("age", "id", descending=[True])


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


@pytest.mark.parametrize("how, join_type", sorted(_JOIN_TYPES.items()))
def test_join_all_types_match_builder(how, join_type):
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
        right, on=sub.col("cust_id") == sub.col("cust_ref"), how=how
    ).to_plan()
    raw = b_join(
        b_read("customers", left_ns),
        b_read("orders", right_ns),
        expression=scalar_function(
            COMPARISON, "equal", expressions=[column("cust_id"), column("cust_ref")]
        ),
        type=join_type,
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


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


# -- Phase 4: grouping sets / rollup / cube, FILTER, DISTINCT, ordered -----


def _sales_ns():
    return named_struct(
        names=["region", "dept", "amount", "status"],
        struct=struct(types=[string(), string(), fp64(), string()], nullable=False),
    )


def _sales_df():
    return sub.read_named_table(
        "sales",
        {
            "region": sub.string,
            "dept": sub.string,
            "amount": sub.fp64,
            "status": sub.string,
        },
    )


@pytest.mark.parametrize(
    "group, sets",
    [
        (lambda df: df.rollup("region", "dept"), [[0, 1], [0], []]),
        (lambda df: df.cube("region", "dept"), [[0, 1], [0], [1], []]),
        (
            lambda df: df.group_by(
                "region", "dept", grouping_sets=[["region", "dept"], ["region"], []]
            ),
            [[0, 1], [0], []],
        ),
    ],
)
def test_grouping_sets_match_builder(group, sets):
    fluent = group(_sales_df()).agg(sub.f.sum(sub.col("amount")).alias("t")).to_plan()
    raw = b_aggregate(
        b_read("sales", _sales_ns()),
        grouping_expressions=[column("region"), column("dept")],
        measures=[
            aggregate_function(
                ARITHMETIC, "sum", expressions=[column("amount")], alias="t"
            )
        ],
        grouping_sets=sets,
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_agg_filter_matches_builder():
    fluent = (
        _sales_df()
        .group_by("region")
        .agg(
            sub.f.sum(sub.col("amount"))
            .filter(sub.col("status") == "paid")
            .alias("paid")
        )
        .to_plan()
    )
    raw = b_aggregate(
        b_read("sales", _sales_ns()),
        grouping_expressions=[column("region")],
        measures=[
            aggregate_function(
                ARITHMETIC, "sum", expressions=[column("amount")], alias="paid"
            )
        ],
        filters=[
            scalar_function(
                COMPARISON,
                "equal",
                expressions=[column("status"), literal("paid", string())],
            )
        ],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_agg_distinct_matches_builder():
    fluent = (
        _sales_df()
        .group_by("region")
        .agg(sub.f.sum(sub.col("amount")).distinct().alias("s"))
        .to_plan()
    )
    raw = b_aggregate(
        b_read("sales", _sales_ns()),
        grouping_expressions=[column("region")],
        measures=[
            aggregate_function(
                ARITHMETIC,
                "sum",
                expressions=[column("amount")],
                alias="s",
                invocation=stalg.AggregateFunction.AGGREGATION_INVOCATION_DISTINCT,
            )
        ],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_agg_order_by_matches_builder():
    fluent = (
        _sales_df()
        .group_by("region")
        .agg(sub.f.sum(sub.col("amount")).order_by("dept", descending=True).alias("s"))
        .to_plan()
    )
    raw = b_aggregate(
        b_read("sales", _sales_ns()),
        grouping_expressions=[column("region")],
        measures=[
            aggregate_function(
                ARITHMETIC,
                "sum",
                expressions=[column("amount")],
                alias="s",
                sorts=[
                    (column("dept"), stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST)
                ],
            )
        ],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_grouping_sets_unknown_key_raises():
    with pytest.raises(ValueError, match="not a group_by key"):
        _sales_df().group_by("region", grouping_sets=[["nope"]])


def test_distinct_on_non_measure_raises():
    with pytest.raises(TypeError, match="aggregate measures"):
        _sales_df().select(sub.col("region").distinct()).to_plan()


# -- Phase 5: read sources (virtual table, local files, extension table) --


def test_from_records_matches_builder():
    ns = named_struct(
        names=["id", "name"], struct=struct(types=[i64(), string()], nullable=False)
    )
    fluent = sub.from_records(
        [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
        {"id": sub.i64, "name": sub.string},
    ).to_plan()
    raw = b_virtual_table(
        [
            [literal(1, i64()), literal("a", string())],
            [literal(2, i64()), literal("b", string())],
        ],
        ns,
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_from_records_positional_matches_dict():
    schema = {"id": sub.i64, "name": sub.string}
    by_dict = sub.from_records([{"id": 1, "name": "a"}], schema).to_plan()
    by_tuple = sub.from_records([(1, "a")], schema).to_plan()
    assert by_dict.SerializeToString() == by_tuple.SerializeToString()


def test_from_records_null_is_typed_null():
    plan = sub.from_records([{"id": None}], {"id": sub.i64}).to_plan()
    lit0 = plan.relations[-1].root.input.read.virtual_table.expressions[0].fields[0]
    assert lit0.literal.WhichOneof("literal_type") == "null"


def test_from_records_row_length_mismatch_raises():
    with pytest.raises(ValueError, match="but schema has"):
        sub.from_records([(1, 2)], {"id": sub.i64})


def test_read_parquet_matches_builder():
    ns = named_struct(names=["id"], struct=struct(types=[i64()], nullable=False))
    fof = stalg.ReadRel.LocalFiles.FileOrFiles
    fluent = sub.read_parquet("f.parquet", {"id": sub.i64}).to_plan()
    raw = b_local_files(
        ns, [fof(uri_file="f.parquet", parquet=fof.ParquetReadOptions())]
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_read_csv_matches_builder():
    ns = named_struct(names=["id"], struct=struct(types=[i64()], nullable=False))
    fof = stalg.ReadRel.LocalFiles.FileOrFiles
    fluent = sub.read_csv(
        ["a.csv", "b.csv"], {"id": sub.i64}, delimiter=";", header_lines_to_skip=2
    ).to_plan()
    text = fof.DelimiterSeparatedTextReadOptions(
        field_delimiter=";", header_lines_to_skip=2
    )
    raw = b_local_files(
        ns,
        [fof(uri_file="a.csv", text=text), fof(uri_file="b.csv", text=text)],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_read_extension_table_matches_builder():
    from google.protobuf.any_pb2 import Any

    ns = named_struct(names=["id"], struct=struct(types=[i64()], nullable=False))
    detail = Any(type_url="example.com/Foo", value=b"payload")
    fluent = sub.read_extension_table({"id": sub.i64}, detail).to_plan()
    raw = b_extension_table(ns, detail)(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_default_registry_is_reused():
    assert sub.default_registry() is sub.default_registry()


def test_to_substrait_registry_override():
    df = people_df()
    custom = ExtensionRegistry(load_default_extensions=True)
    # Should not raise and should honor the explicit registry.
    plan = df.filter(sub.col("age") > 25).to_substrait(registry=custom)
    assert plan.relations


# -- Phase 1: set ops, cross join, write sink -----------------------------


@pytest.mark.parametrize(
    "call, op",
    [
        (lambda a, b: a.union(b), stalg.SetRel.SET_OP_UNION_ALL),
        (lambda a, b: a.union(b, distinct=True), stalg.SetRel.SET_OP_UNION_DISTINCT),
        (
            lambda a, b: a.intersect(b),
            stalg.SetRel.SET_OP_INTERSECTION_MULTISET,
        ),
        (
            lambda a, b: a.intersect(b, distinct=False),
            stalg.SetRel.SET_OP_INTERSECTION_MULTISET_ALL,
        ),
        (lambda a, b: a.except_(b), stalg.SetRel.SET_OP_MINUS_PRIMARY),
        (
            lambda a, b: a.except_(b, distinct=False),
            stalg.SetRel.SET_OP_MINUS_PRIMARY_ALL,
        ),
    ],
)
def test_set_ops_match_builder(call, op):
    cols = {"id": sub.i64, "age": sub.i64, "name": sub.string}
    fluent = call(
        sub.read_named_table("a", cols), sub.read_named_table("b", cols)
    ).to_plan()
    raw = b_set([b_read("a", people_ns()), b_read("b", people_ns())], op)(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_union_nary_matches_builder():
    cols = {"id": sub.i64, "age": sub.i64, "name": sub.string}
    fluent = (
        sub.read_named_table("a", cols)
        .union(sub.read_named_table("b", cols), sub.read_named_table("c", cols))
        .to_plan()
    )
    raw = b_set(
        [b_read("a", people_ns()), b_read("b", people_ns()), b_read("c", people_ns())],
        stalg.SetRel.SET_OP_UNION_ALL,
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_union_without_others_raises():
    with pytest.raises(ValueError, match="at least one other"):
        people_df().union()


def test_cross_join_matches_builder():
    left_ns = named_struct(
        names=["cust_id", "name"],
        struct=struct(types=[i64(), string()], nullable=False),
    )
    right_ns = named_struct(
        names=["order_id", "amount"],
        struct=struct(types=[i64(), fp64()], nullable=False),
    )
    left = sub.read_named_table("customers", {"cust_id": sub.i64, "name": sub.string})
    right = sub.read_named_table("orders", {"order_id": sub.i64, "amount": sub.fp64})
    fluent = left.cross_join(right).to_plan()
    raw = b_cross(b_read("customers", left_ns), b_read("orders", right_ns))(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_write_named_table_matches_builder():
    fluent = people_df().write_named_table("people_copy").to_plan()
    raw = b_write("people_copy", b_read("people", people_ns()))(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_write_replace_mode_matches_builder():
    fluent = people_df().write_named_table("people_copy", mode="replace").to_plan()
    raw = b_write(
        "people_copy",
        b_read("people", people_ns()),
        create_mode=stalg.WriteRel.CREATE_MODE_REPLACE_IF_EXISTS,
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_write_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown write mode"):
        people_df().write_named_table("t", mode="banana")


# -- Phase 3 (finish): post_filter, head/offset, rename/drop --------------


def test_join_post_filter_matches_builder():
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
        right,
        on=sub.col("cust_id") == sub.col("cust_ref"),
        post_filter=sub.col("amount") > 100.0,
    ).to_plan()
    raw = b_join(
        b_read("customers", left_ns),
        b_read("orders", right_ns),
        expression=scalar_function(
            COMPARISON, "equal", expressions=[column("cust_id"), column("cust_ref")]
        ),
        type=stalg.JoinRel.JOIN_TYPE_INNER,
        post_join_filter=scalar_function(
            COMPARISON, "gt", expressions=[column("amount"), literal(100.0, fp64())]
        ),
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_head_matches_limit():
    assert (
        people_df().head(3).to_plan().SerializeToString()
        == people_df().limit(3).to_plan().SerializeToString()
    )


def test_offset_matches_builder():
    fluent = people_df().offset(2).to_plan()
    raw = b_fetch(b_read("people", people_ns()), offset=literal(2, i64()), count=None)(
        registry
    )
    assert fluent.SerializeToString() == raw.SerializeToString()
    # count_expr is left unset -> "all remaining rows".
    assert not fluent.relations[-1].root.input.fetch.HasField("count_expr")


def test_rename_matches_builder():
    fluent = people_df().rename({"age": "years"}).to_plan()
    raw = b_select(
        b_read("people", people_ns()),
        expressions=[
            column("id"),
            column("age", alias="years"),
            column("name"),
        ],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_drop_matches_builder():
    fluent = people_df().drop("age").to_plan()
    raw = b_select(
        b_read("people", people_ns()),
        expressions=[column("id"), column("name")],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_rename_unknown_column_raises():
    with pytest.raises(ValueError, match="unknown columns"):
        people_df().rename({"nope": "x"}).to_plan()


def test_drop_unknown_column_raises():
    with pytest.raises(ValueError, match="unknown columns"):
        people_df().drop("nope").to_plan()


def test_drop_all_columns_raises():
    with pytest.raises(ValueError, match="every column"):
        people_df().drop("id", "age", "name").to_plan()
