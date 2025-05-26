import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.type import boolean, i64
from substrait.builders.plan import read_named_table, fetch
from substrait.builders.extended_expression import literal
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_fetch():
    table = read_named_table("table", named_struct)

    offset = literal(10, i64())
    count = literal(5, i64())

    actual = fetch(table, offset=offset, count=count)(registry)

    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        fetch=stalg.FetchRel(
                            input=table(None).relations[-1].root.input,
                            offset_expr=offset(None, None).referred_expr[0].expression,
                            count_expr=count(None, None).referred_expr[0].expression,
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ]
    )

    assert actual == expected
