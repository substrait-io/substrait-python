import adbc_driver_duckdb.dbapi
import pyarrow
from substrait.dataframe import named_table, literal, col, scalar_function
from substrait.dataframe.functions import add

data = pyarrow.record_batch(
    [[1, 2, 3, 4], ["a", "b", "c", "d"]],
    names=["ints", "strs"],
)

with adbc_driver_duckdb.dbapi.connect(":memory:") as conn:
    with conn.cursor() as cur:
        cur.adbc_ingest("AnswerToEverything", data)

        cur.executescript("INSTALL substrait;")
        cur.executescript("LOAD substrait;")

        table = named_table("AnswerToEverything", conn)
        table = table.project(
            literal(1001, type='i64').alias('BigNumber'),
            col("ints").alias('BigNumber2')
        )

        table = table.project(
            scalar_function("functions_arithmetic.yaml", "add",
                add(col("BigNumber"), col("BigNumber2")), 
                col("BigNumber2")
            ).alias('BigNumber3')
        )

        cur.execute(table.plan.SerializeToString())
        print(cur.fetch_arrow_table())