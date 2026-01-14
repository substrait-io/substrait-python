import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import literal
from substrait.builders.plan import default_version, fetch, read_named_table
from substrait.builders.type import boolean, i64
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()], nullability=stt.Type.NULLABILITY_REQUIRED
)

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_fetch():
    table = read_named_table("table", named_struct)

    offset = literal(10, i64())
    count = literal(5, i64())

    actual = fetch(table, offset=offset, count=count)(registry)

    expected = stp.Plan(
        version=default_version,
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
        ],
    )

    assert actual == expected
