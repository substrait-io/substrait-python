import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.type import boolean, i64
from substrait.builders.plan import read_named_table

struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_read_rel():
    actual = read_named_table("example_table", named_struct)(None)

    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        read=stalg.ReadRel(
                            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                            base_schema=named_struct,
                            named_table=stalg.ReadRel.NamedTable(
                                names=["example_table"]
                            ),
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ]
    )

    assert actual == expected


def test_read_rel_db():
    actual = read_named_table(["example_db", "example_table"], named_struct)(None)

    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        read=stalg.ReadRel(
                            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                            base_schema=named_struct,
                            named_table=stalg.ReadRel.NamedTable(
                                names=["example_db", "example_table"]
                            ),
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ]
    )

    assert actual == expected
