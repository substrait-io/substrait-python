import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import cast, column, literal
from substrait.builders.plan import default_version, project, read_named_table, select
from substrait.builders.type import boolean, i64
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()], nullability=stt.Type.NULLABILITY_REQUIRED
)

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_project():
    table = read_named_table("table", named_struct)

    actual = project(table, [column("id")])(registry)

    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        project=stalg.ProjectRel(
                            input=table(None).relations[-1].root.input,
                            expressions=[
                                stalg.Expression(
                                    selection=stalg.Expression.FieldReference(
                                        direct_reference=stalg.Expression.ReferenceSegment(
                                            struct_field=stalg.Expression.ReferenceSegment.StructField(
                                                field=0
                                            )
                                        ),
                                        root_reference=stalg.Expression.FieldReference.RootReference(),
                                    )
                                )
                            ],
                        )
                    ),
                    names=["id", "is_applicable", "id"],
                )
            )
        ],
    )

    assert actual == expected


def test_select():
    table = read_named_table("table", named_struct)

    actual = select(table, [column("id")])(registry)

    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        project=stalg.ProjectRel(
                            common=stalg.RelCommon(
                                emit=stalg.RelCommon.Emit(output_mapping=[2])
                            ),
                            input=table(None).relations[-1].root.input,
                            expressions=[
                                stalg.Expression(
                                    selection=stalg.Expression.FieldReference(
                                        direct_reference=stalg.Expression.ReferenceSegment(
                                            struct_field=stalg.Expression.ReferenceSegment.StructField(
                                                field=0
                                            )
                                        ),
                                        root_reference=stalg.Expression.FieldReference.RootReference(),
                                    )
                                )
                            ],
                        )
                    ),
                    names=["id"],
                )
            )
        ],
        version=default_version,
    )

    assert actual == expected


# A struct column takes one top-level field but several depth-first names.
nested_named_struct = stt.NamedStruct(
    names=["a", "s", "x", "y", "b"],
    struct=stt.Type.Struct(
        types=[
            i64(nullable=False),
            stt.Type(
                struct=stt.Type.Struct(
                    types=[i64(nullable=False), i64(nullable=False)],
                    nullability=stt.Type.NULLABILITY_REQUIRED,
                )
            ),
            i64(nullable=False),
        ],
        nullability=stt.Type.NULLABILITY_REQUIRED,
    ),
)


def test_select_struct_column():
    table = read_named_table("table", nested_named_struct)

    actual = select(table, [column("a"), column("s")])(registry)
    root = actual.relations[-1].root

    # The projected expressions sit after the input's 3 top-level fields, not after
    # its 5 names, and the struct column keeps its nested names.
    assert list(root.input.project.common.emit.output_mapping) == [3, 4]
    assert list(root.names) == ["a", "s", "x", "y"]
    assert list(infer_plan_schema(actual).names) == ["a", "s", "x", "y"]


def test_project_struct_column():
    table = read_named_table("table", nested_named_struct)

    actual = project(table, [column("s")])(registry)

    assert list(actual.relations[-1].root.names) == [
        *nested_named_struct.names,
        "s",
        "x",
        "y",
    ]
    assert len(infer_plan_schema(actual).struct.types) == 4


@pytest.mark.parametrize("builder", [project, select])
def test_expression_with_more_names_than_fields_is_rejected(builder):
    # Every output name lands in the plan root, so a scalar given two names would
    # leave the root with more names than the output type has fields.
    table = read_named_table("table", named_struct)

    with pytest.raises(ValueError, match="has 2 names"):
        builder(table, [literal(1, i64(), alias=["one", "two"])])(registry)


def test_select_struct_valued_expression_keeps_full_alias():
    table = read_named_table("table", nested_named_struct)
    pair = stt.Type(
        struct=stt.Type.Struct(
            types=[i64(), i64()], nullability=stt.Type.NULLABILITY_NULLABLE
        )
    )

    actual = select(table, [cast(column("s"), pair, alias=["c", "p", "q"])])(registry)

    assert list(actual.relations[-1].root.names) == ["c", "p", "q"]


def test_select_struct_valued_expression_with_partial_alias_is_rejected():
    # Too few names would shift every later column's name onto the wrong field.
    table = read_named_table("table", nested_named_struct)
    pair = stt.Type(
        struct=stt.Type.Struct(
            types=[i64(), i64()], nullability=stt.Type.NULLABILITY_NULLABLE
        )
    )

    with pytest.raises(ValueError, match="has 2 names, but its output type needs 3"):
        select(table, [cast(column("s"), pair, alias=["c", "p"]), column("a")])(
            registry
        )


@pytest.mark.parametrize("builder", [project, select])
def test_expression_without_output_names_is_rejected(builder):
    table = read_named_table("table", named_struct)
    unnamed = column("id")(named_struct, registry)
    del unnamed.referred_expr[0].output_names[:]

    with pytest.raises(ValueError, match="no output names"):
        builder(table, [unnamed])(registry)
