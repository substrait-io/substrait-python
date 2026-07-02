"""Tests for the ergonomic Expr wrapper (substrait.expr).

The central contract: an operator expression must produce the *same* proto as
the equivalent hand-written scalar_function builder call.
"""

import pytest

from substrait.builders.extended_expression import column, literal, scalar_function
from substrait.builders.plan import read_named_table, select
from substrait.builders.type import fp64, i64, named_struct, string, struct
from substrait.expr import (
    FUNCTIONS_ARITHMETIC,
    FUNCTIONS_BOOLEAN,
    FUNCTIONS_COMPARISON,
    col,
    infer_literal_type,
    lit,
)
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=True)

schema = named_struct(
    names=["a", "b", "flag"],
    struct=struct(
        types=[i64(nullable=False), i64(nullable=False), i64()], nullable=False
    ),
)


def _plan_from(unbound_expr):
    """Materialize a single expression by projecting it over `schema`."""
    return select(read_named_table("t", schema), expressions=[unbound_expr])(registry)


def _same(lhs_unbound, rhs_unbound):
    return (
        _plan_from(lhs_unbound).SerializeToString()
        == _plan_from(rhs_unbound).SerializeToString()
    )


@pytest.mark.parametrize(
    "op_result, urn, fn",
    [
        (col("a") < col("b"), FUNCTIONS_COMPARISON, "lt"),
        (col("a") <= col("b"), FUNCTIONS_COMPARISON, "lte"),
        (col("a") > col("b"), FUNCTIONS_COMPARISON, "gt"),
        (col("a") >= col("b"), FUNCTIONS_COMPARISON, "gte"),
        (col("a") == col("b"), FUNCTIONS_COMPARISON, "equal"),
        (col("a") != col("b"), FUNCTIONS_COMPARISON, "not_equal"),
        (col("a") + col("b"), FUNCTIONS_ARITHMETIC, "add"),
        (col("a") - col("b"), FUNCTIONS_ARITHMETIC, "subtract"),
        (col("a") * col("b"), FUNCTIONS_ARITHMETIC, "multiply"),
        (col("a") / col("b"), FUNCTIONS_ARITHMETIC, "divide"),
    ],
)
def test_binary_operator_matches_builder(op_result, urn, fn):
    expected = scalar_function(urn, fn, expressions=[column("a"), column("b")])
    assert _same(op_result.unbound, expected)


def test_boolean_operators_match_builder():
    lhs = (col("a") < col("b")) & (col("a") > col("flag"))
    expected = scalar_function(
        FUNCTIONS_BOOLEAN,
        "and",
        expressions=[
            scalar_function(
                FUNCTIONS_COMPARISON, "lt", expressions=[column("a"), column("b")]
            ),
            scalar_function(
                FUNCTIONS_COMPARISON, "gt", expressions=[column("a"), column("flag")]
            ),
        ],
    )
    assert _same(lhs.unbound, expected)


def test_invert_matches_not():
    expr = ~(col("a") == col("b"))
    expected = scalar_function(
        FUNCTIONS_BOOLEAN,
        "not",
        expressions=[
            scalar_function(
                FUNCTIONS_COMPARISON, "equal", expressions=[column("a"), column("b")]
            )
        ],
    )
    assert _same(expr.unbound, expected)


def test_literal_autowrap_on_rhs():
    # `col("a") > 25` should wrap 25 as an i64 literal.
    expr = col("a") > 25
    expected = scalar_function(
        FUNCTIONS_COMPARISON, "gt", expressions=[column("a"), literal(25, i64())]
    )
    assert _same(expr.unbound, expected)


def test_reflected_operator_puts_literal_on_left():
    expr = 100 - col("a")
    expected = scalar_function(
        FUNCTIONS_ARITHMETIC, "subtract", expressions=[literal(100, i64()), column("a")]
    )
    assert _same(expr.unbound, expected)


@pytest.mark.parametrize(
    "value, kind",
    [
        (True, "bool"),
        (5, "i64"),
        (1.5, "fp64"),
        ("x", "string"),
    ],
)
def test_infer_literal_type(value, kind):
    assert infer_literal_type(value).WhichOneof("kind") == kind


def test_bool_inferred_before_int():
    # isinstance(True, int) is True -- make sure bool wins.
    assert infer_literal_type(True).WhichOneof("kind") == "bool"


def test_infer_literal_type_rejects_unknown():
    with pytest.raises(TypeError):
        infer_literal_type(object())


def test_lit_accepts_bare_type_builder():
    # sub.i64 is a callable builder; lit should call it.
    expr = lit(5, i64)
    expected = literal(5, i64())
    assert _same(expr.unbound, expected)


def test_expr_is_not_hashable():
    # __eq__ is overloaded to build an expression, so Expr is unhashable.
    with pytest.raises(TypeError):
        hash(col("a"))


def test_alias_sets_output_name():
    expr = (col("a") + col("b")).alias("total")
    bound = expr.unbound(schema, registry)
    assert bound.referred_expr[0].output_names[0] == "total"


def test_is_null_builds_comparison_function():
    ns = named_struct(names=["x"], struct=struct(types=[string()], nullable=False))
    plan = select(read_named_table("t", ns), expressions=[col("x").is_null().unbound])(
        registry
    )
    # is_null resolves against functions_comparison and yields a boolean output.
    root = plan.relations[-1].root.input
    assert (
        root.project.expressions[0].scalar_function.output_type.WhichOneof("kind")
        == "bool"
    )


def test_arithmetic_overload_resolves_and_types_output():
    ns = named_struct(
        names=["price"], struct=struct(types=[fp64(nullable=False)], nullable=False)
    )
    # fp64 column * fp64 literal -> multiply overload resolves to an fp64 output.
    plan = select(
        read_named_table("t", ns), expressions=[(col("price") * 2.0).unbound]
    )(registry)
    fn = plan.relations[-1].root.input.project.expressions[0].scalar_function
    assert fn.output_type.WhichOneof("kind") == "fp64"
