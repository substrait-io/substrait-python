import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.type import boolean, i64
from substrait.builders.plan import read_named_table, project
from substrait.builders.extended_expression import column
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_project():
    table = read_named_table("table", named_struct)

    actual = project(table, [column("id")])(registry)

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
        ]
    )

    assert actual == expected
