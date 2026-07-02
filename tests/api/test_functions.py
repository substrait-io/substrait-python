"""Tests for the generated function namespace (substrait.functions)."""

import keyword

import pytest

import substrait.api as sub
from substrait.builders.plan import consistent_partition_window
from substrait.builders.plan import read_named_table as b_read
from substrait.builders.type import fp64, i64, named_struct, string, struct
from substrait.extension_registry import ExtensionRegistry
from substrait.functions import _safe_name

registry = ExtensionRegistry(load_default_extensions=True)


def _all_registry_names():
    return {name for _, name, _ in registry.iter_functions()}


def test_covers_every_default_function():
    # Every function the default extensions define must be reachable on f.
    missing = [n for n in _all_registry_names() if _safe_name(n) not in dir(sub.f)]
    assert missing == [], f"functions not exposed on f: {missing}"


def test_coverage_is_substantial():
    # Guard against a regression that silently drops most functions.
    assert len(_all_registry_names()) > 150
    assert len(dir(sub.f)) >= len(_all_registry_names())


def test_every_helper_is_callable():
    for name in _all_registry_names():
        assert callable(getattr(sub.f, _safe_name(name)))


def test_keyword_names_are_suffixed_and_raw_reachable():
    for kw in ("and", "or", "not"):
        assert keyword.iskeyword(kw)
        suffixed = getattr(sub.f, kw + "_")
        assert callable(suffixed)
        # raw keyword name still reachable via getattr
        assert getattr(sub.f, kw) is suffixed


def test_unknown_function_raises_attributeerror():
    with pytest.raises(AttributeError, match="no Substrait function"):
        sub.f.definitely_not_a_function


def test_dunder_access_does_not_trigger_build():
    with pytest.raises(AttributeError):
        sub.f.__wrapped__


# ---------------------------------------------------------------------------
# Building / resolution
# ---------------------------------------------------------------------------


def _urns(plan):
    return {u.urn.rsplit(":", 1)[-1] for u in plan.extension_urns}


def test_scalar_function_builds():
    df = sub.read_named_table("t", {"name": sub.string})
    plan = df.with_columns(u=sub.f.upper(sub.col("name"))).to_plan()
    assert "functions_string" in _urns(plan)


def test_aggregate_function_builds():
    df = sub.read_named_table("s", {"region": sub.string, "amount": sub.fp64})
    plan = df.group_by("region").agg(sub.f.avg(sub.col("amount")).alias("a")).to_plan()
    assert "functions_arithmetic" in _urns(plan)


def test_window_function_builds():
    ns = named_struct(
        names=["x"], struct=struct(types=[i64(nullable=False)], nullable=False)
    )
    plan = consistent_partition_window(
        b_read("t", ns), window_functions=[sub.f.row_number().unbound]
    )(registry)
    assert plan.relations


def test_collision_int_add_uses_base_arithmetic():
    df = sub.read_named_table("t", {"a": sub.i64.non_null, "b": sub.i64.non_null})
    plan = df.with_columns(s=sub.f.add(sub.col("a"), sub.col("b"))).to_plan()
    assert _urns(plan) == {"functions_arithmetic"}


def test_collision_count_uses_generic_not_decimal():
    df = sub.read_named_table("t", {"a": sub.i64.non_null})
    plan = df.group_by().agg(sub.f.count(sub.col("a")).alias("n")).to_plan()
    assert _urns(plan) == {"functions_aggregate_generic"}


def test_multi_urn_no_matching_overload_raises():
    df = sub.read_named_table("t", {"flag": sub.boolean})
    # add is a multi-URN function but has no boolean overload anywhere.
    with pytest.raises(Exception, match="No matching overload"):
        df.with_columns(s=sub.f.add(sub.col("flag"), sub.col("flag"))).to_plan()


def test_generated_sum_matches_raw_builder():
    from substrait.builders.extended_expression import aggregate_function, column
    from substrait.builders.plan import aggregate as b_aggregate

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
                "extension:io.substrait:functions_arithmetic",
                "sum",
                expressions=[column("amount")],
                alias="total",
            )
        ],
    )(registry)
    assert fluent.SerializeToString() == raw.SerializeToString()


def test_helper_has_docstring_naming_extensions():
    assert "functions_string" in sub.f.upper.__doc__


# ---------------------------------------------------------------------------
# Custom / user-defined extensions
# ---------------------------------------------------------------------------

_CUSTOM_YAML = """%YAML 1.2
---
urn: extension:com.acme:my_functions
scalar_functions:
  - name: "my_double"
    description: Double an integer
    impls:
      - args:
          - name: x
            value: i64
        return: i64
"""


def _custom_registry():
    reg = ExtensionRegistry(load_default_extensions=True)
    reg.register_extension_dict(__import__("yaml").safe_load(_CUSTOM_YAML))
    return reg


def test_functions_for_exposes_custom_extension():
    myf = sub.functions_for(_custom_registry())
    assert "my_double" in dir(myf)
    assert callable(myf.my_double)


def test_global_f_does_not_see_custom_extension():
    # The global f is bound to the default registry only.
    assert "my_double" not in dir(sub.f)


def test_functions_for_builds_custom_function_plan():
    reg = _custom_registry()
    myf = sub.functions_for(reg)
    df = sub.read_named_table("t", {"x": sub.i64.non_null}, registry=reg)
    plan = df.with_columns(d=myf.my_double(sub.col("x"))).to_plan()
    assert any(u.urn == "extension:com.acme:my_functions" for u in plan.extension_urns)


def test_dataframe_f_is_bound_to_its_registry():
    reg = _custom_registry()
    df = sub.read_named_table("t", {"x": sub.i64.non_null}, registry=reg)
    # df.f is the ergonomic accessor: reachable and composable with operators.
    plan = df.filter(df.f.my_double(sub.col("x")) > 10).to_plan()
    assert plan.relations
    assert any(u.urn == "extension:com.acme:my_functions" for u in plan.extension_urns)


def test_dataframe_f_is_cached():
    df = sub.read_named_table("t", {"x": sub.i64.non_null})
    assert df.f is df.f
