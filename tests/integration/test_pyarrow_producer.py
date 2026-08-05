"""Real ``pyarrow.substrait.serialize_expressions`` output folded into a build.

The direction here is the opposite of the engine round-trips next door: pyarrow is the
*producer* and this library the consumer, so nothing hands a newer-spec plan to an
older consumer and there is no native-crash risk. What makes these integration tests
is the coupling to a release we do not control: the numbering and URN shape pyarrow
emits is an observation about pyarrow, not a contract of this package.

They run by default anyway, unlike the engine round-trips. Nothing here can take the
process down, and while pyarrow does emit this shape these are the only tests that
would notice it changing -- the anchor handling is built on that observation, so
finding out from a red test beats finding out from a user. If a pyarrow release does
drift, add ``and not pyarrow`` to the ``addopts`` in pyproject.toml and the suite goes
green again without losing the tests that recorded what changed.

Nothing here is the only guard on the collector behaviour it exercises. Held by
pyarrow-free tests in ``tests/extension_registry/test_collector.py``, which run by
default:

- ``TestAmbiguousInput::test_two_bare_declarations_at_anchor_zero_in_separate_inputs_are_renumbered``
  is the collision below in pyarrow-free form: two inputs each carrying one bare
  anchor-0 declaration must come out as two distinct declarations. Note its sibling
  ``test_one_anchor_meaning_two_things_in_separate_inputs_is_accepted`` is *not* this
  guard despite the similar name -- its carriers name a resolvable URN, which the
  numbering this replaced already renumbered normally, so it passes either way.
- ``TestForeignPlans::test_zero_based_foreign_plan_folds_in`` covers a carrier
  numbering densely from 0, the way one ``serialize_expressions`` call does.
- ``TestForeignPlans::test_anchor_zero_declaration_*`` cover renumbering an anchor-0
  declaration together with the reference naming it, with and without a URN.

So what these add is only that pyarrow really does emit that shape: they go through
the actual bytes instead of an imitation of them, over the same shape
``examples/pyarrow_example.py`` exercises.
"""

import pytest
import substrait.extended_expression_pb2 as stee

from substrait.builders.extended_expression import column, scalar_function
from substrait.builders.plan import project, read_named_table
from substrait.extension_registry import ExtensionRegistry

pytestmark = [pytest.mark.integration, pytest.mark.pyarrow]

# A second guard behind the marker, so an explicit ``-m pyarrow`` on a machine without
# pyarrow skips rather than errors on collection.
pytest.importorskip("pyarrow")

ARITHMETIC = "extension:io.substrait:functions_arithmetic"


@pytest.fixture(scope="module")
def full_registry():
    return ExtensionRegistry(load_default_extensions=True)


@pytest.fixture(scope="module")
def serialize():
    """``*(pyarrow.compute -> expression) -> ExtendedExpression``, via pyarrow.

    One call serializes all of the given expressions into a single carrier, so the
    number of arguments chooses between pyarrow's one-declaration and its
    densely-numbered multi-declaration output. ``importorskip`` for each piece because
    pyarrow is not a dependency of this package, only the producer whose output this
    has to accept -- the marker is what keeps these out of a default run, and this is
    what keeps a marker-selected run honest where pyarrow is absent.
    """
    pa = pytest.importorskip("pyarrow")
    pc = pytest.importorskip("pyarrow.compute")
    pa_substrait = pytest.importorskip("pyarrow.substrait")
    schema = pa.schema([pa.field("a", pa.int64()), pa.field("b", pa.int64())])

    def _serialize(*expressions):
        buffer = pa_substrait.serialize_expressions(
            exprs=[build(pc) for build in expressions],
            names=[f"e{i}" for i in range(len(expressions))],
            schema=schema,
        )
        return stee.ExtendedExpression.FromString(bytes(buffer))

    return _serialize


def _declarations(carrier):
    """``{function anchor: name}`` for a carrier's extension declarations."""
    return {
        declaration.extension_function.function_anchor: declaration.extension_function.name
        for declaration in carrier.extensions
    }


def _project_functions(plan):
    """The function each expression of ``plan``'s ProjectRel resolves to, in order.

    Resolved through the plan's own declarations, so a reference naming an anchor the
    plan does not declare raises ``KeyError`` -- the failure a dropped or misnumbered
    declaration produces. Read at the one path these plans put their references rather
    than by the generic walk ``test_collector`` needs: there the point is that no
    reference field anywhere is missed, here the plan is built two lines above and its
    shape is known.
    """
    declarations = _declarations(plan)
    return [
        declarations[expression.scalar_function.function_reference]
        for expression in plan.relations[-1].root.input.project.expressions
    ]


class TestPyarrowExpressions:
    """pyarrow numbers densely from 0 and emits a bare
    ``extension_function { name: "add" }`` naming no URN -- the producer that motivated
    all of the anchor-0 handling.
    """

    def test_one_expression_folds_in(self, full_registry, serialize):
        expression = serialize(lambda pc: pc.field("a") + pc.field("b"))
        # The premise of everything below: anchor 0, no URN, reference 0.
        assert _declarations(expression) == {0: "add"}
        assert not expression.extension_urns
        assert [
            e.expression.scalar_function.function_reference
            for e in expression.referred_expr
        ] == [0]

        out = project(
            read_named_table("t", expression.base_schema), expressions=[expression]
        )(full_registry)

        assert _declarations(out) == {1: "add"}
        assert _project_functions(out) == ["add"]

    def test_two_expressions_get_their_own_declarations(self, full_registry, serialize):
        """Each serialized expression is its own anchor space, so two of them both
        declare their function at 0 and both reference 0. Folded into one plan they
        used to stay there: two declarations at anchor 0, with every reference to it
        resolving to whichever one the consumer found first -- ``a * b`` silently
        readable as ``a + b``.
        """
        add = serialize(lambda pc: pc.field("a") + pc.field("b"))
        multiply = serialize(lambda pc: pc.field("a") * pc.field("b"))
        assert _declarations(add) == {0: "add"}
        assert _declarations(multiply) == {0: "multiply"}

        out = project(
            read_named_table("t", add.base_schema), expressions=[add, multiply]
        )(full_registry)

        assert _declarations(out) == {1: "add", 2: "multiply"}
        assert _project_functions(out) == ["add", "multiply"]

    def test_several_expressions_in_one_carrier_fold_in(self, full_registry, serialize):
        """Serialized together, pyarrow numbers them densely from 0 in one carrier --
        so anchor 0 arrives alongside anchors it must not be renumbered on top of.
        """
        carrier = serialize(
            lambda pc: pc.field("a") + pc.field("b"),
            lambda pc: pc.field("a") * pc.field("b"),
            lambda pc: pc.field("a") - pc.field("b"),
        )
        assert sorted(_declarations(carrier)) == [0, 1, 2]

        out = project(
            read_named_table("t", carrier.base_schema), expressions=[carrier]
        )(full_registry)

        declarations = _declarations(out)
        assert sorted(declarations) == [1, 2, 3]
        assert set(declarations.values()) == {"add", "multiply", "subtract"}
        assert _project_functions(out) == ["add", "multiply", "subtract"]

    def test_mixed_with_functions_this_build_resolves(self, full_registry, serialize):
        """The two numbering spaces meet: pyarrow's ``add`` (no URN) and this
        library's ``add:i64_i64`` (naming ARITHMETIC) are different identities that
        must not be conflated, and no reference may end up naming the other's.
        """
        expression = serialize(lambda pc: pc.field("a") + pc.field("b"))
        out = project(
            read_named_table("t", expression.base_schema),
            expressions=[
                scalar_function(ARITHMETIC, "add", [column("a"), column("b")]),
                expression,
            ],
        )(full_registry)

        assert _declarations(out) == {1: "add:i64_i64", 2: "add"}
        assert _project_functions(out) == ["add:i64_i64", "add"]
        # Only the resolved one names a URN; the URN table stays 1-based so the
        # other's unset reference matches nothing.
        assert [(u.extension_urn_anchor, u.urn) for u in out.extension_urns] == [
            (1, ARITHMETIC)
        ]
        assert out.extensions[1].extension_function.extension_urn_reference == 0
