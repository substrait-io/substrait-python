"""Tests for plan-local extension anchor assignment.

Extension anchors are plan-local in Substrait, so they are owned by a per-build
``ExtensionCollector`` rather than by the ``ExtensionRegistry`` catalog. These tests
pin the two properties that ownership buys: anchors that depend only on the plan
(not on which extensions happen to be registered), and correct folding of a plan
built elsewhere into a new build.
"""

import importlib.resources as importlib_resources
from collections.abc import Iterable

import pytest
import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.extensions.extensions_pb2 as ste
import substrait.plan_pb2 as stplan
import substrait.type_pb2 as stt
from google.protobuf.message import Message

from substrait.builders.extended_expression import (
    alias,
    column,
    in_predicate,
    scalar_function,
    scalar_subquery,
    set_comparison,
    set_predicate,
)
from substrait.builders.plan import (
    filter,
    project,
    read_named_table,
    reference,
    with_execution_behavior,
)
from substrait.extension_registry import (
    ExtensionCollector,
    ExtensionRegistry,
    build_scope,
    function_reference,
)

ARITHMETIC = "extension:io.substrait:functions_arithmetic"
COMPARISON = "extension:io.substrait:functions_comparison"
PER_RECORD = stplan.ExecutionBehavior.VARIABLE_EVALUATION_MODE_PER_RECORD

I64 = stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED))
NAMED_STRUCT = stt.NamedStruct(
    names=["a", "b"],
    struct=stt.Type.Struct(types=[I64, I64], nullability=stt.Type.NULLABILITY_REQUIRED),
)


@pytest.fixture(scope="module")
def full_registry():
    return ExtensionRegistry(load_default_extensions=True)


@pytest.fixture(scope="module")
def arithmetic_only_registry():
    """A registry holding *only* functions_arithmetic.

    Anchors must not differ between this and the full default set: that
    dependence is exactly what made plans non-reproducible.
    """
    registry = ExtensionRegistry(load_default_extensions=False)
    registry.register_extension_yaml(
        next(
            iter(
                importlib_resources.files("substrait_extensions.extensions").glob(
                    "functions_arithmetic.yaml"
                )
            )
        )
    )
    return registry


def _add_plan(registry):
    """``SELECT a + b FROM t`` -- one function, so one declaration."""
    plan = read_named_table("t", NAMED_STRUCT)
    return project(
        plan,
        expressions=[scalar_function(ARITHMETIC, "add", [column("a"), column("b")])],
    )(registry)


def _declarations(plan):
    """``{function anchor: name}`` for a plan's extension declarations."""
    return {
        declaration.extension_function.function_anchor: declaration.extension_function.name
        for declaration in plan.extensions
    }


_REFERENCE_FIELDS = (
    "function_reference",
    "comparison_function_reference",
    "custom_function_reference",
)


def _function_references(msg):
    """Every function reference anywhere in ``msg``, a reference of 0 included.

    Deliberately not ``substrait.utils``'s own walk: a test reusing the code under
    test could not notice it missing a field. Presence is read the way it has to be
    -- ``function_reference`` has none, so it counts whenever its containing message
    is set, which is the only way a reference of 0 is visible at all; the two oneof
    members count only when their oneof selects them.
    """
    found = []
    for name in _REFERENCE_FIELDS:
        field = msg.DESCRIPTOR.fields_by_name.get(name)
        if field is None:
            continue
        oneof = field.containing_oneof
        if oneof is not None and msg.WhichOneof(oneof.name) != name:
            continue
        found.append(getattr(msg, name))
    for _, value in msg.ListFields():
        if isinstance(value, Message):
            found += _function_references(value)
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            items = value.values() if hasattr(value, "values") else value
            for item in items:
                if isinstance(item, Message):
                    found += _function_references(item)
    return found


def _resolved_functions(plan):
    """The set of function names every reference in ``plan`` resolves to.

    Raises ``KeyError`` on a dangling reference -- one naming an anchor the plan does
    not declare -- which is the failure a lost declaration produces.
    """
    declarations = _declarations(plan)
    return {declarations[reference] for reference in _function_references(plan)}


def _declaration(name, *, function_anchor=0, urn_reference=0):
    """A function declaration with its plan-local anchors spelled out."""
    return ste.SimpleExtensionDeclaration(
        extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
            extension_urn_reference=urn_reference,
            function_anchor=function_anchor,
            name=name,
        )
    )


def _carrier(*declarations, urns=()):
    """A carrier holding only the two fields ``adopt`` reads, from ``(anchor, urn)``.

    A Plan rather than an ExtendedExpression merely because it is the shorter of the
    two to spell; ``adopt`` treats them alike.
    """
    return stplan.Plan(
        extension_urns=[
            ste.SimpleExtensionURN(extension_urn_anchor=anchor, urn=urn)
            for anchor, urn in urns
        ],
        extensions=declarations,
    )


def _anchor_zero_expression(declaration, *, urns=(), output_name="opaque"):
    """An ExtendedExpression naming ``declaration`` at anchor 0, from both ends.

    The shape pyarrow's ``serialize_expressions`` emits: a declaration at anchor 0
    and a ``function_reference`` left at 0 to name it. 0 is a valid
    anchor/reference (spelled out in the protos since Substrait v0.83.0), so this is
    an ordinary carrier -- what makes it worth its own
    helper is that proto3 omits both zero-valued fields from the wire, so a
    ``ListFields()`` walk sees neither.
    """
    return stee.ExtendedExpression(
        base_schema=NAMED_STRUCT,
        extension_urns=[
            ste.SimpleExtensionURN(extension_urn_anchor=anchor, urn=urn)
            for anchor, urn in urns
        ],
        extensions=[declaration],
        referred_expr=[
            stee.ExpressionReference(
                expression=stalg.Expression(
                    scalar_function=stalg.Expression.ScalarFunction(output_type=I64)
                ),
                output_names=[output_name],
            )
        ],
    )


class TestCollector:
    def test_allocates_from_one_on_first_use(self):
        with build_scope() as (collector, owns_scope):
            assert owns_scope
            assert collector.function_reference(ARITHMETIC, "add:i64_i64") == 1
            assert collector.function_reference(COMPARISON, "gt:any_any") == 2

    def test_same_identity_reuses_its_reference(self):
        collector = ExtensionCollector()
        first = collector.function_reference(ARITHMETIC, "add:i64_i64")
        collector.function_reference(COMPARISON, "gt:any_any")
        assert collector.function_reference(ARITHMETIC, "add:i64_i64") == first

    def test_urn_anchors_assigned_at_emit(self):
        collector = ExtensionCollector()
        collector.function_reference(ARITHMETIC, "add:i64_i64")
        collector.function_reference(COMPARISON, "gt:any_any")
        collector.function_reference(ARITHMETIC, "subtract:i64_i64")

        out = stplan.Plan()
        collector.write_into(out)

        # Two distinct URNs, densely numbered in order of first reference.
        assert [(u.extension_urn_anchor, u.urn) for u in out.extension_urns] == [
            (1, ARITHMETIC),
            (2, COMPARISON),
        ]
        # Three functions, referencing their URN's anchor.
        assert [
            (
                d.extension_function.function_anchor,
                d.extension_function.name,
                d.extension_function.extension_urn_reference,
            )
            for d in out.extensions
        ] == [
            (1, "add:i64_i64", 1),
            (2, "gt:any_any", 2),
            (3, "subtract:i64_i64", 1),
        ]

    def test_declarations_dedupe_on_the_urn_they_name(self):
        """Declarations are deduplicated on the identity they arrived with, not on
        their bytes: the same function reaching two inputs under different incoming
        URN anchors is one declaration, while two that differ only in which URN they
        name stay distinct.

        Spelled with anchor-0 declarations because that is where the two could most
        easily be confused -- their bytes differ only in the URN reference, which is
        the field the identity is read from.
        """
        collector = ExtensionCollector()
        collector.adopt(
            _carrier(_declaration("floor", urn_reference=7), urns=[(7, COMPARISON)])
        )
        collector.adopt(
            _carrier(_declaration("floor", urn_reference=3), urns=[(3, COMPARISON)])
        )
        collector.adopt(
            _carrier(_declaration("floor", urn_reference=1), urns=[(1, ARITHMETIC)])
        )

        out = stplan.Plan()
        collector.write_into(out)

        urns = {u.extension_urn_anchor: u.urn for u in out.extension_urns}
        assert [
            (
                d.extension_function.function_anchor,
                d.extension_function.name,
                urns[d.extension_function.extension_urn_reference],
            )
            for d in out.extensions
        ] == [(1, "floor", COMPARISON), (2, "floor", ARITHMETIC)]

    def test_a_type_declaration_is_refused_rather_than_dropped(self):
        """Type and type-variation declarations have anchors of their own that nothing
        re-derives yet, so collecting one would silently lose it (the same gap
        ``merge_extension_declarations`` reports)."""
        carrier = _carrier(
            ste.SimpleExtensionDeclaration(
                extension_type=ste.SimpleExtensionDeclaration.ExtensionType(
                    type_anchor=1, name="point"
                )
            ),
            urns=[(1, "extension:acme:custom")],
        )
        with pytest.raises(NotImplementedError, match="extension_type"):
            ExtensionCollector().adopt(carrier)

    def test_outside_a_build_scope_is_an_error(self):
        with pytest.raises(RuntimeError, match="no build in progress"):
            function_reference(ARITHMETIC, "add:i64_i64")

    def test_nested_scope_defers_to_the_owner(self):
        with build_scope() as (outer, outer_owns):
            with build_scope() as (inner, inner_owns):
                assert outer_owns and not inner_owns
                assert inner is outer


class TestPlanLocalAnchors:
    def test_anchors_start_at_one(self, full_registry):
        plan = _add_plan(full_registry)
        assert [u.extension_urn_anchor for u in plan.extension_urns] == [1]
        assert _declarations(plan) == {1: "add:i64_i64"}

    def test_independent_of_registry_contents(
        self, full_registry, arithmetic_only_registry
    ):
        """The headline #236 symptom: a one-function plan used to emit anchor 284
        against the default set and 4 against a minimal one."""
        assert _add_plan(full_registry).SerializeToString(
            deterministic=True
        ) == _add_plan(arithmetic_only_registry).SerializeToString(deterministic=True)

    def test_repeated_builds_are_byte_identical(self, full_registry):
        assert _add_plan(full_registry).SerializeToString(
            deterministic=True
        ) == _add_plan(full_registry).SerializeToString(deterministic=True)

    def test_declarations_are_dense_and_ordered_by_first_use(self, full_registry):
        plan = read_named_table("t", NAMED_STRUCT)
        plan = project(
            plan,
            expressions=[
                scalar_function(ARITHMETIC, "add", [column("a"), column("b")]),
                scalar_function(ARITHMETIC, "subtract", [column("a"), column("b")]),
                # `add` again: must reuse its reference rather than allocate a new one.
                scalar_function(ARITHMETIC, "add", [column("b"), column("a")]),
            ],
        )(full_registry)
        assert _declarations(plan) == {1: "add:i64_i64", 2: "subtract:i64_i64"}


def _foreign_plan(registry, *, urn, name, urn_anchor, function_anchor, inners=()):
    """A plan built "elsewhere": a filter whose condition references its own anchors.

    Deliberately uses anchor numbers a fresh build would hand out to *different*
    functions, which is what used to corrupt the merged output.

    ``inners`` is a sequence of further ``(urn, name, urn_anchor, function_anchor)``
    functions, nested left to right into the outer one's argument, so the plan
    carries a reference at each of several distinct paths. They are declared *after*
    the outer one, so numbering by first use in declaration order can be made to
    permute the incoming anchors rather than merely shift them -- see
    ``TestForeignPlans.test_execution_behavior_wrapper_does_not_double_remap``.
    """
    plan = read_named_table("t", NAMED_STRUCT)(registry)
    plan.ClearField("extension_urns")
    plan.ClearField("extensions")
    declared = [(urn, name, urn_anchor, function_anchor), *inners]
    for d_urn, d_name, d_urn_anchor, d_function_anchor in declared:
        plan.extension_urns.append(
            ste.SimpleExtensionURN(extension_urn_anchor=d_urn_anchor, urn=d_urn)
        )
        plan.extensions.append(
            ste.SimpleExtensionDeclaration(
                extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
                    extension_urn_reference=d_urn_anchor,
                    function_anchor=d_function_anchor,
                    name=d_name,
                )
            )
        )
    root = plan.relations[-1].root
    argument = stalg.Expression(
        selection=stalg.Expression.FieldReference(
            direct_reference=stalg.Expression.ReferenceSegment(
                struct_field=stalg.Expression.ReferenceSegment.StructField(field=0)
            ),
            root_reference=stalg.Expression.FieldReference.RootReference(),
        )
    )
    for inner in reversed(inners):
        argument = stalg.Expression(
            scalar_function=stalg.Expression.ScalarFunction(
                function_reference=inner[3],
                arguments=[stalg.FunctionArgument(value=argument)],
                output_type=I64,
            )
        )
    condition = stalg.Expression(
        scalar_function=stalg.Expression.ScalarFunction(
            function_reference=function_anchor,
            arguments=[stalg.FunctionArgument(value=argument)],
            output_type=stt.Type(
                bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_REQUIRED)
            ),
        )
    )
    root.input.CopyFrom(
        stalg.Rel(filter=stalg.FilterRel(input=root.input, condition=condition))
    )
    return plan


class TestForeignPlans:
    # Anchor numbers the incoming plan used. 1 is what this build would hand out
    # anyway (no rewrite needed); the larger values force the incoming relations to
    # be renumbered, which is the path that used to corrupt the output.
    @pytest.mark.parametrize("urn_anchor,function_anchor", [(1, 1), (9, 5), (3, 284)])
    def test_extending_a_foreign_plan_does_not_collide(
        self, full_registry, urn_anchor, function_anchor
    ):
        """#236's correctness bug: this used to emit two URNs at one anchor and two
        functions at another, making the plan's function references ambiguous."""
        foreign = _foreign_plan(
            full_registry,
            urn=COMPARISON,
            name="gt:any_any",
            urn_anchor=urn_anchor,
            function_anchor=function_anchor,
        )
        out = project(
            foreign,
            expressions=[
                scalar_function(ARITHMETIC, "add", [column("a"), column("b")])
            ],
        )(full_registry)

        function_anchors = [
            d.extension_function.function_anchor for d in out.extensions
        ]
        urn_anchors = [u.extension_urn_anchor for u in out.extension_urns]
        assert len(function_anchors) == len(set(function_anchors))
        assert len(urn_anchors) == len(set(urn_anchors))

        declarations = _declarations(out)
        assert set(declarations.values()) == {"gt:any_any", "add:i64_i64"}

        # The foreign condition's reference must still resolve to gt, and ours to add.
        project_rel = out.relations[-1].root.input.project
        foreign_reference = (
            project_rel.input.filter.condition.scalar_function.function_reference
        )
        our_reference = project_rel.expressions[0].scalar_function.function_reference
        assert declarations[foreign_reference] == "gt:any_any"
        assert declarations[our_reference] == "add:i64_i64"

    @pytest.mark.parametrize("nested", [False, True], ids=["outermost", "nested"])
    def test_execution_behavior_wrapper_does_not_double_remap(
        self, full_registry, nested
    ):
        """``with_execution_behavior`` copies its input plan wholesale, so it used to
        forward the input's declarations -- stale, because ``_bind`` had already
        renumbered the relations against the collector. An enclosing builder adopted
        that numbering a second time and re-applied a remap the relations already
        carried, silently pointing each reference at the other's declaration.

        The foreign layout makes re-deriving the pair *permute* the incoming anchors
        (gt@2 with subtract@1 becomes the swap ``{2: 1, 1: 2}``). A layout that only
        shifts them hides this: re-applying a remap whose new values are not
        themselves keys is accidentally idempotent.
        """
        foreign = _foreign_plan(
            full_registry,
            urn=COMPARISON,
            name="gt:any_any",
            urn_anchor=1,
            function_anchor=2,
            inners=[(ARITHMETIC, "subtract:i64_i64", 2, 1)],
        )
        unbound = with_execution_behavior(foreign, PER_RECORD)
        if nested:
            unbound = project(unbound, expressions=[column("a")])
        out = unbound(full_registry)

        root_input = out.relations[-1].root.input
        condition = (
            root_input.project.input if nested else root_input
        ).filter.condition.scalar_function
        declarations = _declarations(out)
        assert declarations[condition.function_reference] == "gt:any_any"
        inner_reference = condition.arguments[
            0
        ].value.scalar_function.function_reference
        assert declarations[inner_reference] == "subtract:i64_i64"
        # The wrapper still does its actual job.
        assert out.execution_behavior.variable_eval_mode == PER_RECORD

    def test_function_absent_from_the_registry_is_carried_through(self, full_registry):
        """Identities come from the declaration, not a catalog lookup, so a plan
        referencing an unknown extension function survives being extended."""
        foreign = _foreign_plan(
            full_registry,
            urn="extension:acme:custom",
            name="acme_thing:i64",
            urn_anchor=1,
            function_anchor=1,
        )
        out = project(
            foreign,
            expressions=[
                scalar_function(ARITHMETIC, "add", [column("a"), column("b")])
            ],
        )(full_registry)

        declarations = _declarations(out)
        assert set(declarations.values()) == {"acme_thing:i64", "add:i64_i64"}
        assert "extension:acme:custom" in {u.urn for u in out.extension_urns}
        foreign_reference = out.relations[
            -1
        ].root.input.project.input.filter.condition.scalar_function.function_reference
        assert declarations[foreign_reference] == "acme_thing:i64"

    def test_anchor_zero_declaration_is_renumbered_with_its_reference(
        self, full_registry
    ):
        """pyarrow's ``serialize_expressions`` emits a bare
        ``extension_function { name: "add" }`` at anchor 0, named by a
        ``function_reference`` left at 0. Both are valid
        (since Substrait v0.83.0), so the declaration is re-derived like any
        other -- 1-based on the way out, because the same protos ask producers to
        prefer non-zero -- and the reference that named it moves with it.

        What must survive is the *identity* (``add``, naming no URN) and the
        reference's *meaning*, not the number 0.
        """
        expression = _anchor_zero_expression(_declaration("add"), output_name="total")
        before = expression.SerializeToString(deterministic=True)
        out = project(read_named_table("t", NAMED_STRUCT), expressions=[expression])(
            full_registry
        )

        assert _declarations(out) == {1: "add"}
        # Naming no URN, it must still name none: an unset extension_urn_reference
        # reads back as 0, which is why URN anchors are emitted 1-based.
        assert not out.extension_urns
        assert out.extensions[0].extension_function.extension_urn_reference == 0
        project_rel = out.relations[-1].root.input.project
        assert project_rel.expressions[0].scalar_function.function_reference == 1
        # The caller's expression is rewritten on a copy, not in place.
        assert expression.SerializeToString(deterministic=True) == before

    def test_anchor_zero_declaration_coexists_with_collected_ones(self, full_registry):
        """An incoming anchor-0 declaration is numbered into the same dense 1-based
        space as the functions this build resolves, so the two cannot collide -- and
        neither reference is left naming the other's declaration."""
        expression = _anchor_zero_expression(_declaration("opaque"))
        out = project(
            read_named_table("t", NAMED_STRUCT),
            expressions=[
                expression,
                scalar_function(ARITHMETIC, "add", [column("a"), column("b")]),
            ],
        )(full_registry)

        declarations = _declarations(out)
        assert declarations == {1: "opaque", 2: "add:i64_i64"}
        references = [
            e.scalar_function.function_reference
            for e in out.relations[-1].root.input.project.expressions
        ]
        assert [declarations[r] for r in references] == ["opaque", "add:i64_i64"]

    def test_anchor_zero_declaration_naming_a_urn_is_renumbered_too(
        self, full_registry
    ):
        """Resolving a URN changes nothing about the anchor: 0 is renumbered either
        way, and the URN reference is re-derived alongside it -- 7 indexes the
        incoming carrier's URN table, which this build replaces, so it must end up
        naming a URN the output actually declares rather than dangling.
        """
        expression = _anchor_zero_expression(
            _declaration("gt", urn_reference=7),
            urns=[(7, COMPARISON)],
            output_name="flag",
        )
        out = project(
            read_named_table("t", NAMED_STRUCT),
            expressions=[
                expression,
                scalar_function(ARITHMETIC, "add", [column("a"), column("b")]),
            ],
        )(full_registry)

        declarations = _declarations(out)
        assert declarations == {1: "gt", 2: "add:i64_i64"}
        references = [
            e.scalar_function.function_reference
            for e in out.relations[-1].root.input.project.expressions
        ]
        assert [declarations[r] for r in references] == ["gt", "add:i64_i64"]

        urns = {u.extension_urn_anchor: u.urn for u in out.extension_urns}
        assert urns == {1: COMPARISON, 2: ARITHMETIC}
        assert {
            declarations[d.extension_function.function_anchor]: urns[
                d.extension_function.extension_urn_reference
            ]
            for d in out.extensions
        } == {"gt": COMPARISON, "add:i64_i64": ARITHMETIC}

    def test_zero_based_foreign_plan_folds_in(self, full_registry):
        """A producer numbering from 0 rather than 1 is not a special case: 0 is a
        valid anchor/reference (since Substrait v0.83.0), so a plan whose URN
        anchors, function anchors and references all run 0,1,2 is renumbered whole.

        Every one of its three references sits at a different depth, so a walk that
        cannot see a reference of 0 leaves the outermost one naming this build's
        first declaration instead -- a silently different function, not a load error.
        """
        foreign = _foreign_plan(
            full_registry,
            urn=COMPARISON,
            name="gt:any_any",
            urn_anchor=0,
            function_anchor=0,
            inners=[
                (ARITHMETIC, "add:i64_i64", 1, 1),
                (ARITHMETIC, "subtract:i64_i64", 2, 2),
            ],
        )
        out = project(
            foreign,
            expressions=[
                scalar_function(ARITHMETIC, "multiply", [column("a"), column("b")])
            ],
        )(full_registry)

        declarations = _declarations(out)
        assert declarations == {
            1: "gt:any_any",
            2: "add:i64_i64",
            3: "subtract:i64_i64",
            4: "multiply:i64_i64",
        }
        assert _resolved_functions(out) == set(declarations.values())

        # Each reference by path, so the assertion above cannot be satisfied by three
        # references that all happen to resolve to *some* declared function.
        condition = out.relations[
            -1
        ].root.input.project.input.filter.condition.scalar_function
        add = condition.arguments[0].value.scalar_function
        subtract = add.arguments[0].value.scalar_function
        assert declarations[condition.function_reference] == "gt:any_any"
        assert declarations[add.function_reference] == "add:i64_i64"
        assert declarations[subtract.function_reference] == "subtract:i64_i64"

        # The incoming plan declared ARITHMETIC at two anchors; emission collapses
        # them, and no URN anchor is emitted at 0 for an unset reference to match.
        urns = {u.extension_urn_anchor: u.urn for u in out.extension_urns}
        assert urns == {1: COMPARISON, 2: ARITHMETIC}

    def test_rebuilding_a_materialized_plan_is_stable(self, full_registry):
        """Extending a plan this library already materialized needs no renumbering,
        so the result is the same as building the whole chain in one go."""
        one_shot = read_named_table("t", NAMED_STRUCT)
        one_shot = project(
            one_shot,
            expressions=[
                scalar_function(ARITHMETIC, "add", [column("a"), column("b")])
            ],
        )
        one_shot = project(one_shot, expressions=[column("add(a,b)")])(full_registry)

        stepwise = read_named_table("t", NAMED_STRUCT)(full_registry)
        stepwise = project(
            stepwise,
            expressions=[
                scalar_function(ARITHMETIC, "add", [column("a"), column("b")])
            ],
        )(full_registry)
        stepwise = project(stepwise, expressions=[column("add(a,b)")])(full_registry)

        assert one_shot.SerializeToString(
            deterministic=True
        ) == stepwise.SerializeToString(deterministic=True)


def _inner_query():
    """A subquery's inner query: ``SELECT * FROM u WHERE a + b > a``.

    Its two functions are declared innermost-first (``add`` at 1, ``gt`` at 2), so a
    build that resolved ``gt`` before folding this in maps them ``{1: 2, 2: 1}``: a
    *permutation*, which a remap applied twice would swap back and a dropped
    declaration cannot fake. A layout that only shifts the anchors hides both.
    """
    return filter(
        read_named_table("u", NAMED_STRUCT),
        expression=scalar_function(
            COMPARISON,
            "gt",
            [
                scalar_function(ARITHMETIC, "add", [column("a"), column("b")]),
                column("a"),
            ],
        ),
    )


# ``builder(query) -> UnboundExtendedExpression``, and the bound expression's path to
# the Rel the inner query was lifted into -- one entry per subquery flavour, since each
# embeds its Rel in a different field of ``Expression.Subquery``.
_SUBQUERY_BUILDERS = {
    "scalar_subquery": (
        scalar_subquery,
        lambda expression: expression.subquery.scalar.input,
    ),
    "set_predicate": (
        lambda query: set_predicate(
            query, stalg.Expression.Subquery.SetPredicate.PREDICATE_OP_EXISTS
        ),
        lambda expression: expression.subquery.set_predicate.tuples,
    ),
    "in_predicate": (
        lambda query: in_predicate([column("a")], query),
        lambda expression: expression.subquery.in_predicate.haystack,
    ),
    "set_comparison": (
        lambda query: set_comparison(
            column("a"),
            query,
            stalg.Expression.Subquery.SetComparison.REDUCTION_OP_ANY,
            stalg.Expression.Subquery.SetComparison.COMPARISON_OP_EQ,
        ),
        lambda expression: expression.subquery.set_comparison.right,
    ),
}


class TestSubqueries:
    """An ``Expression.Subquery`` embeds a bare Rel, so the inner query's declarations
    do not travel with it -- they have to be folded into the enclosing build instead.

    ``query`` may be an UnboundPlan, which resolves inside this build's scope and so
    numbers itself against the same collector, or an already-built Plan (a DataFrame's
    ``to_plan()`` handed back as a subquery), which arrives numbered against a table
    that is about to be discarded. The second used to lose them: its references were
    left naming anchors this plan does not declare, or -- where the numbering happened
    to overlap -- one of *this* build's declarations, which loads fine and computes
    something else.
    """

    @pytest.mark.parametrize("prebuilt", [False, True], ids=["unbound", "pre-built"])
    @pytest.mark.parametrize(
        "builder,inner_rel",
        list(_SUBQUERY_BUILDERS.values()),
        ids=list(_SUBQUERY_BUILDERS),
    )
    def test_inner_query_functions_are_declared(
        self, full_registry, builder, inner_rel, prebuilt
    ):
        inner = _inner_query()
        query = inner(full_registry) if prebuilt else inner
        before = query.SerializeToString(deterministic=True) if prebuilt else None
        out = project(
            read_named_table("t", NAMED_STRUCT),
            expressions=[
                # Resolved first, so ``gt`` is this build's anchor 1 and folding the
                # inner query in has to permute its pair rather than shift it.
                scalar_function(COMPARISON, "gt", [column("a"), column("b")]),
                builder(query),
            ],
        )(full_registry)

        declarations = _declarations(out)
        assert declarations == {1: "gt:any_any", 2: "add:i64_i64"}
        # Nothing anywhere in the plan names an anchor it does not declare.
        assert _resolved_functions(out) == {"gt:any_any", "add:i64_i64"}
        # By path, so the set above cannot be satisfied by references that resolve to
        # *some* declared function: the lifted condition still means gt(add(a, b), a).
        expressions = out.relations[-1].root.input.project.expressions
        condition = inner_rel(expressions[1]).filter.condition.scalar_function
        assert declarations[condition.function_reference] == "gt:any_any"
        add = condition.arguments[0].value.scalar_function
        assert declarations[add.function_reference] == "add:i64_i64"
        assert declarations[expressions[0].scalar_function.function_reference] == (
            "gt:any_any"
        )
        if prebuilt:
            # Folded on a copy: the caller still holds its plan, numbered its own way.
            assert query.SerializeToString(deterministic=True) == before

    def test_shared_subtree_lifted_into_a_subquery_is_renumbered_too(
        self, full_registry
    ):
        """A pre-built inner query carrying a shared subtree (what ``DataFrame.cache``
        produces) is inlined into the subquery Rel, because a ReferenceRel is
        plan-global and cannot resolve once lifted out of its plan. The references
        inside that subtree need re-deriving like any others, so the fold has to
        happen before the subtree is read -- inlining first would splice the inner
        plan's own numbering into a plan that no longer has that table.
        """
        inner = filter(
            reference(
                project(
                    read_named_table("u", NAMED_STRUCT),
                    expressions=[
                        column("a"),
                        column("b"),
                        scalar_function(ARITHMETIC, "add", [column("a"), column("b")]),
                    ],
                )
            ),
            expression=scalar_function(COMPARISON, "gt", [column("a"), column("b")]),
        )(full_registry)
        assert _declarations(inner) == {1: "add:i64_i64", 2: "gt:any_any"}

        out = project(
            read_named_table("t", NAMED_STRUCT),
            expressions=[
                scalar_function(COMPARISON, "gt", [column("a"), column("b")]),
                set_predicate(
                    inner, stalg.Expression.Subquery.SetPredicate.PREDICATE_OP_EXISTS
                ),
            ],
        )(full_registry)

        declarations = _declarations(out)
        assert declarations == {1: "gt:any_any", 2: "add:i64_i64"}
        assert _resolved_functions(out) == {"gt:any_any", "add:i64_i64"}
        tuples = (
            out.relations[-1]
            .root.input.project.expressions[1]
            .subquery.set_predicate.tuples
        )
        # The subtree is inlined where the ReferenceRel stood, carrying the `add` whose
        # reference the inner plan numbered 1 -- this build's `gt`.
        inlined = tuples.filter.input.project.expressions[-1].scalar_function
        assert declarations[inlined.function_reference] == "add:i64_i64"
        assert (
            declarations[tuples.filter.condition.scalar_function.function_reference]
            == "gt:any_any"
        )


class TestAlias:
    """``alias`` binds an expression and hands back a message with one output name
    changed, so it is the one expression builder whose result can be its *input*.

    Renaming in place would rewrite a column name in an ExtendedExpression the caller
    still holds, and returning the input's declarations would leak an anchor space the
    collector owns until the outermost resolver writes it.
    """

    @pytest.mark.parametrize(
        "permuting", [False, True], ids=["identity-remap", "permuting-remap"]
    )
    def test_nested_alias_declares_nothing_and_leaves_its_input_alone(
        self, full_registry, permuting
    ):
        expression = scalar_function(
            ARITHMETIC,
            "add",
            [
                column("a"),
                scalar_function(ARITHMETIC, "subtract", [column("a"), column("b")]),
            ],
        )(NAMED_STRUCT, full_registry)
        assert _declarations(expression) == {1: "subtract:i64_i64", 2: "add:i64_i64"}
        before = expression.SerializeToString(deterministic=True)

        with build_scope() as (collector, owns_scope):
            # This scope owns the build, so ``alias``'s own wrapper is nested.
            assert owns_scope
            if permuting:
                # Allocated in the opposite order, so the fold maps {1: 2, 2: 1}: a
                # remap the expression must not be seen carrying already.
                collector.function_reference(ARITHMETIC, "add:i64_i64")
                collector.function_reference(ARITHMETIC, "subtract:i64_i64")
            out = alias(expression, "renamed")(NAMED_STRUCT, full_registry)
            written = stplan.Plan()
            collector.write_into(written)

        assert out.referred_expr[0].output_names[0] == "renamed"
        assert not out.extensions and not out.extension_urns
        # The returned copy's references resolve through the collector's numbering
        # rather than the input's.
        declarations = _declarations(written)
        add = out.referred_expr[0].expression.scalar_function
        subtract = add.arguments[1].value.scalar_function
        assert declarations[add.function_reference] == "add:i64_i64"
        assert declarations[subtract.function_reference] == "subtract:i64_i64"
        # Untouched, whichever way the fold went: with an identity remap the fold
        # hands back the caller's own message, so the rename has to land on a copy.
        assert expression.SerializeToString(deterministic=True) == before

    def test_outermost_alias_still_declares_what_it_renames(self, full_registry):
        """Dropping the copied declarations is sound only because the collector holds
        the same information: reached directly, ``alias``'s scope is the outermost one
        and writes them itself."""
        out = alias(
            scalar_function(ARITHMETIC, "add", [column("a"), column("b")]), "renamed"
        )(NAMED_STRUCT, full_registry)

        assert _declarations(out) == {1: "add:i64_i64"}
        assert _resolved_functions(out) == {"add:i64_i64"}
        assert [(u.extension_urn_anchor, u.urn) for u in out.extension_urns] == [
            (1, ARITHMETIC)
        ]
        assert out.referred_expr[0].output_names[0] == "renamed"


class TestAmbiguousInput:
    """An input that declares two different functions at one anchor is rejected.

    Every reference to that anchor names both, and ``adopt``'s remap can send it to
    only one of them, so folding such a plan in would silently pick a function -- the
    ambiguity the collector exists to rule out.

    Parametrized over anchor 0 as well as an ordinary one: 0 is a valid
    anchor/reference (since Substrait v0.83.0), so it is policed like the rest
    rather than exempted from the check.
    """

    @pytest.mark.parametrize("anchor", [0, 5])
    def test_two_identities_at_one_anchor_are_rejected(self, anchor):
        carrier = _carrier(
            _declaration("gt:any_any", function_anchor=anchor, urn_reference=1),
            _declaration("lt:any_any", function_anchor=anchor, urn_reference=1),
            urns=[(1, COMPARISON)],
        )
        with pytest.raises(ValueError, match=f"function_anchor {anchor}"):
            ExtensionCollector().adopt(carrier)

    def test_two_bare_declarations_at_anchor_zero_are_rejected(self):
        """The shape a producer numbering from 0 would have to emit to be ambiguous:
        two bare ``extension_function { name: ... }`` in one carrier, both at anchor
        0, so its ``function_reference: 0`` names neither.

        pyarrow does not do this -- it numbers densely, so one carrier holds at most
        one declaration at 0 (checked against real pyarrow output in
        ``tests/integration/test_pyarrow_producer.py``) -- but this used to be
        accepted, with both declarations emitted at anchor 0 and every reference to
        them resolving to whichever the consumer found first.
        """
        carrier = _carrier(_declaration("add"), _declaration("subtract"))
        with pytest.raises(
            ValueError,
            match="function_anchor 0 is declared both as 'add' \\(no URN\\) "
            "and as 'subtract' \\(no URN\\)",
        ):
            ExtensionCollector().adopt(carrier)

    @pytest.mark.parametrize("anchor", [0, 5])
    def test_one_identity_declared_twice_is_accepted(self, anchor):
        """Redundant rather than ambiguous: both declarations mean the same function,
        so a reference to the anchor still resolves to exactly one thing."""
        carrier = _carrier(
            _declaration("gt:any_any", function_anchor=anchor, urn_reference=1),
            _declaration("gt:any_any", function_anchor=anchor, urn_reference=1),
            urns=[(1, COMPARISON)],
        )
        assert ExtensionCollector().adopt(carrier) == {anchor: 1}

    @pytest.mark.parametrize("anchor", [0, 5])
    def test_one_anchor_meaning_two_things_in_separate_inputs_is_accepted(self, anchor):
        """Anchors are plan-local, so two independently built inputs meeting at a
        multi-input relation number theirs separately and are remapped separately.

        At anchor 0 this is the pyarrow case: each serialized expression is its own
        anchor space, so two of them declaring different functions at 0 is ordinary
        input that must come out as two declarations.
        """
        collector = ExtensionCollector()
        gt = _carrier(
            _declaration("gt:any_any", function_anchor=anchor, urn_reference=1),
            urns=[(1, COMPARISON)],
        )
        lt = _carrier(
            _declaration("lt:any_any", function_anchor=anchor, urn_reference=1),
            urns=[(1, COMPARISON)],
        )
        assert collector.adopt(gt) == {anchor: 1}
        assert collector.adopt(lt) == {anchor: 2}

    def test_two_bare_declarations_at_anchor_zero_in_separate_inputs_are_renumbered(
        self,
    ):
        """The same as above with no URN to resolve, which is the shape pyarrow emits.

        Kept separate because the URN is what made the case above uninteresting to the
        numbering this replaced: it treated a declaration as unrewritable only when
        anchor 0 came *with* an unresolvable URN, so a carrier naming a real URN was
        renumbered normally either way. A bare declaration was the one that got frozen
        at 0 -- so two of them, arriving from two separately serialized inputs, both
        stayed at 0 and every reference to it resolved to whichever the consumer found
        first. That is the pyarrow collision, and this is its pyarrow-free guard:
        ``tests/integration`` covers it through the real bytes, but that suite can be
        switched off.
        """
        collector = ExtensionCollector()
        assert collector.adopt(_carrier(_declaration("add"))) == {0: 1}
        assert collector.adopt(_carrier(_declaration("multiply"))) == {0: 2}

        out = stplan.Plan()
        collector.write_into(out)
        assert _declarations(out) == {1: "add", 2: "multiply"}


class TestNoPerLevelMerging:
    """The collector accumulates declarations once per build rather than having each
    verb re-merge its children's, which is the extension half of #207.

    White-box on purpose: the point is that the builders no longer reach for the
    merge helpers at all, so a refactor reintroducing per-level merging trips this.
    """

    @pytest.fixture
    def merge_helpers_are_fatal(self, monkeypatch):
        """Make every legacy merge helper explode, wherever a builder could reach it.

        Patched both in ``substrait.utils`` and in each builder module's own
        namespace: ``from substrait.utils import merge_...`` binds a module-local name
        at import time, which a patch of ``substrait.utils`` alone would never reach.
        Both builder modules are covered -- either could reintroduce the import.
        """
        import substrait.builders.extended_expression as builders_expression
        import substrait.builders.plan as builders_plan
        import substrait.utils

        def fail(*args, **kwargs):
            raise AssertionError(
                "builders re-merged extension declarations; the collector owns them"
            )

        names = (
            "merge_extension_declarations",
            "merge_extension_urns",
            "merge_extensions_into",
        )
        for module in (substrait.utils, builders_plan, builders_expression):
            for name in names:
                if hasattr(module, name):
                    monkeypatch.setattr(module, name, fail)

    def test_building_a_chain_never_re_merges_declarations(
        self, full_registry, merge_helpers_are_fatal
    ):
        functions = ["add", "subtract", "multiply", "divide"]
        plan = read_named_table("t", NAMED_STRUCT)
        for i in range(40):
            plan = project(
                plan,
                expressions=[
                    scalar_function(
                        ARITHMETIC,
                        functions[i % len(functions)],
                        [column("a"), column("b")],
                        alias=f"c{i}",
                    )
                ],
            )
        out = plan(full_registry)

        # One declaration per distinct function, however long the chain.
        assert len(out.extensions) == len(functions)
        assert sorted(_declarations(out)) == [1, 2, 3, 4]

    def test_building_an_expression_never_re_merges_declarations(
        self, full_registry, merge_helpers_are_fatal
    ):
        """An ExtendedExpression built on its own goes through the same collector, so
        the expression builders have no more use for the helpers than the plan ones.
        """
        expression = scalar_function(
            ARITHMETIC,
            "add",
            [
                column("a"),
                scalar_function(ARITHMETIC, "subtract", [column("a"), column("b")]),
            ],
        )(NAMED_STRUCT, full_registry)

        assert _declarations(expression) == {1: "subtract:i64_i64", 2: "add:i64_i64"}


class TestAnchorsAreNotARegistryConcern:
    """The registry hands out no anchors, so the two members that implied it does are
    gone rather than deprecated: ``lookup_urn`` returned a URN anchor and
    ``FunctionEntry.anchor`` a function anchor, and neither is knowable from a catalog
    (#236). Pinned as absent so a refactor cannot quietly bring them back.
    """

    def test_the_registry_has_no_lookup_urn(self, full_registry):
        assert not hasattr(ExtensionRegistry, "lookup_urn")
        assert not hasattr(full_registry, "lookup_urn")

    def test_a_function_entry_has_no_anchor(self, full_registry):
        entry, _ = full_registry.lookup_function(ARITHMETIC, "add", [I64, I64])
        assert not hasattr(type(entry), "anchor")
        assert not hasattr(entry, "anchor")
        # What replaces it: the identity a declaration can be re-derived from.
        assert entry.urn == ARITHMETIC
        assert str(entry) == "add:i64_i64"

    def test_has_urn_replaces_lookup_urn(self, full_registry):
        assert full_registry.has_urn(ARITHMETIC)
        assert not full_registry.has_urn("extension:acme:nope")
        assert ARITHMETIC in full_registry.urns()
