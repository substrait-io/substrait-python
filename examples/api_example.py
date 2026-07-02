"""Example usage of the ergonomic `substrait.api` facade.

Compare this with `builder_example.py`, which builds the same kinds of plans
with the lower-level `substrait.builders.*` functions.
"""

import substrait.api as sub
from substrait.utils.display import pretty_print_plan


def filter_select_example():
    """read -> filter -> with_columns -> select, with operator expressions."""
    plan = (
        sub.read_named_table(
            "people", {"id": sub.i64, "age": sub.i64, "name": sub.string}
        )
        .filter((sub.col("age") > 25) & sub.col("name").is_not_null())
        .with_columns(next_year=sub.col("age") + 1)
        .select("id", "name", "next_year")
        .to_plan()
    )
    pretty_print_plan(plan, use_colors=True)


def aggregate_example():
    """group_by().agg() with the named-function namespace `f`.

    Note the explicit nullability: ``region`` is required, ``amount`` nullable.
    ``amount > 0`` also shows literal coercion -- the int ``0`` is typed to match
    the fp64 column so the comparison overload resolves.
    """
    plan = (
        sub.read_named_table(
            "sales", {"region": sub.string.non_null, "amount": sub.fp64}
        )
        .filter(sub.col("amount") > 0)
        .group_by("region")
        .agg(
            sub.f.sum(sub.col("amount")).alias("total"),
            sub.f.count(sub.col("amount")).alias("n"),
        )
        .to_plan()
    )
    pretty_print_plan(plan, use_colors=True)


def join_example():
    """Join two tables and project across the combined schema."""
    customers = sub.read_named_table(
        "customers", {"cust_id": sub.i64, "name": sub.string}
    )
    orders = sub.read_named_table(
        "orders", {"order_id": sub.i64, "cust_ref": sub.i64, "amount": sub.fp64}
    )
    plan = (
        customers.join(
            orders, on=sub.col("cust_id") == sub.col("cust_ref"), how="inner"
        )
        .select("name", "amount")
        .sort("amount", descending=True)
        .limit(10)
        .to_plan()
    )
    pretty_print_plan(plan, use_colors=True)


if __name__ == "__main__":
    print("=== filter / with_columns / select ===")
    filter_select_example()
    print("\n=== group_by / agg ===")
    aggregate_example()
    print("\n=== join / sort / limit ===")
    join_example()
