import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.plan import read_named_table, write_named_table
from substrait.builders.type import boolean, i64

struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_write_rel():
    actual = write_named_table(
        "example_table_write_test",
        read_named_table("example_table", named_struct),
    )(None)

    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        write=stalg.WriteRel(
                            input=stalg.Rel(
                                read=stalg.ReadRel(
                                    common=stalg.RelCommon(
                                        direct=stalg.RelCommon.Direct()
                                    ),
                                    base_schema=named_struct,
                                    named_table=stalg.ReadRel.NamedTable(
                                        names=["example_table"]
                                    ),
                                )
                            ),
                            op=stalg.WriteRel.WRITE_OP_CTAS,
                            table_schema=named_struct,
                            create_mode=stalg.WriteRel.CREATE_MODE_ERROR_IF_EXISTS,
                            named_table=stalg.NamedObjectWrite(
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
