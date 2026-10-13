"""Tests for detached expression subtrees (spec v0.105.0, bounded expression nesting)."""

import pytest
import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt
from google.protobuf import any_pb2, text_format
from google.protobuf.message import DecodeError, Message

import substrait.dataframe as sub
from substrait.builders.extended_expression import column
from substrait.builders.plan import select
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_extended_expression_schema, infer_plan_schema
from substrait.utils.detached_expressions import (
    detach_expressions,
    resolve_detached_expressions,
)
from substrait.utils.display import PlanPrinter

registry = ExtensionRegistry(load_default_extensions=True)

# The spec's examples, site/examples/proto-textformat/{plan_rel,extended_expression}.
SPEC_PLAN_REL = """
root {
  input {
    project {
      common { direct {} }
      input {
        read {
          common { direct {} }
          base_schema {
            names: "value"
            struct {
              types { i64 { nullability: NULLABILITY_REQUIRED } }
              nullability: NULLABILITY_REQUIRED
            }
          }
          named_table { names: "example" }
        }
      }
      expressions { detached_expression_ordinal: 0 }
    }
  }
  names: "value"
  names: "answer"
}
detached_expressions { literal { i64: 42 } }
"""

SPEC_EXTENDED_EXPRESSION = """
version { minor_number: 104 }
base_schema { struct { nullability: NULLABILITY_REQUIRED } }
referred_expr {
  expression { detached_expression_ordinal: 0 }
  output_names: "result"
  output_names: "answer"
}
detached_expressions {
  nested { struct { fields { detached_expression_ordinal: 1 } } }
}
detached_expressions { literal { i64: 42 } }
"""


def _plan_rel(textproto: str) -> stp.PlanRel:
    return text_format.Parse(textproto, stp.PlanRel())


def _plan(textproto: str) -> stp.Plan:
    plan = stp.Plan()
    plan.relations.add().CopyFrom(_plan_rel(textproto))
    return plan


def _deep_plan(levels: int) -> stp.Plan:
    """A plan projecting a struct literal nested ``levels`` structs deep.

    Built by mutating in place: under upb, a message constructor copies its
    arguments through the parser and so is itself bound by the depth limit."""
    plan = stp.Plan()
    root = plan.relations.add().root
    root.names.append("x")
    project = root.input.project
    project.input.read.named_table.names.append("t")
    project.input.read.base_schema.struct.nullability = stt.Type.NULLABILITY_REQUIRED
    expr = project.expressions.add()
    for _ in range(levels):
        expr = expr.nested.struct.fields.add()
    expr.literal.i64 = 42
    return plan


def _submessages(msg):
    for field, value in msg.ListFields():
        if isinstance(value, Message):
            yield value
        elif field.message_type is not None:
            yield from value


def _height(msg) -> int:
    """How many message levels the deepest submessage sits below ``msg``."""
    deepest, stack = 0, [(msg, 0)]
    while stack:
        node, depth = stack.pop()
        deepest = max(deepest, depth)
        stack.extend((child, depth + 1) for child in _submessages(node))
    return deepest


def _ordinals(msg):
    """Every detached expression ordinal in ``msg``, in no particular order."""
    found, stack = [], [msg]
    while stack:
        node = stack.pop()
        if isinstance(node, stalg.Expression) and (
            node.WhichOneof("rex_type") == "detached_expression_ordinal"
        ):
            found.append(node.detached_expression_ordinal)
        stack.extend(_submessages(node))
    return found


# ---------------------------------------------------------------------------
# Resolving
# ---------------------------------------------------------------------------


def test_resolve_spec_plan_rel_example():
    resolved = resolve_detached_expressions(_plan_rel(SPEC_PLAN_REL))
    assert resolved.root.input.project.expressions[0].literal.i64 == 42
    assert len(resolved.detached_expressions) == 0


def test_resolve_spec_extended_expression_example():
    ee = text_format.Parse(SPEC_EXTENDED_EXPRESSION, stee.ExtendedExpression())
    resolved = resolve_detached_expressions(ee)
    expression = resolved.referred_expr[0].expression
    assert expression.nested.struct.fields[0].literal.i64 == 42
    assert len(resolved.detached_expressions) == 0


def test_resolve_does_not_modify_input():
    plan = _plan(SPEC_PLAN_REL)
    before = plan.SerializeToString()
    resolve_detached_expressions(plan)
    assert plan.SerializeToString() == before


def test_resolve_without_detached_expressions_returns_input():
    plan = _deep_plan(3)
    assert resolve_detached_expressions(plan) is plan


def test_resolve_ignores_unreachable_entries():
    # Unreachable entries need not be valid: this one is itself an ordinal.
    plan_rel = _plan_rel(
        SPEC_PLAN_REL + "detached_expressions { detached_expression_ordinal: 0 }"
    )
    resolved = resolve_detached_expressions(plan_rel)
    assert resolved.root.input.project.expressions[0].literal.i64 == 42


@pytest.mark.parametrize(
    "table, message",
    [
        ("", "out of range"),
        (
            "detached_expressions { detached_expression_ordinal: 0 }",
            "itself an ordinal",
        ),
        (
            # Entry 0 points back at itself through a nested struct.
            (
                "detached_expressions {"
                " nested { struct { fields { detached_expression_ordinal: 0 } } } }"
            ),
            "more than once, or by a cycle",
        ),
    ],
)
def test_resolve_rejects_invalid_references(table, message):
    plan_rel = _plan_rel(
        SPEC_PLAN_REL.replace("detached_expressions { literal { i64: 42 } }", table)
    )
    with pytest.raises(ValueError, match=message):
        resolve_detached_expressions(plan_rel)


def test_resolve_rejects_reused_entry():
    plan_rel = _plan_rel(SPEC_PLAN_REL)
    project = plan_rel.root.input.project
    project.expressions.add().detached_expression_ordinal = 0
    with pytest.raises(ValueError, match="more than once"):
        resolve_detached_expressions(plan_rel)


def test_resolve_does_not_cross_plan_rels():
    # Ordinals are local to their PlanRel: the second one has no table of its own.
    plan = _plan(SPEC_PLAN_REL)
    second = plan.relations.add()
    second.CopyFrom(plan.relations[0])
    second.ClearField("detached_expressions")
    with pytest.raises(ValueError, match="out of range"):
        resolve_detached_expressions(plan)


def test_resolve_keeps_table_when_an_any_payload_may_reference_it():
    plan_rel = _plan_rel(SPEC_PLAN_REL)
    plan_rel.root.input.project.common.advanced_extension.enhancement.CopyFrom(
        any_pb2.Any(type_url="example.com/Detail", value=b"\x08\x00")
    )
    resolved = resolve_detached_expressions(plan_rel)
    assert resolved.root.input.project.expressions[0].literal.i64 == 42
    assert list(resolved.detached_expressions) == list(plan_rel.detached_expressions)


def test_resolve_rejects_unsupported_message():
    with pytest.raises(TypeError, match="Plan, PlanRel or ExtendedExpression"):
        resolve_detached_expressions(stalg.Expression())


# ---------------------------------------------------------------------------
# Detaching
# ---------------------------------------------------------------------------


def test_detach_within_budget_is_byte_identical():
    plan = _deep_plan(5)
    assert detach_expressions(plan).SerializeToString() == plan.SerializeToString()


def test_deep_plan_round_trips_through_bytes():
    plan = _deep_plan(1000)
    with pytest.raises(DecodeError):
        stp.Plan.FromString(plan.SerializeToString())

    detached = detach_expressions(plan)
    assert _height(detached) <= 100
    parsed = stp.Plan.FromString(detached.SerializeToString())
    assert resolve_detached_expressions(parsed) == plan


# The relation tree around the expression is 8 levels deep; detaching only
# shortens expressions, so smaller budgets are best effort.
@pytest.mark.parametrize("max_depth", [0, 8, 20, 64])
def test_detach_respects_custom_budget(max_depth):
    plan = _deep_plan(60)
    detached = detach_expressions(plan, max_depth=max_depth)
    if max_depth:
        assert _height(detached) <= max_depth
    assert resolve_detached_expressions(detached) == plan


def test_detach_orders_entries_in_pre_order():
    detached = detach_expressions(_deep_plan(200))
    table = detached.relations[0].detached_expressions
    assert len(table) > 1
    # Each entry holds exactly the next cut down the chain.
    for ordinal, entry in enumerate(table[:-1]):
        assert _ordinals(entry) == [ordinal + 1]
    assert _ordinals(table[-1]) == []


def test_detach_keeps_existing_entries():
    plan = _plan(SPEC_PLAN_REL)
    detached = detach_expressions(plan, max_depth=0)
    table = detached.relations[0].detached_expressions
    assert table[0].literal.i64 == 42
    assert resolve_detached_expressions(detached) == resolve_detached_expressions(plan)


def test_detach_extended_expression():
    ee = text_format.Parse(SPEC_EXTENDED_EXPRESSION, stee.ExtendedExpression())
    resolved = resolve_detached_expressions(ee)
    detached = detach_expressions(resolved, max_depth=0)
    expression = detached.referred_expr[0].expression
    assert expression.WhichOneof("rex_type") == "detached_expression_ordinal"
    assert resolve_detached_expressions(detached) == resolved


def _dataframe_plans():
    t = sub.read_named_table(
        "t", {"id": sub.i64, "region": sub.string, "amount": sub.fp64}
    )
    return [
        t.filter((sub.col("id") > 1) & (sub.col("amount") < 10.0)).to_plan(),
        t.select((sub.col("amount") * 2 + 1).alias("x")).to_plan(),
        t.group_by("region").agg(sub.f.avg(sub.col("amount")).alias("a")).to_plan(),
    ]


@pytest.mark.parametrize("plan", _dataframe_plans())
def test_fully_detached_dataframe_plans_round_trip(plan):
    detached = detach_expressions(plan, max_depth=0)
    assert detached.relations[-1].detached_expressions
    parsed = stp.Plan.FromString(detached.SerializeToString())
    assert resolve_detached_expressions(parsed) == plan


def test_detach_rejects_unsupported_message():
    with pytest.raises(TypeError, match="Plan, PlanRel or ExtendedExpression"):
        detach_expressions(stalg.Rel())


# ---------------------------------------------------------------------------
# Consumers accept detached input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plan", _dataframe_plans())
def test_infer_plan_schema_resolves_detached_expressions(plan):
    detached = detach_expressions(plan, max_depth=0)
    assert infer_plan_schema(detached, registry=registry) == infer_plan_schema(
        plan, registry=registry
    )


def test_infer_extended_expression_schema_resolves_detached_expressions():
    ee = text_format.Parse(SPEC_EXTENDED_EXPRESSION, stee.ExtendedExpression())
    schema = infer_extended_expression_schema(ee)
    assert schema.types[0].struct.types[0].WhichOneof("kind") == "i64"


def test_builders_inline_a_detached_input_plan():
    plan = _dataframe_plans()[1]
    detached = detach_expressions(plan, max_depth=0)
    built = select(detached, expressions=[column("x")])(registry)
    assert not any(pr.detached_expressions for pr in built.relations)
    assert _ordinals(built) == []
    assert built == select(plan, expressions=[column("x")])(registry)


def test_display_resolves_detached_expressions():
    plan = _dataframe_plans()[1]
    detached = detach_expressions(plan, max_depth=0)
    printer = PlanPrinter()
    assert printer.stringify_plan(detached) == printer.stringify_plan(plan)
