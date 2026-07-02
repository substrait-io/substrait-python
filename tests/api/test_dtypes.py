"""Tests for nullability control (substrait.dtypes) and literal coercion."""

import pytest
import substrait.type_pb2 as stt

import substrait.api as sub
from substrait.builders.plan import read_named_table as b_read
from substrait.builders.plan import select
from substrait.builders.type import fp64, i32, i64, named_struct, string, struct
from substrait.dtypes import DataType
from substrait.expr import col
from substrait.extension_registry import ExtensionRegistry

registry = ExtensionRegistry(load_default_extensions=True)

REQUIRED = stt.Type.NULLABILITY_REQUIRED
NULLABLE = stt.Type.NULLABILITY_NULLABLE


# ---------------------------------------------------------------------------
# #1 nullability control
# ---------------------------------------------------------------------------


def test_datatype_is_callable_and_defaults_nullable():
    assert sub.i64().i64.nullability == NULLABLE
    assert sub.i64(nullable=False).i64.nullability == REQUIRED


def test_datatype_nullable_and_non_null_properties():
    assert sub.i64.nullable.i64.nullability == NULLABLE
    assert sub.i64.non_null.i64.nullability == REQUIRED


def test_bare_datatype_in_schema_is_nullable():
    plan = sub.read_named_table("t", {"id": sub.i64}).to_plan()
    schema = plan.relations[-1].root.input.read.base_schema
    assert schema.struct.types[0].i64.nullability == NULLABLE


def test_non_null_datatype_in_schema_is_required():
    plan = sub.read_named_table("t", {"id": sub.i64.non_null}).to_plan()
    schema = plan.relations[-1].root.input.read.base_schema
    assert schema.struct.types[0].i64.nullability == REQUIRED


def test_mixed_nullability_schema_matches_explicit_builder():
    fluent = sub.read_named_table(
        "t", {"id": sub.i64.non_null, "name": sub.string}
    ).to_plan()
    explicit = b_read(
        "t",
        named_struct(
            names=["id", "name"],
            struct=struct(types=[i64(nullable=False), string()], nullable=False),
        ),
    )(registry)
    assert fluent.SerializeToString() == explicit.SerializeToString()


def test_datatype_repr():
    assert repr(sub.i64) == "<dtype i64>"


def test_datatype_exported():
    assert isinstance(sub.i64, DataType)


# ---------------------------------------------------------------------------
# Full Substrait type-system coverage
# ---------------------------------------------------------------------------

# proto Type kinds intentionally NOT surfaced on the ergonomic facade:
#  - deprecated in favor of the precision_* variants
#  - not concrete data types / advanced extension machinery
_EXCLUDED_KINDS = {
    "timestamp",
    "time",
    "timestamp_tz",
    "func",
    "user_defined",
    "user_defined_type_reference",
    "alias",
}
# proto kind -> name exported on substrait.api
_KIND_TO_API = {"bool": "boolean", "varchar": "varchar", "list": "list_", "map": "map_"}


def _proto_type_kinds():
    return [f.name for f in stt.Type.DESCRIPTOR.fields]


def test_every_concrete_type_is_reachable_on_api():
    missing = []
    for kind in _proto_type_kinds():
        if kind in _EXCLUDED_KINDS:
            continue
        name = _KIND_TO_API.get(kind, kind)
        if name not in sub.__all__:
            missing.append(kind)
    assert missing == [], f"Substrait types not exposed on substrait.api: {missing}"


def test_no_arg_types_are_datatypes_with_nullability():
    for dt in (sub.uuid, sub.interval_year):
        assert isinstance(dt, DataType)
        assert dt.non_null.WhichOneof("kind") in ("uuid", "interval_year")


@pytest.mark.parametrize(
    "typ, expected_kind",
    [
        (sub.uuid.non_null, "uuid"),
        (sub.interval_year.non_null, "interval_year"),
        (sub.interval_day(6), "interval_day"),
        (sub.interval_compound(6), "interval_compound"),
        (sub.fixed_char(10), "fixed_char"),
        (sub.varchar(10), "varchar"),
        (sub.fixed_binary(16), "fixed_binary"),
        (sub.decimal(38, 10), "decimal"),
        (sub.precision_time(6), "precision_time"),
        (sub.precision_timestamp(6), "precision_timestamp"),
        (sub.precision_timestamp_tz(6), "precision_timestamp_tz"),
    ],
)
def test_parametrized_types_build_expected_kind(typ, expected_kind):
    assert typ.WhichOneof("kind") == expected_kind


def test_parametrized_type_usable_in_schema():
    # A decimal + varchar schema round-trips through read_named_table.
    plan = sub.read_named_table(
        "t", {"price": sub.decimal(38, 10), "code": sub.varchar(8)}
    ).to_plan()
    schema = plan.relations[-1].root.input.read.base_schema
    kinds = [t.WhichOneof("kind") for t in schema.struct.types]
    assert kinds == ["decimal", "varchar"]


# ---------------------------------------------------------------------------
# #2 literal coercion + cast
# ---------------------------------------------------------------------------


def _project_expr(ns, expr):
    return select(b_read("t", ns), expressions=[expr.unbound])(registry)


def test_fp64_times_int_literal_resolves_to_fp64():
    ns = named_struct(
        names=["price"], struct=struct(types=[fp64(nullable=False)], nullable=False)
    )
    plan = _project_expr(ns, col("price") * 2)
    fn = plan.relations[-1].root.input.project.expressions[0].scalar_function
    # The int literal was coerced to fp64 so multiply:fp64_fp64 resolves.
    assert fn.output_type.WhichOneof("kind") == "fp64"
    assert fn.arguments[1].value.literal.WhichOneof("literal_type") == "fp64"


def test_i32_compared_to_int_literal_resolves():
    ns = named_struct(
        names=["n"], struct=struct(types=[i32(nullable=False)], nullable=False)
    )
    # Without coercion this would try gt:i32_i64 and fail to resolve.
    plan = _project_expr(ns, col("n") > 25)
    fn = plan.relations[-1].root.input.project.expressions[0].scalar_function
    assert fn.arguments[1].value.literal.WhichOneof("literal_type") == "i32"


def test_float_literal_not_narrowed_to_int_column():
    ns = named_struct(
        names=["n"], struct=struct(types=[i64(nullable=False)], nullable=False)
    )
    # A float literal must NOT be narrowed to the integer column type; because
    # Substrait has no multiply:i64_fp64 this raises rather than silently
    # losing the fractional part. The user casts the column to bridge it.
    with pytest.raises(Exception, match="fp64"):
        _project_expr(ns, col("n") * 1.5)
    # Casting the column resolves it as fp64_fp64.
    plan = _project_expr(ns, col("n").cast(sub.fp64) * 1.5)
    fn = plan.relations[-1].root.input.project.expressions[0].scalar_function
    assert fn.output_type.WhichOneof("kind") == "fp64"


def test_i64_column_gt_int_literal_unchanged():
    # Backwards-compatible: the common i64 > int case is still i64_i64.
    ns = named_struct(
        names=["age"], struct=struct(types=[i64(nullable=False)], nullable=False)
    )
    plan = _project_expr(ns, col("age") > 25)
    fn = plan.relations[-1].root.input.project.expressions[0].scalar_function
    assert fn.arguments[1].value.literal.WhichOneof("literal_type") == "i64"


def test_reflected_operator_coerces_literal():
    ns = named_struct(
        names=["price"], struct=struct(types=[fp64(nullable=False)], nullable=False)
    )
    plan = _project_expr(ns, 100 - col("price"))
    fn = plan.relations[-1].root.input.project.expressions[0].scalar_function
    # literal on the left, coerced to fp64, operand order preserved.
    assert fn.arguments[0].value.literal.WhichOneof("literal_type") == "fp64"
    assert fn.arguments[1].value.HasField("selection")


def test_cast_bridges_two_column_types():
    ns = named_struct(
        names=["a", "b"],
        struct=struct(types=[i32(nullable=False), i64(nullable=False)], nullable=False),
    )
    # i32 + i64 does not resolve directly; cast makes it i64 + i64.
    plan = _project_expr(ns, col("a").cast(sub.i64) + col("b"))
    add_fn = plan.relations[-1].root.input.project.expressions[0].scalar_function
    assert add_fn.arguments[0].value.HasField("cast")


def test_cast_accepts_proto_type_and_builder():
    ns = named_struct(
        names=["a"], struct=struct(types=[i32(nullable=False)], nullable=False)
    )
    from_builder = _project_expr(ns, col("a").cast(sub.i64))
    from_proto = _project_expr(ns, col("a").cast(i64()))
    assert from_builder.SerializeToString() == from_proto.SerializeToString()


def test_two_column_mismatch_still_raises_without_cast():
    ns = named_struct(
        names=["a", "b"],
        struct=struct(types=[i32(nullable=False), i64(nullable=False)], nullable=False),
    )
    # Coercion only applies to literals, not between two columns.
    with pytest.raises(Exception):
        _project_expr(ns, col("a") + col("b"))
