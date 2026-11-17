import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import literal, scalar_subquery
from substrait.builders.plan import cross, fetch, read_named_table, reference
from substrait.builders.plan import set as set_relation
from substrait.builders.type import boolean, i64


def _filtered_plan(anchor=0, result=True):
    schema = stt.NamedStruct(
        names=["id"],
        struct=stt.Type.Struct(
            types=[i64()], nullability=stt.Type.NULLABILITY_REQUIRED
        ),
    )
    plan = read_named_table("rows", schema)(None)
    definition = plan.named_lambdas.add(lambda_anchor=anchor, name="predicate")
    predicate = getattr(definition, "lambda")
    predicate.parameters.nullability = stt.Type.NULLABILITY_REQUIRED
    predicate.body.literal.boolean = result
    invocation = plan.relations[0].root.input.read.filter.lambda_invocation
    invocation.named_lambda.lambda_reference = anchor
    invocation.arguments.SetInParent()
    return plan


def test_fetch_preserves_the_lambda_called_by_its_input():
    source = _filtered_plan()
    result = fetch(source, offset=None, count=literal(2, i64()))(None)

    fetched = result.relations[0].root.input.fetch
    assert fetched.input == source.relations[0].root.input
    assert result.named_lambdas == source.named_lambdas
    assert (
        fetched.input.read.filter.lambda_invocation.named_lambda.lambda_reference
        == result.named_lambdas[0].lambda_anchor
    )


def _negation(source, anchor):
    source.extension_urns.add(
        extension_urn_anchor=1, urn="extension:io.substrait:functions_boolean"
    )
    declaration = source.extensions.add().extension_function
    declaration.extension_urn_reference = 1
    declaration.function_anchor = anchor
    declaration.name = "not:bool"
    expression = stalg.Expression()
    expression.scalar_function.function_reference = anchor
    expression.scalar_function.arguments.add().value.literal.boolean = False
    expression.scalar_function.output_type.CopyFrom(boolean(nullable=False))
    return expression


def test_function_remap_in_a_definition_does_not_renumber_a_lambda():
    source = _filtered_plan()
    body = getattr(source.named_lambdas[0], "lambda").body
    body.CopyFrom(_negation(source, 0))

    result = fetch(source, offset=None, count=None)(None)
    definition = result.named_lambdas[0]
    assert definition.lambda_anchor == 0
    anchor = result.extensions[0].extension_function.function_anchor
    assert anchor != 0
    assert (
        getattr(definition, "lambda").body.scalar_function.function_reference == anchor
    )
    assert body.scalar_function.function_reference == 0


def test_multi_input_keeps_disjoint_and_shared_definitions():
    left, right = _filtered_plan(0), _filtered_plan(3, False)
    reused = _filtered_plan(0)
    reused.named_lambdas[0].name = "other diagnostic name"

    result = cross(cross(left, right), reused)(None)
    assert list(result.named_lambdas) == [*left.named_lambdas, *right.named_lambdas]
    joined = result.relations[0].root.input.cross
    assert joined.left.cross.right == right.relations[0].root.input
    assert joined.right == reused.relations[0].root.input


def test_multi_input_rejects_conflicting_definitions_at_the_same_anchor():
    with pytest.raises(
        ValueError, match="conflicting definitions for named lambda anchor 0"
    ):
        cross(_filtered_plan(), _filtered_plan(result=False))(None)


def test_reference_in_a_definition_cannot_bind_to_another_inputs_lambda():
    left, right = _filtered_plan(2), _filtered_plan(0)
    body = getattr(left.named_lambdas[0], "lambda").body
    body.named_lambda_reference.lambda_reference = 0
    with pytest.raises(
        ValueError, match="unknown lambda_anchor 0 in Plan.named_lambdas"
    ):
        set_relation([left, right], stalg.SetRel.SET_OP_UNION_ALL)(None)


def test_definition_cannot_silently_rebind_its_shared_subtree():
    left = reference(_filtered_plan(0))(None)
    right = reference(_filtered_plan(1))(None)
    definition = getattr(right.named_lambdas.add(lambda_anchor=2), "lambda")
    definition.parameters.nullability = stt.Type.NULLABILITY_REQUIRED
    definition.body.subquery.scalar.input.reference.subtree_ordinal = 0

    with pytest.raises(ValueError, match="cannot rebase shared subtree references"):
        set_relation([left, right], stalg.SetRel.SET_OP_UNION_ALL)(None)


def test_fetch_rejects_a_type_alias_used_in_a_definition():
    source = _filtered_plan()
    source.type_aliases.add(type_alias_anchor=0, type=boolean(nullable=False))
    cast = getattr(source.named_lambdas[0], "lambda").body.cast
    cast.input.literal.boolean = True
    cast.type.alias.type_alias_reference = 0
    cast.type.alias.nullability = stt.Type.NULLABILITY_REQUIRED

    with pytest.raises(ValueError, match="type_aliases"):
        fetch(source, None, None)(None)


def _exists_over_subtree(expression, ordinal=0):
    exists = expression.subquery.set_predicate
    exists.predicate_op = stalg.Expression.Subquery.SetPredicate.PREDICATE_OP_EXISTS
    exists.tuples.reference.subtree_ordinal = ordinal


def _subtree_read_by_definition(source):
    source.relations.insert(0, stp.PlanRel(rel=source.relations[0].root.input))
    _exists_over_subtree(getattr(source.named_lambdas[0], "lambda").body)
    read = source.relations[0].rel.read
    read.ClearField("filter")
    return read


def test_function_remap_rejects_opaque_subtree_read_by_a_definition():
    source = _filtered_plan()
    read = _subtree_read_by_definition(source)
    read.advanced_extension.enhancement.Pack(_negation(source, 7))
    with pytest.raises(ValueError, match="cannot remap function anchors"):
        fetch(source, None, None)(None)


@pytest.mark.parametrize("opaque", [False, True])
def test_subtree_remap_checks_dependencies_beyond_the_definition(opaque):
    left, right = _filtered_plan(0), _filtered_plan(1)
    shared = stalg.Rel(read=_subtree_read_by_definition(left))
    _exists_over_subtree(shared.read.filter)
    if opaque:
        shared.read.advanced_extension.enhancement.Pack(shared.read.filter)
        shared.read.ClearField("filter")
    _subtree_read_by_definition(right).named_table.names[0] = "other_rows"
    for plan in (left, right):
        plan.relations.insert(1, stp.PlanRel(rel=shared))
    _exists_over_subtree(getattr(right.named_lambdas[0], "lambda").body, 1)

    with pytest.raises(ValueError, match="cannot rebase shared subtree references"):
        set_relation([left, right], stalg.SetRel.SET_OP_UNION_ALL)(None)


@pytest.mark.parametrize("through_subtree", [False, True])
def test_fetch_rejects_only_a_parameter_binding_used_in_a_definition(through_subtree):
    source = _filtered_plan()
    if through_subtree:
        parameter = _subtree_read_by_definition(source).filter.dynamic_parameter
    else:
        parameter = getattr(source.named_lambdas[0], "lambda").body.dynamic_parameter
    parameter.parameter_reference = 0
    parameter.type.CopyFrom(boolean(nullable=False))
    source.parameter_bindings.add(parameter_anchor=1).value.boolean = True
    assert fetch(source, None, None)(None).named_lambdas == source.named_lambdas

    source.parameter_bindings.add(parameter_anchor=0).value.boolean = False
    with pytest.raises(ValueError, match="parameter_bindings"):
        fetch(source, None, None)(None)


def test_subquery_rejects_a_named_invocation_but_allows_unused_definitions():
    source = _filtered_plan()
    with pytest.raises(ValueError, match="cannot embed a subquery.*named lambda"):
        scalar_subquery(source)(None, None)

    read = source.relations[0].root.input.read
    read.advanced_extension.enhancement.Pack(read.filter)
    read.ClearField("filter")
    with pytest.raises(ValueError, match="cannot embed a subquery.*named lambda"):
        scalar_subquery(source)(None, None)

    read.ClearField("advanced_extension")
    expression = scalar_subquery(source)(None, None)
    assert (
        expression.referred_expr[0].expression.subquery.scalar.input
        == source.relations[0].root.input
    )


def test_nested_exists_cannot_hide_a_subquerys_named_lambda_dependency():
    source = _filtered_plan()
    source.relations.insert(0, stp.PlanRel(rel=source.relations[0].root.input))
    _exists_over_subtree(source.relations[-1].root.input.read.filter)
    with pytest.raises(ValueError, match="cannot embed a subquery.*named lambda"):
        scalar_subquery(source)(None, None)
