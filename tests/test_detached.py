"""Tests for detached expression subtrees (spec v0.105.0, bounded expression nesting)."""

import pytest
import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt
from google.protobuf import any_pb2, text_format
from google.protobuf.message import DecodeError, Message

import substrait.dataframe as sub
from substrait.builders.extended_expression import (
    column,
    in_predicate,
    scalar_subquery,
    set_comparison,
    set_predicate,
)
from substrait.builders.plan import project, read_named_table, select
from substrait.builders.type import fp64, named_struct, struct
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import (
    infer_expression_type,
    infer_extended_expression_schema,
    infer_plan_schema,
)
from substrait.utils.detached import (
    detach,
    resolve_detached,
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
    """Yield ``(child, levels)``: a map value sits two levels down, under its entry."""
    for field, value in msg.ListFields():
        if isinstance(value, Message):
            yield value, 1
        elif hasattr(value, "values"):
            yield from ((v, 2) for v in value.values() if isinstance(v, Message))
        elif field.message_type is not None:
            yield from ((v, 1) for v in value)


def _height(msg) -> int:
    """How many message levels the deepest submessage sits below ``msg``."""
    deepest, stack = 0, [(msg, 0)]
    while stack:
        node, depth = stack.pop()
        deepest = max(deepest, depth)
        stack.extend((child, depth + levels) for child, levels in _submessages(node))
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
        stack.extend(child for child, _ in _submessages(node))
    return found


# ---------------------------------------------------------------------------
# Resolving
# ---------------------------------------------------------------------------


def test_resolve_spec_plan_rel_example():
    resolved = resolve_detached(_plan_rel(SPEC_PLAN_REL))
    assert resolved.root.input.project.expressions[0].literal.i64 == 42
    assert len(resolved.detached_expressions) == 0


def test_resolve_spec_extended_expression_example():
    ee = text_format.Parse(SPEC_EXTENDED_EXPRESSION, stee.ExtendedExpression())
    resolved = resolve_detached(ee)
    expression = resolved.referred_expr[0].expression
    assert expression.nested.struct.fields[0].literal.i64 == 42
    assert len(resolved.detached_expressions) == 0


def test_resolve_does_not_modify_input():
    plan = _plan(SPEC_PLAN_REL)
    before = plan.SerializeToString()
    resolve_detached(plan)
    assert plan.SerializeToString() == before


def test_resolve_without_detached_expressions_returns_input():
    plan = _deep_plan(3)
    assert resolve_detached(plan) is plan


def test_resolve_ignores_unreachable_entries():
    # Unreachable entries need not be valid: this one is itself an ordinal.
    plan_rel = _plan_rel(
        SPEC_PLAN_REL + "detached_expressions { detached_expression_ordinal: 0 }"
    )
    resolved = resolve_detached(plan_rel)
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
        resolve_detached(plan_rel)


def test_resolve_rejects_reused_entry():
    plan_rel = _plan_rel(SPEC_PLAN_REL)
    project = plan_rel.root.input.project
    project.expressions.add().detached_expression_ordinal = 0
    with pytest.raises(ValueError, match="more than once"):
        resolve_detached(plan_rel)


def test_resolve_does_not_cross_plan_rels():
    # Ordinals are local to their PlanRel: the second one has no table of its own.
    plan = _plan(SPEC_PLAN_REL)
    second = plan.relations.add()
    second.CopyFrom(plan.relations[0])
    second.ClearField("detached_expressions")
    with pytest.raises(ValueError, match="out of range"):
        resolve_detached(plan)


def _with_any_payload(plan_rel: stp.PlanRel) -> stp.PlanRel:
    plan_rel.root.input.project.common.advanced_extension.enhancement.CopyFrom(
        any_pb2.Any(type_url="example.com/Detail", value=b"\x08\x00")
    )
    return plan_rel


def test_resolve_keeps_entries_an_any_payload_may_reference():
    # Entry 1 is unreachable from the relation tree, so the opaque payload may
    # reference it: it must keep its ordinal. Entry 2, resolved here, is dropped.
    plan_rel = _with_any_payload(
        _plan_rel(
            SPEC_PLAN_REL.replace(
                "detached_expression_ordinal: 0", "detached_expression_ordinal: 2"
            )
            + "detached_expressions { literal { i64: 7 } }"
            "detached_expressions { literal { i64: 42 } }"
        )
    )
    resolved = resolve_detached(plan_rel)
    assert resolved.root.input.project.expressions[0].literal.i64 == 42
    assert [e.literal.i64 for e in resolved.detached_expressions] == [42, 7]


def test_resolve_with_any_payload_drops_entries_it_resolved():
    resolved = resolve_detached(_with_any_payload(_plan_rel(SPEC_PLAN_REL)))
    assert len(resolved.detached_expressions) == 0


def test_round_trips_with_any_payload_do_not_grow_the_table():
    plan = _deep_plan(200)
    _with_any_payload(plan.relations[0])
    sizes = []
    for _ in range(3):
        detached = detach(plan)
        sizes.append(len(detached.relations[0].detached_expressions))
        plan = resolve_detached(stp.Plan.FromString(detached.SerializeToString()))
        assert len(plan.relations[0].detached_expressions) == 0
    assert sizes == [sizes[0]] * 3


def test_resolve_screens_out_ordinal_tag_bytes_elsewhere():
    # 144 encodes as the bytes 0x90 0x01, the same as the ordinal field's tag.
    plan = _deep_plan(1)
    plan.relations[0].root.input.project.expressions[0].nested.struct.fields[
        0
    ].literal.i64 = 144
    assert resolve_detached(plan) is plan


def test_resolve_rejects_unsupported_message():
    with pytest.raises(TypeError, match="Plan, PlanRel or ExtendedExpression"):
        resolve_detached(stalg.Expression())


# ---------------------------------------------------------------------------
# Detaching
# ---------------------------------------------------------------------------


def test_detach_within_budget_returns_input():
    plan = _deep_plan(5)
    assert detach(plan) is plan


def test_deep_plan_round_trips_through_bytes():
    plan = _deep_plan(1000)
    with pytest.raises(DecodeError):
        stp.Plan.FromString(plan.SerializeToString())

    detached = detach(plan)
    assert _height(detached) <= 100
    parsed = stp.Plan.FromString(detached.SerializeToString())
    assert resolve_detached(parsed) == plan


# The relation tree around the expression is 8 levels deep; detaching only
# shortens expressions, so smaller budgets are best effort.
@pytest.mark.parametrize("max_depth", [0, 8, 20, 64])
def test_detach_respects_custom_budget(max_depth):
    plan = _deep_plan(60)
    detached = detach(plan, max_depth=max_depth)
    if max_depth:
        assert _height(detached) <= max_depth
    assert resolve_detached(detached) == plan


def test_detach_orders_entries_in_pre_order():
    detached = detach(_deep_plan(200))
    table = detached.relations[0].detached_expressions
    assert len(table) > 1
    # Each entry holds exactly the next cut down the chain.
    for ordinal, entry in enumerate(table[:-1]):
        assert _ordinals(entry) == [ordinal + 1]
    assert _ordinals(table[-1]) == []


def test_detach_keeps_existing_entries():
    plan = _plan(SPEC_PLAN_REL)
    detached = detach(plan, max_depth=0)
    table = detached.relations[0].detached_expressions
    assert table[0].literal.i64 == 42
    assert resolve_detached(detached) == resolve_detached(plan)


def test_detach_extended_expression():
    ee = text_format.Parse(SPEC_EXTENDED_EXPRESSION, stee.ExtendedExpression())
    resolved = resolve_detached(ee)
    detached = detach(resolved, max_depth=0)
    expression = detached.referred_expr[0].expression
    assert expression.WhichOneof("rex_type") == "detached_expression_ordinal"
    assert resolve_detached(detached) == resolved


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
    detached = detach(plan, max_depth=0)
    assert detached.relations[-1].detached_expressions
    parsed = stp.Plan.FromString(detached.SerializeToString())
    assert resolve_detached(parsed) == plan


def test_detach_rejects_unsupported_message():
    with pytest.raises(TypeError, match="Plan, PlanRel or ExtendedExpression"):
        detach(stalg.Rel())


# ---------------------------------------------------------------------------
# Consumers accept detached input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plan", _dataframe_plans())
def test_infer_plan_schema_resolves_detached_expressions(plan):
    detached = detach(plan, max_depth=0)
    assert infer_plan_schema(detached, registry=registry) == infer_plan_schema(
        plan, registry=registry
    )


def test_infer_extended_expression_schema_resolves_detached_expressions():
    ee = text_format.Parse(SPEC_EXTENDED_EXPRESSION, stee.ExtendedExpression())
    schema = infer_extended_expression_schema(ee)
    assert schema.types[0].struct.types[0].WhichOneof("kind") == "i64"


def test_builders_inline_a_detached_input_plan():
    plan = _dataframe_plans()[1]
    detached = detach(plan, max_depth=0)
    built = select(detached, expressions=[column("x")])(registry)
    assert not any(pr.detached_expressions for pr in built.relations)
    assert _ordinals(built) == []
    assert built == select(plan, expressions=[column("x")])(registry)


def test_display_resolves_detached_expressions():
    plan = _dataframe_plans()[1]
    detached = detach(plan, max_depth=0)
    printer = PlanPrinter()
    assert printer.stringify_plan(detached) == printer.stringify_plan(plan)


_SUBQUERY_BUILDERS = {
    "scalar_subquery": scalar_subquery,
    "set_predicate": lambda query: set_predicate(
        query, stalg.Expression.Subquery.SetPredicate.PREDICATE_OP_EXISTS
    ),
    "in_predicate": lambda query: in_predicate([column("v")], query),
    "set_comparison": lambda query: set_comparison(
        column("v"),
        query,
        stalg.Expression.Subquery.SetComparison.REDUCTION_OP_ANY,
        stalg.Expression.Subquery.SetComparison.COMPARISON_OP_EQ,
    ),
}


@pytest.mark.parametrize("builder", _SUBQUERY_BUILDERS.values(), ids=_SUBQUERY_BUILDERS)
def test_subquery_builders_inline_a_detached_plan(builder):
    inner = _dataframe_plans()[1]
    outer_schema = named_struct(
        names=["v"], struct=struct(types=[fp64(nullable=False)], nullable=False)
    )

    def build(query):
        return project(
            read_named_table("o", outer_schema), expressions=[builder(query)]
        )(registry)

    built = build(detach(inner, max_depth=0))
    assert _ordinals(built) == []
    assert built == build(inner)


def test_expression_type_of_an_ordinal_names_the_fix():
    expression = stalg.Expression(detached_expression_ordinal=3)
    with pytest.raises(ValueError, match="ordinal 3 .*resolve_detached"):
        infer_expression_type(expression, stt.Type.Struct())


def test_display_shows_a_malformed_detached_plan_as_is():
    plan = _plan(
        SPEC_PLAN_REL.replace(
            "detached_expression_ordinal: 0", "detached_expression_ordinal: 5"
        )
    )
    assert "$detached[5]" in PlanPrinter().stringify_plan(plan)


def test_resolve_blanks_resolved_entries_kept_in_place():
    # Entry 0 (resolved) holds ordinal 2 (resolved, trailing, dropped); entry 1 is
    # unreached and kept for the payload. Entry 0 must not keep pointing at 2.
    plan_rel = _with_any_payload(
        _plan_rel(
            SPEC_PLAN_REL.replace(
                "detached_expressions { literal { i64: 42 } }",
                "detached_expressions {"
                " nested { struct { fields { detached_expression_ordinal: 2 } } } }"
                "detached_expressions { literal { i64: 7 } }"
                "detached_expressions { literal { i64: 42 } }",
            )
        )
    )
    resolved = resolve_detached(plan_rel)
    table = resolved.detached_expressions
    assert len(table) == 2
    assert _ordinals(table[0]) == []
    assert table[1].literal.i64 == 7


def test_detach_walks_fields_in_declaration_order():
    # SwitchExpression declares ``match`` (field 3) before ``ifs`` (1) and
    # ``else`` (2); substrait-java numbers cuts in declaration order.
    plan = _deep_plan(0)
    expr = plan.relations[0].root.input.project.expressions[0]
    expr.Clear()
    switch = expr.switch_expression
    switch.match.literal.i64 = 1
    clause = switch.ifs.add()
    clause.then.literal.i64 = 2
    getattr(switch, "else").literal.i64 = 3
    clause.SetInParent()
    getattr(clause, "if").i64 = 1

    table = detach(plan, max_depth=0).relations[0].detached_expressions
    assert [e.literal.i64 for e in table[1:]] == [1, 2, 3]


def test_detach_processes_existing_entries_first():
    plan = _plan(
        SPEC_PLAN_REL.replace(
            "detached_expressions { literal { i64: 42 } }",
            "detached_expressions { nested { struct { fields { literal { i64: 42 } } } } }",
        )
    )
    project = plan.relations[0].root.input.project
    project.expressions.add().nested.struct.fields.add().literal.i64 = 7

    table = detach(plan, max_depth=0).relations[0].detached_expressions
    # Entry 0 existed; its child is cut first, then the relation tree's.
    assert table[1].literal.i64 == 42
    assert [e.literal.i64 for e in table[2:] if e.HasField("literal")] == [7]


def test_detach_with_nothing_to_cut_returns_input():
    plan = _deep_plan(200)
    plan.relations[0].root.input.project.ClearField("expressions")
    assert detach(plan, max_depth=10) is plan


def test_builders_inline_a_detached_plan_from_a_callable():
    plan = _dataframe_plans()[1]
    detached = detach(plan, max_depth=0)
    built = select(lambda registry: detached, expressions=[column("x")])(registry)
    assert _ordinals(built) == []
    assert built == select(plan, expressions=[column("x")])(registry)


def test_builders_refuse_entries_a_payload_may_reference():
    plan = _plan(SPEC_PLAN_REL + "detached_expressions { literal { i64: 7 } }")
    _with_any_payload(plan.relations[0])
    with pytest.raises(ValueError, match="would not travel with it"):
        select(plan, expressions=[column("value")])(registry)


def test_builders_reject_an_ordinal_without_a_table():
    plan = _plan(SPEC_PLAN_REL)
    plan.relations[0].ClearField("detached_expressions")
    with pytest.raises(ValueError, match="resolve_detached"):
        select(plan, expressions=[column("value")])(registry)


def test_display_shows_ordinal_function_arguments():
    plan = _dataframe_plans()[1]
    detached = detach(plan, max_depth=0)
    # Corrupt the table so the printer shows the plan unresolved.
    detached.relations[0].detached_expressions.add().detached_expression_ordinal = 0
    detached.relations[
        0
    ].root.input.project.expressions.add().detached_expression_ordinal = 99
    output = PlanPrinter().stringify_plan(detached)
    assert "<unknown_function_argument_value>" not in output
    assert "$detached[0]:" in output


def test_display_resolves_each_plan_rel_on_its_own():
    plan = _plan(SPEC_PLAN_REL)
    malformed = plan.relations.add()
    malformed.CopyFrom(plan.relations[0])
    malformed.root.input.project.expressions[0].detached_expression_ordinal = 5
    output = PlanPrinter().stringify_plan(plan)
    # The first PlanRel resolves; only the second prints its ordinal and table.
    assert "$detached[5]" in output
    assert output.count("$detached[0]:") == 1
