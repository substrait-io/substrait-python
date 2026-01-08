import substrait.gen.proto.algebra_pb2 as stalg
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.type_pb2 as stt
from substrait.builders.extended_expression import column
from substrait.builders.plan import default_version, project, read_named_table, select
from substrait.builders.type import boolean, i64
from substrait.extension_registry import ExtensionRegistry

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
