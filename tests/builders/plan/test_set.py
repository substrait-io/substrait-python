import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.type import boolean, i64
from substrait.builders.plan import read_named_table, set
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_set():
    table = read_named_table("table", named_struct)
    table2 = read_named_table("table2", named_struct)

    actual = set([table, table2], stalg.SetRel.SET_OP_UNION_ALL)(None)

    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        set=stalg.SetRel(
                            inputs=[
                                table(None).relations[-1].root.input,
                                table2(None).relations[-1].root.input,
                            ],
                            op=stalg.SetRel.SET_OP_UNION_ALL,
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ]
    )

    assert actual == expected
