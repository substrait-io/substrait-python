import substrait.algebra_pb2 as stalg
import substrait.plan_pb2 as stp
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import column, literal
from substrait.builders.plan import default_version, expand, read_named_table
from substrait.builders.type import fp64, string
from substrait.type_inference import infer_plan_schema

struct = stt.Type.Struct(
    types=[string(nullable=False), fp64(nullable=False), fp64(nullable=False)],
    nullability=stt.Type.NULLABILITY_REQUIRED,
)
named_struct = stt.NamedStruct(names=["region", "q1", "q2"], struct=struct)


def _read():
    return read_named_table("sales", named_struct)


def test_expand_rel():
    actual = expand(
        _read(),
        fields=[
            ("consistent", column("region")),
            ("switching", [literal("q1", string()), literal("q2", string())]),
            ("switching", [column("q1"), column("q2")]),
        ],
        names=["region", "variable", "value", "idx"],
    )(None)

    inp = _read()(None).relations[-1].root.input
    ns = named_struct

    def col_expr(name):
        return column(name)(ns, None).referred_expr[0].expression

    def lit_expr(v):
        return literal(v, string())(ns, None).referred_expr[0].expression

    expected = stp.Plan(
        version=default_version,
        relations=[
            stp.PlanRel(
                root=stalg.RelRoot(
                    input=stalg.Rel(
                        expand=stalg.ExpandRel(
                            input=inp,
                            fields=[
                                stalg.ExpandRel.ExpandField(
                                    consistent_field=col_expr("region")
                                ),
                                stalg.ExpandRel.ExpandField(
                                    switching_field=stalg.ExpandRel.SwitchingField(
                                        duplicates=[lit_expr("q1"), lit_expr("q2")]
                                    )
                                ),
                                stalg.ExpandRel.ExpandField(
                                    switching_field=stalg.ExpandRel.SwitchingField(
                                        duplicates=[col_expr("q1"), col_expr("q2")]
                                    )
                                ),
                            ],
                        )
                    ),
                    names=["region", "variable", "value", "idx"],
                )
            )
        ],
    )
    assert actual == expected


def test_expand_schema_inference():
    plan = expand(
        _read(),
        fields=[
            ("consistent", column("region")),
            ("switching", [column("q1"), column("q2")]),
        ],
        names=["region", "value", "idx"],
    )(None)
    schema = infer_plan_schema(plan)
    kinds = [t.WhichOneof("kind") for t in schema.struct.types]
    # region (string), value (fp64), and the appended i32 duplicate index.
    assert kinds == ["string", "fp64", "i32"]


def test_expand_empty_switching_field_raises_clear_error():
    # An empty switching field has no expression to derive a type from; schema
    # inference must raise a clear error rather than an opaque IndexError.
    import pytest

    plan = expand(
        _read(),
        fields=[("switching", [])],
        names=["value", "idx"],
    )(None)
    with pytest.raises(ValueError, match="no duplicate expressions"):
        infer_plan_schema(plan)
