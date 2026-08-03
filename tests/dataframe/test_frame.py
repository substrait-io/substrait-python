"""Tests for the fluent DataFrame facade (substrait.dataframe.frame / substrait.dataframe).

Each fluent chain is checked against the equivalent raw builder pipeline for
byte-identical protobuf output.
"""

import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp

import substrait.dataframe as sub
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
from substrait.builders.plan import hash_join as b_hash_join
from substrait.builders.plan import join as b_join
from substrait.builders.plan import local_files as b_local_files
from substrait.builders.plan import merge_join as b_merge_join
from substrait.builders.plan import read_named_table as b_read
from substrait.builders.plan import select as b_select
from substrait.builders.plan import set as b_set
from substrait.builders.plan import sort as b_sort
from substrait.builders.plan import virtual_table as b_virtual_table
from substrait.builders.plan import write_named_table as b_write
from substrait.builders.type import fp64, i64, named_struct, string, struct
from substrait.dataframe.frame import _JOIN_TYPES
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


# -- Phase 6: subqueries --------------------------------------------------


def _outer():
    return sub.read_named_table("o", {"x": sub.i64, "y": sub.i64})


def _inner():
    return sub.read_named_table("i", {"v": sub.i64})


def _rel(df):
    return df.to_plan().relations[-1].root.input


def _filter_condition(df):
    return _rel(df).filter.condition


def test_scalar_subquery_embeds_inner_rel():
    inner = _inner()
    cond = _filter_condition(_outer().filter(sub.col("x") > sub.scalar_subquery(inner)))
    sq = cond.scalar_function.arguments[1].value.subquery
    assert sq.WhichOneof("subquery_type") == "scalar"
    assert sq.scalar.input == _rel(inner)


@pytest.mark.parametrize(
    "make, op",
    [
        (sub.exists, stalg.Expression.Subquery.SetPredicate.PREDICATE_OP_EXISTS),
        (sub.unique, stalg.Expression.Subquery.SetPredicate.PREDICATE_OP_UNIQUE),
    ],
)
def test_set_predicate_subquery(make, op):
    inner = _inner()
    cond = _filter_condition(_outer().filter(make(inner)))
    assert cond.subquery.WhichOneof("subquery_type") == "set_predicate"
    assert cond.subquery.set_predicate.predicate_op == op
    assert cond.subquery.set_predicate.tuples == _rel(inner)


def test_in_subquery():
    inner = _inner()
    cond = _filter_condition(_outer().filter(sub.col("x").in_subquery(inner)))
    in_pred = cond.subquery.in_predicate
    assert cond.subquery.WhichOneof("subquery_type") == "in_predicate"
    assert len(in_pred.needles) == 1
    assert in_pred.needles[0].selection.direct_reference.struct_field.field == 0
    assert in_pred.haystack == _rel(inner)


@pytest.mark.parametrize(
    "make, reduction, comparison",
    [
        (
            lambda c, q: c > sub.any_(q),
            stalg.Expression.Subquery.SetComparison.REDUCTION_OP_ANY,
            stalg.Expression.Subquery.SetComparison.COMPARISON_OP_GT,
        ),
        (
            lambda c, q: c <= sub.all_(q),
            stalg.Expression.Subquery.SetComparison.REDUCTION_OP_ALL,
            stalg.Expression.Subquery.SetComparison.COMPARISON_OP_LE,
        ),
        (
            lambda c, q: c == sub.any_(q),
            stalg.Expression.Subquery.SetComparison.REDUCTION_OP_ANY,
            stalg.Expression.Subquery.SetComparison.COMPARISON_OP_EQ,
        ),
    ],
)
def test_set_comparison_subquery(make, reduction, comparison):
    inner = _inner()
    cond = _filter_condition(_outer().filter(make(sub.col("x"), inner)))
    sc = cond.subquery.set_comparison
    assert cond.subquery.WhichOneof("subquery_type") == "set_comparison"
    assert sc.reduction_op == reduction
    assert sc.comparison_op == comparison
    assert sc.right == _rel(inner)


def test_subquery_merges_inner_extensions():
    # A function used inside the subquery must be declared in the outer plan.
    inner = _inner().filter(sub.col("v") > 5)
    plan = _outer().filter(sub.exists(inner)).to_plan()
    urns = {u.urn for u in plan.extension_urns}
    assert "extension:io.substrait:functions_comparison" in urns


def test_subquery_over_a_prebuilt_plan_merges_its_extensions():
    """``sub.DataFrame(other.to_plan())`` as the subquery: a plan that arrives already
    numbered, against a table this build is about to replace.

    A Subquery embeds a bare Rel, so the inner plan's declarations do not travel with
    it. Where the two numberings happen to overlap -- as they do here, the outer
    ``gt`` taking the anchor the inner plan gave ``add`` -- the reference loads fine
    and names the wrong function, so this checks by name rather than by anchor.
    """
    inner = _inner().filter(sub.col("v") + 1 > 5)
    prebuilt = sub.DataFrame(inner.to_plan())
    plan = _outer().filter(sub.col("x") > 0).filter(sub.exists(prebuilt)).to_plan()

    declarations = {
        d.extension_function.function_anchor: d.extension_function.name
        for d in plan.extensions
    }
    assert set(declarations.values()) == {"gt:any_any", "add:i64_i64"}
    condition = plan.relations[-1].root.input.filter.condition
    tuples = condition.subquery.set_predicate.tuples
    lifted = tuples.filter.condition.scalar_function
    assert declarations[lifted.function_reference] == "gt:any_any"
    add = lifted.arguments[0].value.scalar_function
    assert declarations[add.function_reference] == "add:i64_i64"


def test_subquery_requires_dataframe():
    with pytest.raises(TypeError, match="expects a DataFrame"):
        sub.scalar_subquery(sub.col("x"))


# -- Phase 7: write op, DDL, update ---------------------------------------


def test_write_insert_matches_builder():
    fluent = people_df().write_named_table("t", op="insert", mode="append").to_plan()
    raw = b_write(
        "t",
        b_read("people", people_ns()),
        create_mode=stalg.WriteRel.CREATE_MODE_APPEND_IF_EXISTS,
        op=stalg.WriteRel.WRITE_OP_INSERT,
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_write_unknown_op_raises():
    with pytest.raises(ValueError, match="unknown write op"):
        people_df().write_named_table("t", op="banana")


def test_create_table_ddl():
    ddl = (
        sub.create_table(["db", "t"], {"id": sub.i64, "v": sub.string}, replace=True)
        .to_plan()
        .relations[-1]
        .root.input.ddl
    )
    assert ddl.object == stalg.DdlRel.DDL_OBJECT_TABLE
    assert ddl.op == stalg.DdlRel.DDL_OP_CREATE_OR_REPLACE
    assert list(ddl.named_object.names) == ["db", "t"]
    assert list(ddl.table_schema.names) == ["id", "v"]


def test_create_view_infers_schema_and_embeds_query():
    query = people_df().select("id")
    ddl = sub.create_view("v", query).to_plan().relations[-1].root.input.ddl
    assert ddl.object == stalg.DdlRel.DDL_OBJECT_VIEW
    assert ddl.HasField("view_definition")
    assert ddl.view_definition == query.to_plan().relations[-1].root.input
    assert list(ddl.table_schema.names) == ["id"]


@pytest.mark.parametrize(
    "make, op, obj",
    [
        (
            lambda: sub.drop_table("t"),
            stalg.DdlRel.DDL_OP_DROP,
            stalg.DdlRel.DDL_OBJECT_TABLE,
        ),
        (
            lambda: sub.drop_table("t", if_exists=True),
            stalg.DdlRel.DDL_OP_DROP_IF_EXIST,
            stalg.DdlRel.DDL_OBJECT_TABLE,
        ),
        (
            lambda: sub.drop_view("v"),
            stalg.DdlRel.DDL_OP_DROP,
            stalg.DdlRel.DDL_OBJECT_VIEW,
        ),
    ],
)
def test_drop_ddl(make, op, obj):
    ddl = make().to_plan().relations[-1].root.input.ddl
    assert ddl.op == op
    assert ddl.object == obj


def test_update_table():
    up = (
        sub.update_table(
            "accounts",
            {"id": sub.i64, "balance": sub.fp64},
            {"balance": sub.col("balance") + 100.0},
            where=sub.col("id") == 1,
        )
        .to_plan()
        .relations[-1]
        .root.input.update
    )
    assert list(up.named_table.names) == ["accounts"]
    assert len(up.transformations) == 1
    assert up.transformations[0].column_target == 1  # "balance"
    assert up.HasField("condition")


def test_update_table_by_index_no_condition():
    up = (
        sub.update_table("t", {"a": sub.i64, "b": sub.i64}, {0: sub.lit(5)})
        .to_plan()
        .relations[-1]
        .root.input.update
    )
    assert up.transformations[0].column_target == 0
    assert not up.HasField("condition")


def test_update_merges_transformation_extensions():
    plan = sub.update_table(
        "accounts",
        {"id": sub.i64, "balance": sub.fp64},
        {"balance": sub.col("balance") + 100.0},
    ).to_plan()
    urns = {u.urn for u in plan.extension_urns}
    assert "extension:io.substrait:functions_arithmetic" in urns


# -- Phase (no-bump): window functions ------------------------------------


def _win_df():
    return sub.read_named_table(
        "sales", {"region": sub.string, "day": sub.i64, "amount": sub.fp64}
    )


def _win_expr(expr):
    return (
        _win_df().select(expr).to_plan().relations[-1].root.input.project.expressions[0]
    )


def test_window_partition_and_order():
    e = _win_expr(sub.f.row_number().over(partition_by="region", order_by="day"))
    assert e.WhichOneof("rex_type") == "window_function"
    assert len(e.window_function.partitions) == 1
    assert len(e.window_function.sorts) == 1
    assert (
        e.window_function.sorts[0].direction
        == stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST
    )


def test_window_multiple_partitions_and_desc_order():
    e = _win_expr(
        sub.f.rank().over(
            partition_by=["region", "day"], order_by="amount", descending=True
        )
    )
    assert len(e.window_function.partitions) == 2
    assert (
        e.window_function.sorts[0].direction
        == stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST
    )


@pytest.mark.parametrize(
    "frame_kwargs, bounds_type, lower, upper",
    [
        (
            {"rows": (None, 0)},
            stalg.Expression.WindowFunction.BOUNDS_TYPE_ROWS,
            "unbounded",
            "current_row",
        ),
        (
            {"rows": (-1, 1)},
            stalg.Expression.WindowFunction.BOUNDS_TYPE_ROWS,
            "preceding",
            "following",
        ),
        (
            {"range": (None, None)},
            stalg.Expression.WindowFunction.BOUNDS_TYPE_RANGE,
            "unbounded",
            "unbounded",
        ),
    ],
)
def test_window_frame(frame_kwargs, bounds_type, lower, upper):
    w = _win_expr(sub.f.rank().over(order_by="day", **frame_kwargs)).window_function
    assert w.bounds_type == bounds_type
    assert w.lower_bound.WhichOneof("kind") == lower
    assert w.upper_bound.WhichOneof("kind") == upper


def test_window_frame_offsets():
    w = _win_expr(sub.f.rank().over(order_by="day", rows=(-2, 3))).window_function
    assert w.lower_bound.preceding.offset == 2
    assert w.upper_bound.following.offset == 3


def test_window_rows_and_range_conflict_raises():
    with pytest.raises(ValueError, match="at most one"):
        sub.f.rank().over(rows=(None, 0), range=(None, 0))


def test_over_on_non_window_raises():
    with pytest.raises(TypeError, match="window functions"):
        _win_df().select(sub.col("region").over(partition_by="day")).to_plan()


# -- Phase (core-ext): Expand / unpivot -----------------------------------


def _wide_df():
    return sub.read_named_table(
        "sales",
        {"region": sub.string, "q1": sub.fp64, "q2": sub.fp64, "q3": sub.fp64},
    )


def test_unpivot_structure():
    plan = (
        _wide_df()
        .unpivot(
            ["q1", "q2", "q3"],
            index="region",
            variable_name="quarter",
            value_name="amount",
        )
        .to_plan()
    )
    root = plan.relations[-1].root
    assert list(root.names) == ["region", "quarter", "amount"]  # index col dropped
    expand = root.input.project.input.expand
    assert [f.WhichOneof("field_type") for f in expand.fields] == [
        "consistent_field",
        "switching_field",
        "switching_field",
    ]
    assert [d.literal.string for d in expand.fields[1].switching_field.duplicates] == [
        "q1",
        "q2",
        "q3",
    ]


def test_unpivot_schema_inference_allows_chaining():
    # Filtering after unpivot exercises infer_rel_schema for the expand relation.
    plan = (
        _wide_df()
        .unpivot(["q1", "q2", "q3"], index="region", value_name="amount")
        .filter(sub.col("amount") > 0.0)
        .to_plan()
    )
    assert plan.relations[-1].root.input.HasField("filter")


def test_unpivot_requires_on():
    with pytest.raises(ValueError, match="at least one column"):
        _wide_df().unpivot([], index="region")


# -- Phase (core-ext): physical joins + exchange --------------------------


def _ab():
    left = sub.read_named_table("a", {"x": sub.i64, "y": sub.string})
    right = sub.read_named_table("b", {"w": sub.i64, "z": sub.fp64})
    return left, right


def test_nested_loop_join_and_chaining():
    left, right = _ab()
    plan = (
        left.nested_loop_join(right, on=sub.col("x") == sub.col("w"), how="inner")
        .select("x", "z")
        .to_plan()
    )
    root = plan.relations[-1].root
    assert root.input.project.input.HasField("nested_loop_join")
    assert list(root.names) == ["x", "z"]


def test_nested_loop_semi_join_left_only_schema():
    left, right = _ab()
    # left_semi keeps only left columns; filtering on x proves the inferred schema.
    plan = (
        left.nested_loop_join(right, on=sub.col("x") == sub.col("w"), how="left_semi")
        .filter(sub.col("x") > 0)
        .to_plan()
    )
    assert plan.relations[-1].root.input.HasField("filter")


def test_nested_loop_join_unknown_type_raises():
    left, right = _ab()
    with pytest.raises(ValueError, match="unknown join type"):
        left.nested_loop_join(right, on=sub.col("x") == sub.col("w"), how="banana")


@pytest.mark.parametrize(
    "make, kind, count",
    [
        (lambda df: df.repartition(4), "round_robin", 4),
        (lambda df: df.broadcast(), "broadcast", 0),
    ],
)
def test_exchange(make, kind, count):
    df = sub.read_named_table("a", {"x": sub.i64})
    ex = make(df).to_plan().relations[-1].root.input.exchange
    assert ex.WhichOneof("exchange_kind") == kind
    assert ex.partition_count == count


def test_exchange_preserves_schema_for_chaining():
    df = sub.read_named_table("a", {"x": sub.i64, "y": sub.i64})
    plan = df.repartition(2).filter(sub.col("y") > 0).to_plan()
    assert plan.relations[-1].root.input.HasField("filter")


# -- Phase (0.96-unblocked): TopN + execution-context variables -----------


def test_top_n_structure_and_chaining():
    df = sub.read_named_table("t", {"id": sub.i64, "score": sub.fp64})
    plan = df.top_n(5, "score", descending=True, with_ties=True).select("id").to_plan()
    tn = plan.relations[-1].root.input.project.input.top_n
    assert len(tn.sorts) == 1
    assert tn.sorts[0].direction == stalg.SortField.SORT_DIRECTION_DESC_NULLS_LAST
    assert tn.count.literal.i64 == 5
    assert tn.mode == stalg.FetchMode.FETCH_MODE_WITH_TIES
    assert not tn.HasField("offset")
    assert list(plan.relations[-1].root.names) == ["id"]


def test_top_n_offset_and_multikey():
    df = sub.read_named_table("t", {"id": sub.i64, "score": sub.fp64})
    tn = df.top_n(3, ["score", "id"], offset=2).to_plan().relations[-1].root.input.top_n
    assert len(tn.sorts) == 2
    assert tn.offset.literal.i64 == 2
    assert tn.mode == stalg.FetchMode.FETCH_MODE_ROWS_ONLY


@pytest.mark.parametrize(
    "make, variable, kind",
    [
        (sub.current_timestamp, "current_timestamp", "precision_timestamp_tz"),
        (sub.current_date, "current_date", "date"),
        (sub.current_timezone, "current_timezone", "string"),
    ],
)
def test_execution_context_variable(make, variable, kind):
    from substrait.type_inference import infer_plan_schema

    df = sub.read_named_table("t", {"id": sub.i64})
    plan = df.with_columns(v=make()).to_plan()
    e = plan.relations[-1].root.input.project.expressions[0]
    assert e.WhichOneof("rex_type") == "execution_context_variable"
    assert (
        e.execution_context_variable.WhichOneof("execution_context_variable_type")
        == variable
    )
    # infer_expression_type derives the variable's type
    assert infer_plan_schema(plan).struct.types[-1].WhichOneof("kind") == kind


# -- Phase 9: hints -------------------------------------------------------


def test_hint_annotates_common_and_is_advisory():
    df = sub.read_named_table("t", {"id": sub.i64, "v": sub.i64})
    plan = (
        df.filter(sub.col("v") > 0)
        .hint(row_count=1000, alias="big", output_names=["a", "b"])
        .select("id")
        .to_plan()
    )
    filt = plan.relations[-1].root.input.project.input.filter
    hint = filt.common.hint
    assert hint.stats.row_count == 1000
    assert hint.alias == "big"
    assert list(hint.output_names) == ["a", "b"]
    # advisory only: the filter condition and the plan's output are unchanged
    assert filt.HasField("condition")
    assert list(plan.relations[-1].root.names) == ["id"]


# -- Lambda / higher-order list functions ---------------------------------


def _list_df():
    return sub.read_named_table("t", {"arr": sub.list_(sub.i64.non_null)})


@pytest.mark.parametrize(
    "make",
    [
        lambda: sub.col("arr").list_transform(lambda x: x + 1),
        lambda: sub.col("arr").list_filter(lambda x: x > 0),
    ],
)
def test_higher_order_builds_lambda_arg(make):
    proj = _list_df().select(make()).to_plan().relations[-1].root.input.project
    fn = proj.expressions[0].scalar_function
    assert fn.output_type.WhichOneof("kind") == "list"  # both return a list
    lambda_arg = fn.arguments[1].value
    assert lambda_arg.WhichOneof("rex_type") == "lambda"
    # the lambda body references the element via a lambda-parameter reference
    body = getattr(lambda_arg, "lambda").body
    element = body.scalar_function.arguments[0].value
    assert element.selection.HasField("lambda_parameter_reference")


def test_list_transform_schema_inference():
    from substrait.type_inference import infer_plan_schema

    plan = (
        _list_df()
        .select(sub.col("arr").list_transform(lambda x: x + 1).alias("inc"))
        .to_plan()
    )
    t = infer_plan_schema(plan).struct.types[0]
    assert t.WhichOneof("kind") == "list"
    assert t.list.type.WhichOneof("kind") == "i64"


# -- Niche close-out: equi-joins, params, UDT, options, extension ---------


def test_hash_join_and_chaining():
    left = sub.read_named_table("l", {"id": sub.i64, "name": sub.string})
    right = sub.read_named_table("r", {"rid": sub.i64, "amt": sub.fp64})
    plan = (
        left.hash_join(right, "id", "rid", how="left").select("name", "amt").to_plan()
    )
    hj = plan.relations[-1].root.input.project.input.hash_join
    assert hj.type == stalg.HashJoinRel.JOIN_TYPE_LEFT
    assert len(hj.keys) == 1
    assert (
        hj.keys[0].comparison.simple
        == stalg.ComparisonJoinKey.SIMPLE_COMPARISON_TYPE_EQ
    )
    assert list(plan.relations[-1].root.names) == ["name", "amt"]


def test_merge_join_default_right_on():
    left = sub.read_named_table("l", {"id": sub.i64})
    right = sub.read_named_table("r", {"id": sub.i64})
    mj = left.merge_join(right, "id").to_plan().relations[-1].root.input.merge_join
    assert mj.type == stalg.MergeJoinRel.JOIN_TYPE_INNER
    assert len(mj.keys) == 1


def _equi_join_tables():
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
    return left, right, left_ns, right_ns


# "amount" is a right column; for right_semi the fluent and raw pipelines route
# through the same builder, so this checks the DataFrame layer forwards
# post_filter/residual correctly regardless of join type.
@pytest.mark.parametrize("how", ["inner", "right_semi"])
@pytest.mark.parametrize(
    "method, b_builder, rel_cls",
    [
        ("hash_join", b_hash_join, stalg.HashJoinRel),
        ("merge_join", b_merge_join, stalg.MergeJoinRel),
    ],
)
def test_equi_join_post_filter_and_residual_match_builder(
    method, b_builder, rel_cls, how
):
    left, right, left_ns, right_ns = _equi_join_tables()
    fluent = getattr(left, method)(
        right,
        "cust_id",
        "cust_ref",
        how=how,
        post_filter=sub.col("amount") > 100.0,
        residual=sub.col("amount") > 50.0,
    ).to_plan()
    raw = b_builder(
        b_read("customers", left_ns),
        b_read("orders", right_ns),
        ["cust_id"],
        ["cust_ref"],
        getattr(rel_cls, "JOIN_TYPE_" + how.upper()),
        post_join_filter=scalar_function(
            COMPARISON, "gt", expressions=[column("amount"), literal(100.0, fp64())]
        ),
        residual_expression=scalar_function(
            COMPARISON, "gt", expressions=[column("amount"), literal(50.0, fp64())]
        ),
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_hash_join_without_predicates_leaves_them_unset():
    left, right, _, _ = _equi_join_tables()
    hj = (
        left.hash_join(right, "cust_id", "cust_ref")
        .to_plan()
        .relations[-1]
        .root.input.hash_join
    )
    assert not hj.HasField("post_join_filter")
    assert not hj.HasField("residual_expression")


def test_dynamic_parameter():
    from substrait.type_inference import infer_plan_schema

    df = sub.read_named_table("t", {"id": sub.i64})
    plan = df.with_columns(p=sub.parameter(1, sub.string)).to_plan()
    dp = plan.relations[-1].root.input.project.expressions[0].dynamic_parameter
    assert dp.parameter_reference == 1
    assert dp.type.WhichOneof("kind") == "string"
    assert infer_plan_schema(plan).struct.types[-1].WhichOneof("kind") == "string"


def test_user_defined_type_in_schema():
    plan = sub.read_named_table(
        "u", {"x": sub.user_defined(7, nullable=False)}
    ).to_plan()
    col_t = plan.relations[-1].root.input.read.base_schema.struct.types[0]
    assert col_t.WhichOneof("kind") == "user_defined"
    assert col_t.user_defined.type_reference == 7


def test_function_options():
    df = sub.read_named_table("t", {"x": sub.i64})
    fn = (
        df.select(sub.f.add(sub.col("x"), 2, overflow="ERROR").alias("s"))
        .to_plan()
        .relations[-1]
        .root.input.project.expressions[0]
        .scalar_function
    )
    assert [o.name for o in fn.options] == ["overflow"]
    assert list(fn.options[0].preference) == ["ERROR"]


def test_function_without_options_has_none():
    df = sub.read_named_table("t", {"x": sub.i64})
    fn = (
        df.select(sub.f.add(sub.col("x"), 2))
        .to_plan()
        .relations[-1]
        .root.input.project.expressions[0]
        .scalar_function
    )
    assert len(fn.options) == 0


def test_extension_single_passthrough_and_chaining():
    from google.protobuf.any_pb2 import Any

    df = sub.read_named_table("t", {"id": sub.i64, "v": sub.i64})
    plan = (
        df.extension(Any(type_url="example.com/R", value=b"x"))
        .filter(sub.col("v") > 0)
        .to_plan()
    )
    ext = plan.relations[-1].root.input.filter.input.extension_single
    assert ext.detail.type_url == "example.com/R"
    assert plan.relations[-1].root.input.HasField("filter")


# -- Correlated subqueries (OuterReference) -------------------------------


def test_correlated_exists():
    outer = sub.read_named_table("o", {"k": sub.i64, "v": sub.i64})
    inner = sub.read_named_table("i", {"k": sub.i64, "w": sub.i64})
    corr = inner.filter(sub.col("k") == sub.outer("k"))  # inner.k == outer.k
    plan = outer.filter(sub.exists(corr)).to_plan()

    root_input = plan.relations[-1].root.input
    inner_cond = (
        root_input.filter.condition.subquery.set_predicate.tuples.filter.condition
    )
    lhs, rhs = (a.value.selection for a in inner_cond.scalar_function.arguments)
    assert lhs.WhichOneof("root_type") == "root_reference"  # inner.k
    assert rhs.WhichOneof("root_type") == "outer_reference"  # outer.k
    # The DataFrame emits id-based correlations: the outer reference names the
    # rel_anchor stamped on the binding relation (the enclosing filter's input).
    anchor = root_input.filter.input.read.common.rel_anchor
    assert rhs.outer_reference.WhichOneof("outer_reference_type") == "rel_reference"
    assert rhs.outer_reference.rel_reference == anchor
    assert rhs.direct_reference.struct_field.field == 0  # "k" in the outer schema


def test_correlated_scalar_subquery_chains():
    outer = sub.read_named_table("o", {"k": sub.i64, "v": sub.i64})
    inner = sub.read_named_table("i", {"k": sub.i64, "w": sub.i64})
    sc = inner.filter(sub.col("k") == sub.outer("k")).select("w")
    plan = outer.filter(sub.col("v") > sub.scalar_subquery(sc)).to_plan()
    assert plan.relations[-1].root.input.HasField("filter")


def test_nested_correlation_id_based():
    outer = sub.read_named_table("o", {"k": sub.i64})
    mid = sub.read_named_table("m", {"k": sub.i64})
    inner = sub.read_named_table("i", {"k": sub.i64})
    # innermost references the outermost query -> steps_out=2 (two levels out)
    inner_corr = inner.filter(sub.col("k") == sub.outer("k", steps_out=2))
    mid_corr = mid.filter(sub.exists(inner_corr))
    plan = outer.filter(sub.exists(mid_corr)).to_plan()

    root_input = plan.relations[-1].root.input
    inner_cond = root_input.filter.condition.subquery.set_predicate.tuples.filter.condition.subquery.set_predicate.tuples.filter.condition  # mid  # inner
    rhs = inner_cond.scalar_function.arguments[1].value.selection
    # steps_out=2 selects the outermost query; it is emitted id-based as a
    # rel_reference to the rel_anchor stamped on that outermost relation.
    outermost_read = root_input.filter.input.read
    assert rhs.outer_reference.WhichOneof("outer_reference_type") == "rel_reference"
    assert rhs.outer_reference.rel_reference == outermost_read.common.rel_anchor


def test_correlated_exists_over_cached_outer_is_id_based():
    # Regression: the correlation's enclosing scope is a cache()d frame, so its
    # binding relation is a ReferenceRel (which carries no RelCommon). The anchor
    # lands on the shared subtree the reference points at, and the whole plan still
    # infers. Previously to_plan() raised.
    from substrait.type_inference import infer_plan_schema

    outer = sub.read_named_table("o", {"k": sub.i64}).cache()
    inner = sub.read_named_table("i", {"k": sub.i64})
    corr = inner.filter(sub.col("k") == sub.outer("k"))
    plan = outer.filter(sub.exists(corr)).to_plan()

    root_input = plan.relations[-1].root.input
    # The binding is a ReferenceRel; the anchor is on the shared subtree.
    assert root_input.filter.input.WhichOneof("rel_type") == "reference"
    anchor = plan.relations[0].rel.read.common.rel_anchor
    rhs = root_input.filter.condition.subquery.set_predicate.tuples.filter.condition.scalar_function.arguments[
        1
    ].value.selection.outer_reference
    assert rhs.WhichOneof("outer_reference_type") == "rel_reference"
    assert rhs.rel_reference == anchor
    infer_plan_schema(plan)


def test_correlated_exists_in_join_post_filter_is_id_based():
    # Regression: a correlated subquery in a join's post_join_filter binds against
    # the join output, i.e. the join itself -- so the join is anchored. Previously
    # to_plan() raised on the multi-input host.
    from substrait.type_inference import infer_plan_schema

    left = sub.read_named_table("l", {"a": sub.i64})
    right = sub.read_named_table("r", {"b": sub.i64})
    inner = sub.read_named_table("i", {"k": sub.i64})
    corr = inner.filter(sub.col("k") == sub.outer("a"))
    plan = left.join(
        right, sub.col("a") == sub.col("b"), how="inner", post_filter=sub.exists(corr)
    ).to_plan()

    join = plan.relations[-1].root.input
    assert join.WhichOneof("rel_type") == "join"
    anchor = join.join.common.rel_anchor
    rhs = join.join.post_join_filter.subquery.set_predicate.tuples.filter.condition.scalar_function.arguments[
        1
    ].value.selection.outer_reference
    assert rhs.WhichOneof("outer_reference_type") == "rel_reference"
    assert rhs.rel_reference == anchor
    infer_plan_schema(plan)


def test_correlated_exists_in_reducing_join_condition_stays_steps_out():
    # A reducing join (semi) emits one side, so its output row can't carry the
    # combined condition scope the correlation sees; the reference is left
    # offset-based (steps_out) -- still spec-valid and read by inference -- rather
    # than mis-anchored. to_plan() must still succeed.
    from substrait.type_inference import infer_plan_schema

    left = sub.read_named_table("l", {"a": sub.i64})
    right = sub.read_named_table("r", {"b": sub.i64})
    inner = sub.read_named_table("i", {"k": sub.i64})
    corr = inner.filter(sub.col("k") == sub.outer("b"))  # references the right side
    plan = left.join(right, sub.exists(corr), how="left_semi").to_plan()

    join = plan.relations[-1].root.input
    assert not join.join.common.HasField("rel_anchor")
    rhs = join.join.expression.subquery.set_predicate.tuples.filter.condition.scalar_function.arguments[
        1
    ].value.selection.outer_reference
    assert rhs.WhichOneof("outer_reference_type") == "steps_out"
    infer_plan_schema(plan)


def test_outer_outside_subquery_raises():
    df = sub.read_named_table("t", {"x": sub.i64})
    with pytest.raises(Exception, match="correlated subquery"):
        df.filter(sub.col("x") == sub.outer("x")).to_plan()


def test_outer_steps_out_below_one_raises():
    # Substrait requires steps_out >= 1; the 0-based convention is rejected.
    outer = sub.read_named_table("o", {"k": sub.i64})
    inner = sub.read_named_table("i", {"k": sub.i64})
    corr = inner.filter(sub.col("k") == sub.outer("k", steps_out=0))
    with pytest.raises(ValueError, match="steps_out must be >= 1"):
        outer.filter(sub.exists(corr)).to_plan()


# -- Lateral joins (handle-based id correlation) --------------------------


def test_lateral_join_correlated_filter():
    from substrait.type_inference import infer_plan_schema

    left = sub.read_named_table("l", {"k": sub.i64, "v": sub.i64})
    inner = sub.read_named_table("r", {"k": sub.i64, "w": sub.i64})
    # The right filters on the current left row via the left handle l.col("k").
    plan = left.lateral_join(
        lambda lat: inner.filter(sub.col("k") == lat.col("k")), how="inner"
    ).to_plan()

    lj = plan.relations[-1].root.input.lateral_join
    assert lj.common.HasField("rel_anchor")
    rhs = lj.right.filter.condition.scalar_function.arguments[1].value.selection
    assert rhs.WhichOneof("root_type") == "outer_reference"
    assert rhs.outer_reference.rel_reference == lj.common.rel_anchor
    # Inner + full right schema.
    assert list(infer_plan_schema(plan).names) == ["k", "v", "k", "w"]


def test_lateral_join_nested_handles_no_depth():
    # An inner lateral join references the outer left via its captured handle;
    # the innermost predicate correlates on both levels with no depth argument.
    from substrait.type_inference import infer_plan_schema

    outer = sub.read_named_table("o", {"j": sub.i64})
    mid = sub.read_named_table("m", {"k": sub.i64})
    inner = sub.read_named_table("i", {"k": sub.i64, "j": sub.i64})
    plan = outer.lateral_join(
        lambda o: mid.lateral_join(
            lambda m: inner.filter(
                (sub.col("k") == m.col("k")) & (sub.col("j") == o.col("j"))
            ),
            how="inner",
        ),
        how="inner",
    ).to_plan()

    outer_lj = plan.relations[-1].root.input.lateral_join
    inner_lj = outer_lj.right.lateral_join
    assert outer_lj.common.rel_anchor != inner_lj.common.rel_anchor
    infer_plan_schema(plan)  # both id references resolve


def test_lateral_join_is_deterministic():
    left = sub.read_named_table("l", {"k": sub.i64})
    inner = sub.read_named_table("r", {"k": sub.i64})

    def build():
        return left.lateral_join(
            lambda lat: inner.filter(sub.col("k") == lat.col("k")), how="inner"
        )

    # Building the same frame twice assigns identical anchors -> equal plans,
    # and both materialization entry points reset anchor numbering alike.
    assert build().to_plan() == build().to_plan()
    assert build().to_plan() == build().to_substrait()


def test_lateral_join_left_semi_drops_right():
    from substrait.type_inference import infer_plan_schema

    left = sub.read_named_table("l", {"k": sub.i64, "v": sub.i64})
    inner = sub.read_named_table("r", {"k": sub.i64})
    plan = left.lateral_join(
        lambda lat: inner.filter(sub.col("k") == lat.col("k")), how="left_semi"
    ).to_plan()
    assert list(infer_plan_schema(plan).names) == ["k", "v"]


def test_lateral_join_unknown_how_raises():
    left = sub.read_named_table("l", {"k": sub.i64})
    inner = sub.read_named_table("r", {"k": sub.i64})
    with pytest.raises(ValueError, match="unknown lateral join type 'right'"):
        left.lateral_join(lambda lat: inner, how="right")


def test_lateral_join_on_condition():
    from substrait.type_inference import infer_plan_schema

    left = sub.read_named_table("l", {"k": sub.i64, "v": sub.i64})
    inner = sub.read_named_table("r", {"w": sub.i64})
    # `on` is a match condition over the combined left+right schema.
    plan = left.lateral_join(
        lambda lat: inner, how="inner", on=sub.col("v") == sub.col("w")
    ).to_plan()

    lj = plan.relations[-1].root.input.lateral_join
    assert lj.HasField("expression")
    assert lj.expression.WhichOneof("rex_type") == "scalar_function"
    assert list(infer_plan_schema(plan).names) == ["k", "v", "w"]


def test_lateral_join_post_filter_binds_output_schema():
    from substrait.type_inference import infer_plan_schema

    left = sub.read_named_table("l", {"k": sub.i64, "v": sub.i64})
    inner = sub.read_named_table("r", {"w": sub.i64})
    # A left-mark join appends a `mark` column to the output; post_filter resolves
    # against that output schema, so it can reference `mark` -- which the combined
    # left+right inputs do not carry.
    plan = left.lateral_join(
        lambda lat: inner, how="left_mark", post_filter=sub.col("mark")
    ).to_plan()

    lj = plan.relations[-1].root.input.lateral_join
    assert lj.HasField("post_join_filter")
    field = lj.post_join_filter.selection.direct_reference.struct_field.field
    assert field == 3  # output is [k, v, w, mark]
    assert list(infer_plan_schema(plan).names) == ["k", "v", "w", "mark"]


def test_correlated_exists_above_lateral_join_stays_steps_out():
    # Regression: a correlated subquery stacked ABOVE a lateral join references the
    # join's OUTPUT row. A lateral join's rel_anchor is reserved (per the Substrait
    # spec) for its right input's reference to the current LEFT row, so it must NOT
    # be reused to anchor this correlation -- doing so aliases the left-row anchor
    # and corrupts any reference beyond the left columns (here the right-side `w`).
    # The reference is left offset-based (steps_out) instead.
    from substrait.type_inference import infer_plan_schema

    outer = sub.read_named_table("outer", {"k": sub.i64, "v": sub.i64})
    inner = sub.read_named_table("inner", {"k": sub.i64, "w": sub.i64})
    subq = sub.read_named_table("subq", {"k": sub.i64})

    lj = outer.lateral_join(
        lambda lat: inner.filter(sub.col("k") == lat.col("k")), how="inner"
    )
    # The EXISTS correlates on the lateral join's OUTPUT column `w` (right-side,
    # index 3 in the output [k, v, k, w]).
    plan = lj.filter(
        sub.exists(subq.filter(sub.col("k") == sub.outer("w", steps_out=1)))
    ).to_plan()

    top = plan.relations[-1].root.input
    lat_anchor = top.filter.input.lateral_join.common.rel_anchor
    oref = top.filter.condition.subquery.set_predicate.tuples.filter.condition.scalar_function.arguments[
        1
    ].value.selection.outer_reference
    # Offset-based, NOT aliasing the lateral join's (left-row) anchor.
    assert oref.WhichOneof("outer_reference_type") == "steps_out"
    assert oref.steps_out == 1
    assert lat_anchor >= 1  # the lateral join still carries its own left-row anchor
    infer_plan_schema(plan)  # resolves without corruption


def test_correlated_subquery_projecting_outer_column_then_chaining():
    # Regression: a correlated subquery whose *output* is the outer column forces
    # the enclosing plan's schema inference to resolve the OuterReference. This
    # must not depend on the build-time outer-schema stack (which is gone by the
    # time a downstream verb re-infers the enclosing schema).
    from substrait.type_inference import infer_plan_schema

    outer = sub.read_named_table("o", {"k": sub.i64, "v": sub.i64})
    inner = sub.read_named_table("i", {"k": sub.i64, "w": sub.i64})
    correlated = inner.select(sub.outer("k").alias("ok"))
    plan = (
        outer.with_columns(x=sub.scalar_subquery(correlated))
        .filter(sub.col("v") > 0)
        .to_plan()
    )
    # Schema inference over the whole plan must succeed.
    infer_plan_schema(plan)


@pytest.mark.parametrize(
    "make",
    [
        lambda inner: sub.exists(inner),
        lambda inner: sub.unique(inner),
        lambda inner: sub.col("x").in_subquery(inner),
        lambda inner: sub.col("x") > sub.any_(inner),
        lambda inner: sub.col("x") <= sub.all_(inner),
    ],
)
def test_set_predicate_subquery_projected_infers_bool(make):
    # Regression: projecting a set-predicate subquery (EXISTS / IN / ANY / ALL)
    # must infer a boolean output type -- previously the branch built a Boolean
    # but did not return it, yielding None and a TypeError in the Struct build.
    from substrait.type_inference import infer_plan_schema

    outer = _outer()
    plan = outer.with_columns(flag=make(_inner())).to_plan()
    last = infer_plan_schema(plan).struct.types[-1]
    assert last.WhichOneof("kind") == "bool"


def test_semi_join_output_names_match_types():
    # Regression: a semi join emits only the left side, so RelRoot names must not
    # carry the right side's names (which would leave more names than types).
    from substrait.type_inference import infer_plan_schema

    left, right = _ab()
    plan = left.hash_join(right, "x", "w", how="left_semi").to_plan()
    ns = infer_plan_schema(plan)
    assert list(ns.names) == ["x", "y"]
    assert len(ns.names) == len(ns.struct.types)


def test_mark_join_output_names_match_types():
    from substrait.type_inference import infer_plan_schema

    left, right = _ab()
    plan = left.hash_join(right, "x", "w", how="left_mark").to_plan()
    ns = infer_plan_schema(plan)
    # left + right + a trailing boolean mark column.
    assert list(ns.names) == ["x", "y", "w", "z", "mark"]
    assert len(ns.names) == len(ns.struct.types)
    assert ns.struct.types[-1].WhichOneof("kind") == "bool"


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


# -- Execution behavior (Plan.execution_behavior) -------------------------


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("per_plan", stp.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_PLAN),
        ("per_record", stp.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_RECORD),
    ],
)
def test_with_execution_behavior(mode, expected):
    plan = (
        sub.read_named_table("t", {"id": sub.i64})
        .with_execution_behavior(mode)
        .to_plan()
    )
    assert plan.execution_behavior.variable_eval_mode == expected


def test_execution_behavior_preserved_through_later_ops():
    # Set it first, then keep building -- the setting must survive downstream ops.
    plan = (
        sub.read_named_table("t", {"id": sub.i64, "age": sub.i64})
        .with_execution_behavior("per_record")
        .filter(sub.col("age") > 25)
        .select("id")
        .to_plan()
    )
    assert (
        plan.execution_behavior.variable_eval_mode
        == stp.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_RECORD
    )


def test_execution_behavior_set_mid_chain():
    # Applying it in the middle of a chain is equivalent -- it is order independent.
    plan = (
        sub.read_named_table("t", {"id": sub.i64, "age": sub.i64})
        .filter(sub.col("age") > 25)
        .with_execution_behavior("per_plan")
        .select("id")
        .to_plan()
    )
    assert (
        plan.execution_behavior.variable_eval_mode
        == stp.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_PLAN
    )


def test_execution_behavior_unset_by_default():
    plan = sub.read_named_table("t", {"id": sub.i64}).to_plan()
    assert not plan.HasField("execution_behavior")


def test_with_execution_behavior_invalid_mode():
    with pytest.raises(ValueError, match="unknown execution behavior mode 'nonsense'"):
        sub.read_named_table("t", {"id": sub.i64}).with_execution_behavior("nonsense")


def test_execution_behavior_with_context_variable_end_to_end():
    # The common pairing: a per-record execution behavior alongside a
    # current_timestamp execution context variable.
    plan = (
        sub.read_named_table("t", {"id": sub.i64})
        .with_columns(now=sub.current_timestamp())
        .with_execution_behavior("per_record")
        .to_plan()
    )
    assert (
        plan.execution_behavior.variable_eval_mode
        == stp.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_RECORD
    )
    projected = plan.relations[-1].root.input.project.expressions[0]
    assert projected.WhichOneof("rex_type") == "execution_context_variable"
