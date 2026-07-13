import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import literal
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
