import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import literal
from substrait.builders.plan import (
    ddl,
    default_version,
    read_named_table,
    update,
    write_named_table,
)
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


def test_ddl_create_table():
    actual = ddl(
        ["db", "t"],
        stalg.DdlRel.DDL_OBJECT_TABLE,
        stalg.DdlRel.DDL_OP_CREATE,
        table_schema=named_struct,
    )(None)

    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        ddl=stalg.DdlRel(
                            named_object=stalg.NamedObjectWrite(names=["db", "t"]),
                            table_schema=named_struct,
                            object=stalg.DdlRel.DDL_OBJECT_TABLE,
                            op=stalg.DdlRel.DDL_OP_CREATE,
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ],
    )
    assert actual == expected


def test_update_rel():
    actual = update("t", named_struct, [(0, literal(5, i64(nullable=False)))])(None)

    lit_expr = (
        literal(5, i64(nullable=False))(named_struct, None).referred_expr[0].expression
    )
    expected_update = stalg.UpdateRel(
        table_schema=named_struct,
        transformations=[
            stalg.UpdateRel.TransformExpression(
                column_target=0, transformation=lit_expr
            )
        ],
    )
    expected_update.named_table.names.extend(["t"])
    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(update=expected_update),
                    names=["id", "is_applicable"],
                )
            )
        ],
    )
    assert actual == expected
