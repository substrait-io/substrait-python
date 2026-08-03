import pytest
import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.extensions.extensions_pb2 as ste
import substrait.plan_pb2 as stplan
import substrait.type_pb2 as stt

from substrait.utils import (
    iter_plan_rels,
    merge_extension_declarations,
    merge_extension_urns,
    merge_extensions_into,
    rel_anchor_of,
    remap_function_references,
    to_id_based_outer_references,
    type_num_names,
)


def test_type_num_names_flat_struct():
    assert (
        type_num_names(
            stt.Type(
                struct=stt.Type.Struct(
                    types=[
                        stt.Type(i64=stt.Type.I64()),
                        stt.Type(string=stt.Type.String()),
                        stt.Type(fp32=stt.Type.FP32()),
                    ]
                )
            )
        )
        == 4
    )


def test_type_num_names_nested_struct():
    assert (
        type_num_names(
            stt.Type(
                struct=stt.Type.Struct(
                    types=[
                        stt.Type(i64=stt.Type.I64()),
                        stt.Type(
                            struct=stt.Type.Struct(
                                types=[
                                    stt.Type(i64=stt.Type.I64()),
                                    stt.Type(fp32=stt.Type.FP32()),
                                ]
                            )
                        ),
                        stt.Type(fp32=stt.Type.FP32()),
                    ]
                )
            )
        )
        == 6
    )


def test_type_num_names_flat_list():
    assert (
        type_num_names(
            stt.Type(
                struct=stt.Type.Struct(
                    types=[
                        stt.Type(i64=stt.Type.I64()),
                        stt.Type(list=stt.Type.List(type=stt.Type(i64=stt.Type.I64()))),
                        stt.Type(fp32=stt.Type.FP32()),
                    ]
                )
            )
        )
        == 4
    )


def test_type_num_names_nested_list():
    assert (
        type_num_names(
            stt.Type(
                struct=stt.Type.Struct(
                    types=[
                        stt.Type(i64=stt.Type.I64()),
                        stt.Type(
                            list=stt.Type.List(
                                type=stt.Type(
                                    struct=stt.Type.Struct(
                                        types=[
                                            stt.Type(i64=stt.Type.I64()),
                                            stt.Type(fp32=stt.Type.FP32()),
                                        ]
                                    )
                                )
                            )
                        ),
                        stt.Type(fp32=stt.Type.FP32()),
                    ]
                )
            )
        )
        == 6
    )


def test_merge_extension_urns_deduplicates():
    """Test that merging extension URNs deduplicates correctly."""
    # Create duplicate URN extensions
    urn1 = ste.SimpleExtensionURN(extension_urn_anchor=1, urn="extension:example:test")
    urn2 = ste.SimpleExtensionURN(extension_urn_anchor=1, urn="extension:example:test")
    urn3 = ste.SimpleExtensionURN(extension_urn_anchor=2, urn="extension:example:other")

    merged_urns = merge_extension_urns([urn1], [urn2, urn3])

    assert len(merged_urns) == 2
    assert merged_urns[0].urn == "extension:example:test"
    assert merged_urns[1].urn == "extension:example:other"


def _extension_function(urn_reference, function_anchor, name):
    return ste.SimpleExtensionDeclaration(
        extension_function=ste.SimpleExtensionDeclaration.ExtensionFunction(
            extension_urn_reference=urn_reference,
            function_anchor=function_anchor,
            name=name,
        )
    )


def test_merge_extensions_into_appends_new_and_dedupes_on_identity():
    """merge_extensions_into keeps target's entries and appends only novel ones,
    keying on the same anchor/name identity as the merge_* helpers."""
    target = stee.ExtendedExpression(
        extension_urns=[ste.SimpleExtensionURN(extension_urn_anchor=1, urn="A")],
        extensions=[_extension_function(1, 10, "f:i8")],
    )
    source = stee.ExtendedExpression(
        extension_urns=[
            ste.SimpleExtensionURN(extension_urn_anchor=1, urn="A"),  # dup URN string
            ste.SimpleExtensionURN(extension_urn_anchor=2, urn="B"),
        ],
        extensions=[
            # Same (urn reference, name) as target's -- a duplicate by identity even
            # though the function anchor differs, so it must not be appended (this is
            # what distinguishes identity dedup from strict proto equality).
            _extension_function(1, 99, "f:i8"),
            _extension_function(2, 11, "g:i8"),
        ],
    )

    merge_extensions_into(target, source)

    assert [u.urn for u in target.extension_urns] == ["A", "B"]
    assert [d.extension_function.name for d in target.extensions] == ["f:i8", "g:i8"]
    # target's original declaration is kept; source's identity-duplicate is dropped.
    assert target.extensions[0].extension_function.function_anchor == 10


def test_merge_extensions_into_merges_multiple_sources():
    target = stee.ExtendedExpression()
    source1 = stee.ExtendedExpression(
        extension_urns=[ste.SimpleExtensionURN(extension_urn_anchor=1, urn="A")],
        extensions=[_extension_function(1, 10, "f:i8")],
    )
    source2 = stee.ExtendedExpression(
        extension_urns=[ste.SimpleExtensionURN(extension_urn_anchor=2, urn="B")],
        extensions=[_extension_function(2, 11, "g:i8")],
    )

    merge_extensions_into(target, source1, source2)

    assert [u.urn for u in target.extension_urns] == ["A", "B"]
    assert [d.extension_function.name for d in target.extensions] == ["f:i8", "g:i8"]


def test_merge_extension_declarations_rejects_non_function_mapping():
    """Only ``extension_function`` declarations are supported so far; a type /
    type-variation declaration raises an informative NotImplementedError naming
    the unsupported mapping type."""
    declaration = ste.SimpleExtensionDeclaration(
        extension_type=ste.SimpleExtensionDeclaration.ExtensionType()
    )

    with pytest.raises(NotImplementedError, match="extension_type"):
        merge_extension_declarations([declaration])


# --- remap_function_references -------------------------------------------------
#
# Every proto field that holds a function reference must be rewritten, including
# the two this library never emits itself but a plan built elsewhere may carry.


def test_remap_function_references_rewrites_every_reference_field():
    rel = stalg.Rel(
        project=stalg.ProjectRel(
            expressions=[
                stalg.Expression(
                    scalar_function=stalg.Expression.ScalarFunction(
                        function_reference=7
                    )
                ),
                stalg.Expression(
                    window_function=stalg.Expression.WindowFunction(
                        function_reference=7,
                        sorts=[stalg.SortField(comparison_function_reference=8)],
                    )
                ),
            ]
        )
    )
    out = remap_function_references(rel, {7: 1, 8: 2})

    expressions = out.project.expressions
    assert expressions[0].scalar_function.function_reference == 1
    assert expressions[1].window_function.function_reference == 1
    assert expressions[1].window_function.sorts[0].comparison_function_reference == 2


def test_remap_function_references_rewrites_aggregate_and_window_rels():
    aggregate = stalg.Rel(
        aggregate=stalg.AggregateRel(
            measures=[
                stalg.AggregateRel.Measure(
                    measure=stalg.AggregateFunction(function_reference=8)
                )
            ]
        )
    )
    window = stalg.Rel(
        window=stalg.ConsistentPartitionWindowRel(
            window_functions=[
                stalg.ConsistentPartitionWindowRel.WindowRelFunction(
                    function_reference=7
                )
            ]
        )
    )
    remap = {7: 1, 8: 2}

    assert (
        remap_function_references(aggregate, remap)
        .aggregate.measures[0]
        .measure.function_reference
        == 2
    )
    assert (
        remap_function_references(window, remap)
        .window.window_functions[0]
        .function_reference
        == 1
    )


def test_remap_function_references_rewrites_join_key_comparison():
    """``custom_function_reference`` is never emitted by this library, but a plan
    built elsewhere may use it, so the walk must still cover it."""
    key = stalg.ComparisonJoinKey(
        comparison=stalg.ComparisonJoinKey.ComparisonType(custom_function_reference=8)
    )
    assert (
        remap_function_references(key, {8: 2}).comparison.custom_function_reference == 2
    )


def test_remap_function_references_rewrites_a_reference_of_zero():
    """0 is a valid anchor/reference -- the protos have said so on ``function_anchor``
    since Substrait v0.83.0 ("0 is a valid anchor/reference, but prefer non-zero
    values for ergonomics") -- so an incoming plan may name its
    first function with ``function_reference: 0``.

    proto3 leaves such a field out of ``ListFields()``, so a set-fields walk cannot
    see it, let alone rewrite it: the reference would silently survive into a plan
    whose numbering puts something else at 0. All four fields that hold a reference
    without presence must be rewritten.
    """
    remap = {0: 5}
    rel = stalg.Rel(
        project=stalg.ProjectRel(
            expressions=[
                stalg.Expression(
                    scalar_function=stalg.Expression.ScalarFunction(
                        function_reference=0
                    )
                ),
                stalg.Expression(
                    window_function=stalg.Expression.WindowFunction(
                        function_reference=0
                    )
                ),
            ]
        )
    )
    aggregate = stalg.Rel(
        aggregate=stalg.AggregateRel(
            measures=[
                stalg.AggregateRel.Measure(
                    measure=stalg.AggregateFunction(function_reference=0)
                )
            ]
        )
    )
    window = stalg.Rel(
        window=stalg.ConsistentPartitionWindowRel(
            window_functions=[
                stalg.ConsistentPartitionWindowRel.WindowRelFunction(
                    function_reference=0
                )
            ]
        )
    )

    out = remap_function_references(rel, remap)
    assert out.project.expressions[0].scalar_function.function_reference == 5
    assert out.project.expressions[1].window_function.function_reference == 5
    assert (
        remap_function_references(aggregate, remap)
        .aggregate.measures[0]
        .measure.function_reference
        == 5
    )
    assert (
        remap_function_references(window, remap)
        .window.window_functions[0]
        .function_reference
        == 5
    )


def test_remap_function_references_rewrites_zero_in_the_presence_bearing_fields():
    """The two reference fields that *do* have presence still carry 0 when set to
    it, so selecting one must be enough to have it rewritten."""
    remap = {0: 5}
    sort = stalg.SortField(comparison_function_reference=0)
    key = stalg.ComparisonJoinKey(
        comparison=stalg.ComparisonJoinKey.ComparisonType(custom_function_reference=0)
    )

    assert remap_function_references(sort, remap).comparison_function_reference == 5
    assert (
        remap_function_references(key, remap).comparison.custom_function_reference == 5
    )


@pytest.mark.parametrize(
    "direction",
    [
        stalg.SortField.SORT_DIRECTION_ASC_NULLS_FIRST,
        # The trap: a zero-valued oneof member is as invisible to ListFields() as a
        # reference of 0, so a walk that gates on "is this field set" the wrong way
        # cannot tell the two apart.
        stalg.SortField.SORT_DIRECTION_UNSPECIFIED,
    ],
    ids=["asc", "unspecified"],
)
def test_remap_function_references_does_not_invent_a_sort_comparison(direction):
    """``comparison_function_reference`` shares oneof ``sort_kind`` with
    ``direction``, so a remap that knows the key 0 must not write it blind: a field
    sorted by direction would come out sorted by a comparison function instead.
    """
    sort = stalg.SortField(
        expr=stalg.Expression(literal=stalg.Expression.Literal(i64=1)),
        direction=direction,
    )
    before = sort.SerializeToString(deterministic=True)

    out = remap_function_references(sort, {0: 5})

    assert out.WhichOneof("sort_kind") == "direction"
    assert out.SerializeToString(deterministic=True) == before


def test_remap_function_references_does_not_invent_a_sort_kind():
    """A SortField with no ``sort_kind`` at all keeps none: the oneof gate reads
    which member is selected, not whether the field could hold a reference."""
    sort = stalg.SortField(
        expr=stalg.Expression(literal=stalg.Expression.Literal(i64=1))
    )
    out = remap_function_references(sort, {0: 5})
    assert out.WhichOneof("sort_kind") is None


@pytest.mark.parametrize(
    "simple",
    [
        stalg.ComparisonJoinKey.SIMPLE_COMPARISON_TYPE_EQ,
        stalg.ComparisonJoinKey.SIMPLE_COMPARISON_TYPE_UNSPECIFIED,
    ],
    ids=["eq", "unspecified"],
)
def test_remap_function_references_does_not_invent_a_join_key_comparison(simple):
    """``custom_function_reference`` shares oneof ``inner_type`` with ``simple``, so
    the same gate applies: an equi-join key must not come out comparing by function.
    """
    key = stalg.ComparisonJoinKey(
        comparison=stalg.ComparisonJoinKey.ComparisonType(simple=simple)
    )
    before = key.SerializeToString(deterministic=True)

    out = remap_function_references(key, {0: 5})

    assert out.comparison.WhichOneof("inner_type") == "simple"
    assert out.SerializeToString(deterministic=True) == before


def test_remap_function_references_does_not_materialize_an_unset_function():
    """Only *set* submessages are descended into. An ``AggregateRel.Measure`` with no
    ``measure`` holds no reference to rewrite, and descending anyway would bring the
    ``AggregateFunction`` into existence -- inventing a measure calling function 5 --
    because its ``function_reference`` reads back as the 0 the remap knows.
    """
    rel = stalg.Rel(
        aggregate=stalg.AggregateRel(
            measures=[
                stalg.AggregateRel.Measure(
                    filter=stalg.Expression(
                        literal=stalg.Expression.Literal(boolean=True)
                    )
                )
            ]
        )
    )
    before = rel.SerializeToString(deterministic=True)

    out = remap_function_references(rel, {0: 5})

    assert not out.aggregate.measures[0].HasField("measure")
    assert out.SerializeToString(deterministic=True) == before


def test_remap_function_references_leaves_input_alone():
    rel = stalg.Rel(
        project=stalg.ProjectRel(
            expressions=[
                stalg.Expression(
                    scalar_function=stalg.Expression.ScalarFunction(
                        function_reference=7
                    )
                )
            ]
        )
    )
    remap_function_references(rel, {7: 1})
    assert rel.project.expressions[0].scalar_function.function_reference == 7


def test_remap_function_references_empty_remap_is_the_same_object():
    """The no-op case is the common one -- callers rely on it not copying."""
    rel = stalg.Rel(read=stalg.ReadRel())
    assert remap_function_references(rel, {}) is rel


def test_remap_function_references_passes_through_unmapped():
    expression = stalg.Expression(
        scalar_function=stalg.Expression.ScalarFunction(function_reference=99)
    )
    out = remap_function_references(expression, {7: 1})
    assert out.scalar_function.function_reference == 99


# --- to_id_based_outer_references ----------------------------------------------
#
# Compact hand-built plans exercising the steps_out -> rel_reference conversion.
# A filter condition here is a bare (outer) reference rather than a realistic
# boolean predicate -- the converter only walks expressions to find and rewrite
# OuterReferences, so the surrounding operator shape is what matters.


def _read(name: str, ncols: int = 1) -> stalg.Rel:
    return stalg.Rel(
        read=stalg.ReadRel(
            base_schema=stt.NamedStruct(
                names=[f"c{i}" for i in range(ncols)],
                struct=stt.Type.Struct(
                    types=[stt.Type(i64=stt.Type.I64()) for _ in range(ncols)]
                ),
            ),
            named_table=stalg.ReadRel.NamedTable(names=[name]),
        )
    )


def _outer(steps_out: int, field: int = 0) -> stalg.Expression:
    return stalg.Expression(
        selection=stalg.Expression.FieldReference(
            outer_reference=stalg.Expression.FieldReference.OuterReference(
                steps_out=steps_out
            ),
            direct_reference=stalg.Expression.ReferenceSegment(
                struct_field=stalg.Expression.ReferenceSegment.StructField(field=field)
            ),
        )
    )


def _exists(inner: stalg.Rel) -> stalg.Expression:
    return stalg.Expression(
        subquery=stalg.Expression.Subquery(
            set_predicate=stalg.Expression.Subquery.SetPredicate(
                predicate_op=stalg.Expression.Subquery.SetPredicate.PREDICATE_OP_EXISTS,
                tuples=inner,
            )
        )
    )


def _filter(input: stalg.Rel, condition: stalg.Expression) -> stalg.Rel:
    return stalg.Rel(filter=stalg.FilterRel(input=input, condition=condition))


def _plan(root_input: stalg.Rel, *subtrees: stalg.Rel) -> stplan.Plan:
    relations = [stplan.PlanRel(rel=s) for s in subtrees]
    relations.append(stplan.PlanRel(root=stalg.RelRoot(input=root_input, names=["c0"])))
    return stplan.Plan(relations=relations)


def _outer_refs(plan: stplan.Plan):
    """Every OuterReference in a plan (across subquery-embedded relations)."""
    return [
        rel.filter.condition
        for rel in iter_plan_rels(plan)
        if rel.WhichOneof("rel_type") == "filter"
        and rel.filter.condition.WhichOneof("rex_type") == "selection"
        and rel.filter.condition.selection.WhichOneof("root_type") == "outer_reference"
    ]


def test_convert_correlated_exists_stamps_anchor_and_rewrites():
    plan = _plan(_filter(_read("o"), _exists(_filter(_read("i"), _outer(1)))))
    out = to_id_based_outer_references(plan)

    binding = out.relations[-1].root.input.filter.input  # the outer read
    assert rel_anchor_of(binding) == 1

    ref = out.relations[
        -1
    ].root.input.filter.condition.subquery.set_predicate.tuples.filter.condition.selection.outer_reference
    assert ref.WhichOneof("outer_reference_type") == "rel_reference"
    assert ref.rel_reference == 1
    # The input plan is untouched (conversion works on a copy).
    assert rel_anchor_of(plan.relations[-1].root.input.filter.input) is None


def test_convert_dedup_same_scope_shares_one_anchor():
    # Two correlated columns from the same enclosing scope share a single anchor.
    inner = _filter(
        _read("i"),
        stalg.Expression(
            nested=stalg.Expression.Nested(
                struct=stalg.Expression.Nested.Struct(
                    fields=[_outer(1, 0), _outer(1, 1)]
                )
            )
        ),
    )
    plan = _plan(_filter(_read("o", ncols=2), _exists(inner)))
    out = to_id_based_outer_references(plan)

    anchors = {a for r in iter_plan_rels(out) if (a := rel_anchor_of(r))}
    assert anchors == {1}
    refs = out.relations[
        -1
    ].root.input.filter.condition.subquery.set_predicate.tuples.filter.condition.nested.struct.fields
    assert [f.selection.outer_reference.rel_reference for f in refs] == [1, 1]


def test_convert_distinct_scopes_get_distinct_anchors():
    # An inner subquery referencing two different enclosing scopes (steps_out 1 and
    # 2) anchors each binding relation separately.
    inner = _filter(
        _read("i"),
        stalg.Expression(
            nested=stalg.Expression.Nested(
                struct=stalg.Expression.Nested.Struct(fields=[_outer(1), _outer(2)])
            )
        ),
    )
    mid = _filter(_read("m"), _exists(inner))
    plan = _plan(_filter(_read("o"), _exists(mid)))
    out = to_id_based_outer_references(plan)

    root = out.relations[-1].root.input
    outer_read = root.filter.input
    mid_read = root.filter.condition.subquery.set_predicate.tuples.filter.input
    assert rel_anchor_of(mid_read) != rel_anchor_of(outer_read)

    fields = root.filter.condition.subquery.set_predicate.tuples.filter.condition.subquery.set_predicate.tuples.filter.condition.nested.struct.fields
    assert fields[0].selection.outer_reference.rel_reference == rel_anchor_of(mid_read)
    assert fields[1].selection.outer_reference.rel_reference == rel_anchor_of(
        outer_read
    )


def test_convert_preexisting_anchor_reused_and_counter_continues():
    # An anchor already present in the plan is left alone; freshly allocated
    # anchors continue past the maximum existing one.
    marked = _read("i")
    marked.read.common.rel_anchor = 5
    plan = _plan(_filter(_read("o"), _exists(_filter(marked, _outer(1)))))
    out = to_id_based_outer_references(plan)

    assert rel_anchor_of(out.relations[-1].root.input.filter.input) == 6


def _join(
    left: stalg.Rel,
    right: stalg.Rel,
    *,
    type=stalg.JoinRel.JOIN_TYPE_INNER,
    expression: stalg.Expression = None,
    post_join_filter: stalg.Expression = None,
) -> stalg.Rel:
    return stalg.Rel(
        join=stalg.JoinRel(
            left=left,
            right=right,
            type=type,
            expression=expression,
            post_join_filter=post_join_filter,
        )
    )


def test_convert_reference_rel_binding_anchors_the_shared_subtree():
    # A correlation whose enclosing host input is a ReferenceRel (a cache()d frame)
    # has no RelCommon on the reference itself; the anchor lands on the shared
    # subtree it points at, whose output is exactly the reference's. This is the
    # DAG case that offset-based steps_out cannot address unambiguously.
    ref_rel = stalg.Rel(reference=stalg.ReferenceRel(subtree_ordinal=0))
    plan = _plan(
        _filter(ref_rel, _exists(_filter(_read("i"), _outer(1)))),
        _read("s"),  # subtree at ordinal 0
    )
    out = to_id_based_outer_references(plan)

    subtree = out.relations[0].rel
    assert rel_anchor_of(subtree) == 1
    # The ReferenceRel binding is left as-is (it carries no RelCommon).
    assert rel_anchor_of(out.relations[-1].root.input.filter.input) is None
    ref = out.relations[
        -1
    ].root.input.filter.condition.subquery.set_predicate.tuples.filter.condition.selection.outer_reference
    assert ref.WhichOneof("outer_reference_type") == "rel_reference"
    assert ref.rel_reference == 1


def test_convert_multi_input_join_condition_anchors_the_join():
    # A correlation into a (non-reducing) join's condition resolves against the
    # combined left+right row, which equals the join's own output -- so the join
    # relation is anchored and the reference names it.
    join = _join(
        _read("l"),
        _read("r"),
        expression=_exists(_filter(_read("i"), _outer(1))),
    )
    out = to_id_based_outer_references(_plan(join))

    out_join = out.relations[-1].root.input
    assert rel_anchor_of(out_join) == 1
    ref = out_join.join.expression.subquery.set_predicate.tuples.filter.condition.selection.outer_reference
    assert ref.WhichOneof("outer_reference_type") == "rel_reference"
    assert ref.rel_reference == 1


def test_convert_post_join_filter_anchors_the_join():
    # A correlation in a join's post_join_filter resolves against the join output,
    # i.e. the join itself -- anchored the same way.
    join = _join(
        _read("l"),
        _read("r"),
        post_join_filter=_exists(_filter(_read("i"), _outer(1))),
    )
    out = to_id_based_outer_references(_plan(join))

    out_join = out.relations[-1].root.input
    assert rel_anchor_of(out_join) == 1
    ref = out_join.join.post_join_filter.subquery.set_predicate.tuples.filter.condition.selection.outer_reference
    assert ref.rel_reference == 1


def test_convert_reducing_join_condition_left_as_steps_out():
    # A reducing join (semi/anti) emits only one side, so its output row differs
    # from the combined condition scope the reference sees. No relation carries
    # that row, so the reference stays offset-based (still spec-valid) rather than
    # being mis-anchored to the join's narrower output.
    join = _join(
        _read("l"),
        _read("r"),
        type=stalg.JoinRel.JOIN_TYPE_LEFT_SEMI,
        expression=_exists(_filter(_read("i"), _outer(1))),
    )
    out = to_id_based_outer_references(_plan(join))

    out_join = out.relations[-1].root.input
    assert rel_anchor_of(out_join) is None
    ref = out_join.join.expression.subquery.set_predicate.tuples.filter.condition.selection.outer_reference
    assert ref.WhichOneof("outer_reference_type") == "steps_out"
    assert ref.steps_out == 1


def _lateral_join(
    left: stalg.Rel,
    right: stalg.Rel,
    *,
    rel_anchor: int,
    type=stalg.JoinRel.JOIN_TYPE_INNER,
) -> stalg.Rel:
    return stalg.Rel(
        lateral_join=stalg.LateralJoinRel(
            common=stalg.RelCommon(rel_anchor=rel_anchor),
            left=left,
            right=right,
            type=type,
        )
    )


def test_convert_correlation_above_lateral_join_left_as_steps_out():
    # A LateralJoinRel's rel_anchor is reserved (per the Substrait spec) for its
    # right input's reference to the current *left* row, so it does not name the
    # join's output row. A correlation stacked above the lateral join (into its
    # output) must not reuse that anchor -- doing so would alias the left-row anchor
    # and corrupt any reference beyond the left columns. Such a reference is left
    # offset-based (still spec-valid), like a reducing join's condition.
    lj = _lateral_join(_read("l", ncols=2), _read("r", ncols=2), rel_anchor=5)
    plan = _plan(_filter(lj, _exists(_filter(_read("i"), _outer(1, field=3)))))
    out = to_id_based_outer_references(plan)

    top = out.relations[-1].root.input
    ref = top.filter.condition.subquery.set_predicate.tuples.filter.condition.selection.outer_reference
    assert ref.WhichOneof("outer_reference_type") == "steps_out"
    assert ref.steps_out == 1
    # The lateral join keeps its own (left-row) anchor; no new anchor is minted for
    # the un-rewritable correlation.
    assert rel_anchor_of(top.filter.input) == 5
    assert {a for r in iter_plan_rels(out) if (a := rel_anchor_of(r))} == {5}


def test_convert_binding_without_rel_common_raises():
    # A binding relation that carries no RelCommon at all (an UpdateRel) cannot hold
    # an anchor. No correlated-subquery shape produces this, but the converter
    # guards it rather than silently dropping the reference.
    update = stalg.Rel(
        update=stalg.UpdateRel(
            named_table=stalg.NamedTable(names=["t"]),
        )
    )
    plan = _plan(_filter(update, _exists(_filter(_read("i"), _outer(1)))))
    with pytest.raises(Exception, match="no RelCommon"):
        to_id_based_outer_references(plan)


def test_convert_noncorrelated_plan_unchanged():
    plan = _plan(
        _filter(_read("o"), stalg.Expression(literal=stalg.Expression.Literal(i64=1)))
    )
    assert to_id_based_outer_references(plan) == plan


def test_convert_is_idempotent():
    plan = _plan(_filter(_read("o"), _exists(_filter(_read("i"), _outer(1)))))
    once = to_id_based_outer_references(plan)
    twice = to_id_based_outer_references(once)
    assert twice == once
