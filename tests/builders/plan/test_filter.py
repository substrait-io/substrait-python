import substrait.gen.proto.type_pb2 as stt
import substrait.gen.proto.plan_pb2 as stp
import substrait.gen.proto.algebra_pb2 as stalg
from substrait.builders.type import boolean, i64
from substrait.builders.plan import read_named_table, filter
from substrait.builders.extended_expression import literal
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(types=[i64(nullable=False), boolean()])

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_filter():
    table = read_named_table("table", named_struct)

    actual = filter(table, literal(True, boolean()))(registry)

    expected = stp.Plan(
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        filter=stalg.FilterRel(
                            input=table(None).relations[-1].root.input,
                            condition=stalg.Expression(
                                literal=stalg.Expression.Literal(
                                    boolean=True, nullable=True
                                )
                            ),
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ]
    )

    assert actual == expected
