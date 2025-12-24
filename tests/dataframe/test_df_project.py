import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.type import boolean, i64
from substrait.builders.plan import read_named_table, default_version
from substrait.extension_registry import ExtensionRegistry
import substrait.dataframe as sdf


registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()], nullability=stt.Type.NULLABILITY_REQUIRED
)

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_project():
    df = sdf.DataFrame(read_named_table("table", named_struct))

    actual = df.select(id=sdf.col("id")).to_substrait(registry)

    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        project=stalg.ProjectRel(
                            common=stalg.RelCommon(
                                emit=stalg.RelCommon.Emit(output_mapping=[2])
                            ),
                            input=df.to_substrait(None).relations[-1].root.input,
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

    print(actual)
    print("--------------")
    print(expected)

    assert actual == expected
