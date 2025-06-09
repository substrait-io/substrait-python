from substrait.sql.sql_to_substrait import convert
import pyarrow
import substrait.json
import tempfile
import pyarrow.substrait as pa_substrait
import pytest
import sys


data: pyarrow.Table = pyarrow.Table.from_batches(
    [
        pyarrow.record_batch(
            [[2, 1, 3, 4], ["a", "b", "c", "d"]],
            names=["store_id", "name"],
        )
    ]
)


sales_data = pyarrow.Table.from_batches(
    [
        pyarrow.record_batch(
            [
                [1, 2, 3],
                [1, 1, 4],
                [10, 20, 50],
            ],
            names=["sale_id", "fk_store_id", "amount"],
        )
    ]
)


def sort_arrow(table: pyarrow.Table):
    import pyarrow.compute as pc

    sort_keys = [(name, "ascending") for name in table.column_names]
    sort_indices = pc.sort_indices(table, sort_keys)
    sorted_table = pc.take(table, sort_indices)
    return sorted_table


def assert_query_datafusion(query: str, ignore_order=True):
    from datafusion import SessionContext
    from datafusion import substrait as ss

    ctx = SessionContext()
    ctx.register_record_batches("stores", [data.to_batches()])
    ctx.register_record_batches("sales", [sales_data.to_batches()])

    def df_schema_resolver(name: str):
        pa_schema = ctx.sql(f"SELECT * FROM {name} LIMIT 0").schema()
        return pa_substrait.serialize_schema(pa_schema).to_pysubstrait().base_schema

    plan = convert(query, "generic", df_schema_resolver)

    sql_arrow = ctx.sql(query).to_arrow_table()

    substrait_plan = ss.Serde.deserialize_bytes(plan.SerializeToString())
    df_logical_plan = ss.Consumer.from_substrait_plan(ctx, substrait_plan)
    df = ctx.create_dataframe_from_logical_plan(df_logical_plan)
    substrait_arrow = df.to_arrow_table()

    if ignore_order:
        substrait_arrow = sort_arrow(substrait_arrow)
        sql_arrow = sort_arrow(sql_arrow)

    assert substrait_arrow.equals(sql_arrow, check_metadata=True)


def assert_query_duckdb(query: str, ignore_order=True):
    import duckdb

    duckdb.install_extension("substrait", repository="community")
    duckdb.load_extension("substrait")

    with tempfile.TemporaryDirectory() as temp_dir:
        db = f"{temp_dir}/test.db"

        conn = duckdb.connect(db)

        def duckdb_schema_resolver(name: str):
            pa_schema = conn.sql(f"SELECT * FROM {name} LIMIT 0").arrow().schema
            return pa_substrait.serialize_schema(pa_schema).to_pysubstrait().base_schema

        conn.register("stores", data)
        conn.register("sales", sales_data)

        plan = convert(query, "duckdb", duckdb_schema_resolver)

        conn.install_extension("substrait", repository="community")
        conn.load_extension("substrait")

        plan_json = substrait.json.dump_json(plan)
        sql = f"CALL from_substrait_json('{plan_json}')"

        substrait_out = conn.sql(sql)
        sql_out = conn.sql(query)

        substrait_arrow = substrait_out.arrow()
        sql_arrow = sql_out.arrow()

        if ignore_order:
            substrait_arrow = sort_arrow(substrait_arrow)
            sql_arrow = sort_arrow(sql_arrow)

        assert substrait_arrow.equals(sql_arrow, check_metadata=True)


def assert_query(query: str, engine: str, ignore_order=True):
    if engine == "duckdb":
        assert_query_duckdb(query, ignore_order)
    elif engine == "datafusion":
        assert_query_datafusion(query, ignore_order)


engines = [
    pytest.param(
        "duckdb",
        marks=pytest.mark.skipif(
            sys.platform.startswith("win"),
            reason="duckdb substrait extension not found on windows",
        ),
    ),
    "datafusion",
]


@pytest.mark.parametrize("engine", engines)
def test_select_field(engine: str):
    assert_query("""SELECT store_id FROM stores""", engine)


@pytest.mark.parametrize("engine", engines)
def test_inner_join_filtered(engine: str):
    assert_query(
        """SELECT sale_id + 1 as sale_id, name
                    FROM sales
                    INNER JOIN stores ON store_id = fk_store_id
                    WHERE sale_id < 3
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_left_join(engine: str):
    assert_query(
        """SELECT sale_id + 1 as sale_id, name
                    FROM sales
                    LEFT JOIN stores ON store_id = fk_store_id
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_right_join(engine: str):
    assert_query(
        """SELECT sale_id + 1 as sale_id, name
                    FROM sales
                    RIGHT JOIN stores ON store_id = fk_store_id
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_group_by_empty_measures(engine: str):
    assert_query(
        """SELECT fk_store_id, sale_id
                    FROM sales
                    GROUP BY fk_store_id, sale_id
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_group_by_count(engine: str):
    assert_query(
        """SELECT fk_store_id, SUM(amount) as income
                    FROM sales
                    GROUP BY fk_store_id
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_group_by_unnamed_expr(engine: str):
    assert_query(
        """SELECT fk_store_id + 2 AS plustwo, SUM(amount) as income
                    FROM sales
                    GROUP BY fk_store_id + 2
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_sum(engine: str):
    assert_query(
        """SELECT SUM(amount) + SUM(fk_store_id) as income
                    FROM sales
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_group_by_hidden_dimension(engine: str):
    assert_query(
        """SELECT fk_store_id
                    FROM sales
                    GROUP BY fk_store_id, sale_id
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_group_by_having_no_duplicate(engine: str):
    assert_query(
        """SELECT fk_store_id, SUM(amount + 1) as income
                    FROM sales
                    GROUP BY fk_store_id
                    HAVING SUM(amount) < 40
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_group_by_having_duplicate(engine: str):
    assert_query(
        """SELECT fk_store_id, SUM(amount) as income
                    FROM sales
                    GROUP BY fk_store_id
                    HAVING SUM(amount) < 40
                    """,
        engine,
    )


@pytest.mark.parametrize("engine", engines)
def test_order_by(engine: str):
    assert_query(
        """SELECT store_id FROM stores ORDER BY store_id""", engine, ignore_order=False
    )


@pytest.mark.parametrize(
    "engine",
    [
        pytest.param(
            "duckdb",
            marks=[
                pytest.mark.skipif(
                    sys.platform.startswith("win"),
                    reason="duckdb substrait extension not found on windows",
                ),
                pytest.mark.xfail,
            ],
        ),
        "datafusion",
    ],
)
def test_select_limit(engine: str):
    assert_query("""SELECT store_id FROM stores ORDER BY store_id LIMIT 2""", engine)


@pytest.mark.parametrize(
    "engine",
    [
        pytest.param(
            "duckdb",
            marks=[
                pytest.mark.skipif(
                    sys.platform.startswith("win"),
                    reason="duckdb substrait extension not found on windows",
                ),
                pytest.mark.xfail,
            ],
        ),
        "datafusion",
    ],
)
def test_select_limit_offset(engine: str):
    assert_query(
        """SELECT store_id FROM stores ORDER BY store_id LIMIT 2 OFFSET 2""", engine
    )


@pytest.mark.parametrize(
    "engine",
    [
        pytest.param(
            "duckdb",
            marks=[
                pytest.mark.skipif(
                    sys.platform.startswith("win"),
                    reason="duckdb substrait extension not found on windows",
                ),
                pytest.mark.xfail,
            ],
        ),
        "datafusion",
    ],
)
def test_row_number(engine: str):
    assert_query(
        """SELECT sale_id, fk_store_id, row_number() over (partition by fk_store_id order by sale_id) as rn
                    FROM sales
                    """,
        engine,
    )
