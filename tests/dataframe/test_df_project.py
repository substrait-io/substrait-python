import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

import substrait.dataframe as sdf
from substrait.builders.plan import default_version, read_named_table
from substrait.builders.type import boolean, i64
from substrait.extension_registry import ExtensionRegistry

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
