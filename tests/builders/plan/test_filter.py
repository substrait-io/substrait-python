import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import column, literal
from substrait.builders.plan import default_version, filter, read_named_table
from substrait.builders.type import boolean, i64
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()], nullability=stt.Type.NULLABILITY_REQUIRED
)

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_filter():
    table = read_named_table("table", named_struct)

    actual = filter(table, literal(True, boolean()))(registry)

    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        filter=stalg.FilterRel(
                            input=table(None).relations[-1].root.input,
                            condition=stalg.Expression(
                                literal=stalg.Expression.Literal(
                                    boolean=True, nullable=True
                                )
                            ),
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ],
    )

    assert actual == expected


def test_filter_non_boolean_condition_raises():
    # A filter condition must be a boolean predicate; a non-boolean expression
    # (here the i64 column `id`) is rejected at build time.
    table = read_named_table("table", named_struct)
    with pytest.raises(ValueError, match="boolean predicate"):
        filter(table, column("id"))(registry)


def test_filter_bare_boolean_column_is_allowed():
    # Unlike a join, a bare boolean column is the *normal* filter condition
    # ("keep rows where this flag is true"), so it must not be rejected.
    table = read_named_table("table", named_struct)
    plan = filter(table, column("is_applicable"))(registry)
    assert plan.relations  # builds without error
