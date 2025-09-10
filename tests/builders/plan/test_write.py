import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.type import boolean, i64
from substrait.builders.plan import read_named_table

struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_write_rel():
    actual = read_named_table("example_table", named_struct)(None)

    # write example table test
    stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        write=stalg.WriteRel(
                            input=stalg.Rel(
                                read=stalg.ReadRel(
                                    common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                                    base_schema=named_struct,
                                    named_table=stalg.ReadRel.NamedTable(
                                        names=["example_table"]
                                    ),
                                )
                            ),
                            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                            table_schema=named_struct,
                            create_mode=stalg.WriteRel.CreateMode.CREATE_MODE_REPLACE_IF_EXISTS,
                            named_table=stalg.NamedTable(
                                names=["example_table_write_test"]
                            ),
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ]
    )

    # read back the table
    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        read=stalg.ReadRel(
                            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                            base_schema=named_struct,
                            named_table=stalg.ReadRel.NamedTable(
                                names=["example_table_write_test"]
                            ),
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ]
    )

    assert actual == expected


def test_write_rel_db():
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
