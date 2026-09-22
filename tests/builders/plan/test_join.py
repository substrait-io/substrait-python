import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import column, literal
from substrait.builders.plan import default_version, join, read_named_table
from substrait.builders.type import boolean, i64, string
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()], nullability=stt.Type.NULLABILITY_REQUIRED
)

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)

named_struct_2 = stt.NamedStruct(
    names=["fk_id", "name"],
    struct=stt.Type.Struct(
        types=[i64(nullable=False), string()], nullability=stt.Type.NULLABILITY_REQUIRED
    ),
)


def test_join_optional_args_are_keyword_only():
    # post_join_filter / extension are keyword-only so inserting new params
    # cannot silently rebind an extension passed positionally.
    table = read_named_table("table", named_struct)
    table2 = read_named_table("table2", named_struct_2)
    with pytest.raises(TypeError):
        join(
            table,
            table2,
            literal(True, boolean()),
            stalg.JoinRel.JOIN_TYPE_INNER,
            None,  # would have bound to post_join_filter positionally
        )


def test_join():
    table = read_named_table("table", named_struct)
    table2 = read_named_table("table2", named_struct_2)

    actual = join(
        table, table2, literal(True, boolean()), stalg.JoinRel.JOIN_TYPE_INNER
    )(registry)

    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        join=stalg.JoinRel(
                            left=table(None).relations[-1].root.input,
                            right=table2(None).relations[-1].root.input,
                            expression=literal(True, boolean())(None, None)
                            .referred_expr[0]
                            .expression,
                            type=stalg.JoinRel.JOIN_TYPE_INNER,
                        )
                    ),
                    names=["id", "is_applicable", "fk_id", "name"],
                )
            )
        ],
    )

    assert actual == expected


def test_join_non_boolean_condition_raises():
    # A join condition must be a boolean predicate. A bare column reference (the
    # pandas ``on="key"`` idiom) binds to a non-boolean column and would otherwise
    # build a legit-looking plan that degrades to a Cartesian product at execution.
    table = read_named_table("table", named_struct)
    table2 = read_named_table("table2", named_struct_2)
    with pytest.raises(ValueError, match="boolean predicate"):
        join(table, table2, column("id"), stalg.JoinRel.JOIN_TYPE_INNER)(registry)


def test_join_boolean_column_condition_is_allowed():
    # A boolean column is a valid (if unusual) join condition -- a filtered
    # Cartesian product, expressible in SQL as ``JOIN ... ON <bool col>`` -- so it
    # must not be rejected by the boolean-predicate check.
    table = read_named_table("table", named_struct)
    table2 = read_named_table("table2", named_struct_2)
    plan = join(table, table2, column("is_applicable"), stalg.JoinRel.JOIN_TYPE_INNER)(
        registry
    )
    assert plan.relations  # builds without error


def _post_field(plan):
    ref = plan.relations[-1].root.input.join.post_join_filter.selection
    return ref.direct_reference.struct_field.field


def test_join_post_join_filter_binds_output_schema():
    # post_join_filter is applied to the join output (semantically a FilterRel
    # above the join), so it resolves against the output schema. For an inner join
    # the output is the combined schema [id, is_applicable, fk_id, flag], so a
    # filter on the right-side boolean `flag` binds to index 3; for a right-semi
    # join the output is the right side only [fk_id, flag], so it binds to index 1.
    left = read_named_table("l", named_struct)
    right = read_named_table(
        "r",
        stt.NamedStruct(
            names=["fk_id", "flag"],
            struct=stt.Type.Struct(
                types=[i64(nullable=False), boolean()],
                nullability=stt.Type.NULLABILITY_REQUIRED,
            ),
        ),
    )

    inner = join(
        left,
        right,
        literal(True, boolean()),
        stalg.JoinRel.JOIN_TYPE_INNER,
        post_join_filter=column("flag"),
    )(registry)
    assert _post_field(inner) == 3

    right_semi = join(
        left,
        right,
        literal(True, boolean()),
        stalg.JoinRel.JOIN_TYPE_RIGHT_SEMI,
        post_join_filter=column("flag"),
    )(registry)
    assert list(right_semi.relations[-1].root.names) == ["fk_id", "flag"]
    assert _post_field(right_semi) == 1


def test_join_post_join_filter_on_dropped_side_raises():
    # A right-semi join drops the left side from its output, so a post_join_filter
    # on a left column cannot resolve -- it fails fast rather than emitting a
    # dangling field reference against the combined schema.
    left = read_named_table("l", named_struct)
    right = read_named_table("r", named_struct_2)
    with pytest.raises(ValueError, match="not in list"):
        join(
            left,
            right,
            literal(True, boolean()),
            stalg.JoinRel.JOIN_TYPE_RIGHT_SEMI,
            post_join_filter=column("id"),  # left-only column, absent from output
        )(registry)
