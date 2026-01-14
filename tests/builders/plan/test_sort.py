import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import column
from substrait.builders.plan import default_version, read_named_table, sort
from substrait.builders.type import boolean, i64
from substrait.extension_registry import ExtensionRegistry
from substrait.type_inference import infer_plan_schema

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()], nullability=stt.Type.NULLABILITY_REQUIRED
)

named_struct = stt.NamedStruct(names=["id", "is_applicable"], struct=struct)


def test_sort_no_direction():
    table = read_named_table("table", named_struct)

    col = column("id")

    actual = sort(table, expressions=[col])(registry)

    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        sort=stalg.SortRel(
                            input=table(None).relations[-1].root.input,
                            sorts=[
                                stalg.SortField(
                                    direction=stalg.SortField.SORT_DIRECTION_ASC_NULLS_LAST,
                                    expr=col(infer_plan_schema(table(None)), registry)
                                    .referred_expr[0]
                                    .expression,
                                )
                            ],
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ],
    )

    assert actual == expected


def test_sort_direction():
    table = read_named_table("table", named_struct)

    col = column("id")

    actual = sort(
        table, expressions=[(col, stalg.SortField.SORT_DIRECTION_DESC_NULLS_FIRST)]
    )(registry)

    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        sort=stalg.SortRel(
                            input=table(None).relations[-1].root.input,
                            sorts=[
                                stalg.SortField(
                                    direction=stalg.SortField.SORT_DIRECTION_DESC_NULLS_FIRST,
                                    expr=col(infer_plan_schema(table(None)), registry)
                                    .referred_expr[0]
                                    .expression,
                                )
                            ],
                        )
                    ),
                    names=["id", "is_applicable"],
                )
            )
        ],
    )

    assert actual == expected
