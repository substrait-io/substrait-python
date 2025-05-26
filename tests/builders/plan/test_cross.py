import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.type import boolean, i64, string
from substrait.builders.plan import read_named_table, cross
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)

named_struct_2 = stt.NamedStruct(
    names=["fk_id", "name"],
    struct=stt.Type.Struct(types=[i64(nullable=False), string()]),
)


def test_cross_join():
    table = read_named_table("table", named_struct)
    table2 = read_named_table("table2", named_struct_2)

    actual = cross(table, table2)(registry)

    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        cross=stalg.CrossRel(
                            left=table(None).relations[-1].root.input,
                            right=table2(None).relations[-1].root.input,
                        )
                    ),
                    names=["id", "is_applicable", "fk_id", "name"],
                )
            )
        ]
    )

    assert actual == expected
