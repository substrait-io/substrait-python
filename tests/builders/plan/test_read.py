import pytest
import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt
from google.protobuf import any_pb2
from google.protobuf.wrappers_pb2 import StringValue
from substrait.extensions.extensions_pb2 import AdvancedExtension

from substrait.builders.extended_expression import literal
from substrait.builders.plan import (
    default_version,
    extension_table,
    local_files,
    read_named_table,
    virtual_table,
)
from substrait.builders.type import boolean, i64

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()],
    nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
)

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_read_rel():
    actual = read_named_table("example_table", named_struct)(None)

    expected = stp.Plan(
        version=default_version,
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
        ],
    )

    assert actual == expected


def test_read_rel_db():
    actual = read_named_table(["example_db", "example_table"], named_struct)(None)

    expected = stp.Plan(
        version=default_version,
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
        ],
    )

    assert actual == expected


def test_read_rel_schema_nullable():
    struct = stt.Type.Struct(
        types=[i64(nullable=False), boolean()],
        nullability=stt.Type.Nullability.NULLABILITY_NULLABLE,
    )

    named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)
    with pytest.raises(
        Exception, match=r"NamedStruct must not contain a nullable struct"
    ):
        read_named_table("example_table", named_struct)(None)


def test_virtual_table_rel():
    rows = [[literal(1, i64(nullable=False)), literal(True, boolean())]]
    actual = virtual_table(rows, named_struct)(None)

    fields = [
        literal(1, i64(nullable=False))(named_struct, None).referred_expr[0].expression,
        literal(True, boolean())(named_struct, None).referred_expr[0].expression,
    ]
    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        read=stalg.ReadRel(
                            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                            base_schema=named_struct,
                            virtual_table=stalg.ReadRel.VirtualTable(
                                expressions=[
                                    stalg.Expression.Nested.Struct(fields=fields)
                                ]
                            ),
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ],
    )
    assert actual == expected


def test_local_files_rel():
    fof = stalg.ReadRel.LocalFiles.FileOrFiles
    items = [fof(uri_file="a.parquet", parquet=fof.ParquetReadOptions())]
    actual = local_files(named_struct, items)(None)

    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        read=stalg.ReadRel(
                            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                            base_schema=named_struct,
                            local_files=stalg.ReadRel.LocalFiles(items=items),
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ],
    )
    assert actual == expected


def test_extension_table_rel():
    detail = any_pb2.Any()
    detail.Pack(StringValue(value="custom"))
    actual = extension_table(named_struct, detail)(None)

    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        read=stalg.ReadRel(
                            common=stalg.RelCommon(direct=stalg.RelCommon.Direct()),
                            base_schema=named_struct,
                            extension_table=stalg.ReadRel.ExtensionTable(detail=detail),
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ],
    )
    assert actual == expected


def test_virtual_table_rejects_nullable_schema():
    nullable = stt.NamedStruct(
        names=["id", "is_applicable"],
        struct=stt.Type.Struct(
            types=[i64(nullable=False), boolean()],
            nullability=stt.Type.Nullability.NULLABILITY_NULLABLE,
        ),
    )
    with pytest.raises(Exception, match=r"must not contain a nullable struct"):
        virtual_table([], nullable)(None)


def test_read_rel_ae():
    any = any_pb2.Any()
    any.Pack(StringValue(value="Opt1"))

    extension = AdvancedExtension(optimization=[any])

    actual = read_named_table(["example_db", "example_table"], named_struct, extension)(
        None
    )

    expected = stp.Plan(
        version=default_version,
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
                            advanced_extension=extension,
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ],
    )

    assert actual == expected
