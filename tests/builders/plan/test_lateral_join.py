import pytest
import substrait.algebra_pb2 as stalg

from substrait.builders.extended_expression import (
    column,
    fresh_rel_anchors,
    literal,
)
from substrait.builders.plan import lateral_join, project, read_named_table
from substrait.builders.type import boolean, i64, named_struct, string, struct
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema

registry = ExtensionRegistry(load_default_extensions=False)

left_ns = named_struct(
    ["k", "v"], struct([i64(nullable=False), string()], nullable=False)
)
right_ns = named_struct(["w"], struct([i64(nullable=False)], nullable=False))


def _left():
    return read_named_table("left", left_ns)


def _right():
    return read_named_table("right", right_ns)


def _correlated_right(left):
    # A right input that projects the current left row's first column ("k") via
    # the left handle, on top of its own column.
    return project(_right(), expressions=[left.column("k")])


def test_lateral_join_optional_args_are_keyword_only():
    with pytest.raises(TypeError):
        lateral_join(
            _left(),
            _correlated_right,
            stalg.JoinRel.JOIN_TYPE_INNER,
            None,  # would have bound to expression positionally
        )


def test_lateral_join_sets_anchor_matching_right_reference():
    with fresh_rel_anchors():
        plan = lateral_join(
            _left(), _correlated_right, type=stalg.JoinRel.JOIN_TYPE_INNER
        )(registry)

    rel = plan.relations[-1].root.input
    assert rel.WhichOneof("rel_type") == "lateral_join"
    lj = rel.lateral_join
    # The join assigns a rel_anchor and the right's handle reference names it.
    assert lj.common.HasField("rel_anchor")
    ref = lj.right.project.expressions[0].selection
    assert ref.WhichOneof("root_type") == "outer_reference"
    assert ref.outer_reference.WhichOneof("outer_reference_type") == "rel_reference"
    assert ref.outer_reference.rel_reference == lj.common.rel_anchor
    # "k" is the left's first column.
    assert ref.direct_reference.struct_field.field == 0


def test_lateral_join_inner_output_and_inference():
    with fresh_rel_anchors():
        plan = lateral_join(
            _left(), _correlated_right, type=stalg.JoinRel.JOIN_TYPE_INNER
        )(registry)

    # Output names: left + right (right = its own column + the correlated one).
    assert list(plan.relations[-1].root.names) == ["k", "v", "w", "k"]
    ns = infer_plan_schema(plan, registry=registry)
    assert [t.WhichOneof("kind") for t in ns.struct.types] == [
        "i64",  # left.k
        "string",  # left.v
        "i64",  # right.w
        "i64",  # right's correlated reference to left.k
    ]


def test_lateral_join_left_semi_drops_right():
    with fresh_rel_anchors():
        plan = lateral_join(
            _left(), _correlated_right, type=stalg.JoinRel.JOIN_TYPE_LEFT_SEMI
        )(registry)

    assert list(plan.relations[-1].root.names) == ["k", "v"]
    ns = infer_plan_schema(plan, registry=registry)
    assert [t.WhichOneof("kind") for t in ns.struct.types] == ["i64", "string"]


def test_lateral_join_left_mark_appends_boolean():
    with fresh_rel_anchors():
        plan = lateral_join(
            _left(), _correlated_right, type=stalg.JoinRel.JOIN_TYPE_LEFT_MARK
        )(registry)

    ns = infer_plan_schema(plan, registry=registry)
    assert list(ns.names)[-1] == "mark"
    assert ns.struct.types[-1].WhichOneof("kind") == "bool"
    assert len(ns.names) == len(ns.struct.types)


def test_lateral_join_nested_handles_reference_distinct_anchors():
    # An inner lateral join can reference the outer left via its captured handle,
    # with no depth bookkeeping; each join gets a distinct anchor.
    def inner_of(outer):
        def middle(_middle_left):
            return project(_right(), expressions=[outer.column("k")])

        return lateral_join(_right(), middle, type=stalg.JoinRel.JOIN_TYPE_INNER)

    with fresh_rel_anchors():
        plan = lateral_join(_left(), inner_of, type=stalg.JoinRel.JOIN_TYPE_INNER)(
            registry
        )

    outer = plan.relations[-1].root.input.lateral_join
    inner = outer.right.lateral_join
    assert outer.common.rel_anchor != inner.common.rel_anchor
    # The innermost projection references the OUTER join's anchor.
    ref = inner.right.project.expressions[0].selection
    assert ref.outer_reference.rel_reference == outer.common.rel_anchor
    infer_plan_schema(plan, registry=registry)


def _uncorrelated_right(_left):
    # A right input that ignores the left row (no correlation), for exercising
    # the match condition / post-filter arguments in isolation.
    return _right()


def test_lateral_join_expression_condition():
    # An optional match condition binds against the combined left+right inputs and
    # is emitted on LateralJoinRel.expression.
    with fresh_rel_anchors():
        plan = lateral_join(
            _left(),
            _uncorrelated_right,
            type=stalg.JoinRel.JOIN_TYPE_INNER,
            expression=literal(True, boolean()),
        )(registry)

    lj = plan.relations[-1].root.input.lateral_join
    assert lj.HasField("expression")
    assert lj.expression.literal.boolean is True
    infer_plan_schema(plan, registry=registry)


def _post_field(plan):
    ref = plan.relations[-1].root.input.lateral_join.post_join_filter.selection
    return ref.direct_reference.struct_field.field


def test_lateral_join_post_join_filter_binds_output_schema():
    # post_join_filter is applied to the join output (semantically a FilterRel
    # above the lateral join), so it resolves against the *output* schema, not the
    # combined left+right inputs. For an inner join the output is [k, v, w], so a
    # filter on the right column `w` binds to index 2; for a left-mark join the
    # output appends a `mark` column absent from the combined inputs, binding to
    # index 3.
    with fresh_rel_anchors():
        inner = lateral_join(
            _left(),
            _uncorrelated_right,
            type=stalg.JoinRel.JOIN_TYPE_INNER,
            post_join_filter=column("w"),
        )(registry)
    assert list(inner.relations[-1].root.names) == ["k", "v", "w"]
    assert _post_field(inner) == 2

    with fresh_rel_anchors():
        mark = lateral_join(
            _left(),
            _uncorrelated_right,
            type=stalg.JoinRel.JOIN_TYPE_LEFT_MARK,
            post_join_filter=column("mark"),
        )(registry)
    assert list(mark.relations[-1].root.names) == ["k", "v", "w", "mark"]
    assert _post_field(mark) == 3
    infer_plan_schema(mark, registry=registry)


def test_lateral_join_post_join_filter_on_dropped_side_raises():
    # A left-semi lateral join drops the right side from its output, so a
    # post_join_filter on a right column cannot resolve -- it fails fast rather
    # than emitting a dangling reference against the combined inputs.
    with pytest.raises(ValueError, match="not in list"):
        with fresh_rel_anchors():
            lateral_join(
                _left(),
                _uncorrelated_right,
                type=stalg.JoinRel.JOIN_TYPE_LEFT_SEMI,
                post_join_filter=column("w"),  # right-only, absent from output
            )(registry)
