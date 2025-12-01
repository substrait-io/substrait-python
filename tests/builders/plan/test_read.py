import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.type import boolean, i64
from substrait.builders.plan import read_named_table
import pytest
from substrait.gen.proto.extensions.extensions_pb2 import AdvancedExtension
from google.protobuf import any_pb2
from google.protobuf.wrappers_pb2 import StringValue

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()],
    nullability=stt.Type.Nullability.NULLABILITY_REQUIRED,
)

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


def test_read_rel_ae():
    any = any_pb2.Any()
    any.Pack(StringValue(value="Opt1"))

    extension = AdvancedExtension(optimization=[any])

    actual = read_named_table(["example_db", "example_table"], named_struct, extension)(
        None
    )

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
                            advanced_extension=extension,
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ]
    )

    assert actual == expected
