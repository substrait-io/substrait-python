import pytest
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


@pytest.mark.parametrize(
    "nullabilities",
    [
        pytest.param((False, True), id="nullable-last"),
        pytest.param((True, False), id="nullable-first"),
        pytest.param((False, False), id="all-required"),
        pytest.param((True, True), id="all-nullable"),
        pytest.param((False, False, True), id="nullable-third"),
        pytest.param((False,), id="single-required"),
        pytest.param((True,), id="single-nullable"),
    ],
)
def test_expand_switching_field_nullability(nullabilities):
    # algebra.proto: a switching field is nullable if any duplicate is nullable.
    names = [f"value_{i}" for i in range(len(nullabilities))]
    input_schema = stt.NamedStruct(
        names=["region", *names],
        struct=stt.Type.Struct(
            types=[string(nullable=False)] + [fp64(nullable=n) for n in nullabilities],
            nullability=stt.Type.NULLABILITY_REQUIRED,
        ),
    )
    plan = expand(
        read_named_table("sales", input_schema),
        fields=[
            ("consistent", column("region")),
            ("switching", [column(name) for name in names]),
        ],
        names=["region", "value", "idx"],
    )(None)
    original = stp.Plan()
    original.CopyFrom(plan)

    schema = infer_plan_schema(plan)

    assert schema.struct.types[0] == string(nullable=False)
    assert schema.struct.types[1] == fp64(nullable=any(nullabilities))
    assert plan == original


def test_expand_switching_field_preserves_unbound_type():
    # A partially bound plan may carry a placeholder with no nullability.
    unbound = stt.Type(unbound=stt.Type.Unbound())
    input_schema = stt.NamedStruct(
        names=["u"],
        struct=stt.Type.Struct(
            types=[unbound], nullability=stt.Type.NULLABILITY_REQUIRED
        ),
    )
    plan = expand(
        read_named_table("partial", input_schema),
        fields=[("switching", [column("u"), column("u")])],
        names=["value", "idx"],
    )(None)

    assert infer_plan_schema(plan).struct.types[0] == unbound


def _switching_plan(types):
    names = [f"value_{i}" for i in range(len(types))]
    schema = stt.NamedStruct(
        names=names,
        struct=stt.Type.Struct(types=types, nullability=stt.Type.NULLABILITY_REQUIRED),
    )
    return expand(
        read_named_table("partial", schema),
        fields=[("switching", [column(name) for name in names])],
        names=["value", "idx"],
    )(None)


@pytest.mark.parametrize(
    "bound_nullabilities, unbound_position",
    [
        pytest.param((False,), 0, id="unbound-required"),
        pytest.param((False,), 1, id="required-unbound"),
        pytest.param((True,), 0, id="unbound-nullable"),
        pytest.param((True,), 1, id="nullable-unbound"),
        pytest.param((False, True), 0, id="unbound-required-nullable"),
        pytest.param((False, True), 1, id="required-unbound-nullable"),
        pytest.param((False, True), 2, id="required-nullable-unbound"),
    ],
)
def test_expand_switching_field_combines_unbound_duplicates(
    bound_nullabilities, unbound_position
):
    unbound = stt.Type(unbound=stt.Type.Unbound())
    types = [fp64(nullable=n) for n in bound_nullabilities]
    types.insert(unbound_position, unbound)
    plan = _switching_plan(types)
    original = plan.SerializeToString()

    result = infer_plan_schema(plan).struct.types[0]

    # A known nullable duplicate fixes nullability regardless of the placeholder.
    # Otherwise the placeholder may still bind to a nullable type.
    expected = fp64(nullable=True) if any(bound_nullabilities) else unbound
    assert result == expected
    assert plan.SerializeToString() == original


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("unbound_position", [None, 0, 1, 2])
def test_expand_switching_field_rejects_mixed_type_classes(reverse, unbound_position):
    types = [fp64(nullable=False), string(nullable=True)]
    if reverse:
        types.reverse()
    if unbound_position is not None:
        types.insert(unbound_position, stt.Type(unbound=stt.Type.Unbound()))
    plan = _switching_plan(types)
    original = plan.SerializeToString()

    with pytest.raises(ValueError, match="duplicates must share one type class"):
        infer_plan_schema(plan)

    assert plan.SerializeToString() == original


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
