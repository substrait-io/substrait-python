import substrait.algebra_pb2 as stalg
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import column, literal
from substrait.builders.plan import (
    filter,
    materialize,
    read_named_table,
    select,
    with_relation_alias,
)
from substrait.builders.type import boolean, i64
from substrait.extension_registry import ExtensionRegistry


def test_materialize_preserves_inferred_names_on_nested_relations():
    registry = ExtensionRegistry(load_default_extensions=False)
    schema = stt.NamedStruct(
        names=["id", "is_applicable"],
        struct=stt.Type.Struct(
            types=[i64(nullable=False), boolean()],
            nullability=stt.Type.NULLABILITY_REQUIRED,
        ),
    )
    plan = select(
        filter(
            read_named_table("example", schema),
            literal(True, boolean(nullable=False)),
        ),
        [column("id")],
    )

    bound = materialize(plan, registry, include_relation_output_names=True)
    project = bound.relations[-1].root.input.project
    filtered = project.input.filter
    read = filtered.input.read

    assert list(project.common.hint.output_names) == ["id"]
    assert list(filtered.common.hint.output_names) == ["id", "is_applicable"]
    assert list(read.common.hint.output_names) == ["id", "is_applicable"]


def test_materialize_keeps_output_name_hints_opt_in():
    registry = ExtensionRegistry(load_default_extensions=False)
    schema = stt.NamedStruct(
        names=["id"],
        struct=stt.Type.Struct(
            types=[i64(nullable=False)],
            nullability=stt.Type.NULLABILITY_REQUIRED,
        ),
    )

    bound = materialize(read_named_table("example", schema), registry)

    assert not bound.relations[-1].root.input.read.common.HasField("hint")


def test_relation_aliases_survive_native_relation_nesting():
    registry = ExtensionRegistry(load_default_extensions=False)
    schema = stt.NamedStruct(
        names=["order_id"],
        struct=stt.Type.Struct(
            types=[i64(nullable=False)],
            nullability=stt.Type.NULLABILITY_REQUIRED,
        ),
    )
    base = with_relation_alias(
        read_named_table("orders", schema),
        "orders_read",
    )
    projected = with_relation_alias(
        select(base, [column("order_id")]),
        "orders_project",
    )

    bound = materialize(
        projected,
        registry,
        include_relation_output_names=True,
    )

    project = bound.relations[-1].root.input.project
    assert project.common.hint.alias == "orders_project"
    assert list(project.common.hint.output_names) == ["order_id"]
    assert project.input.read.common.hint.alias == "orders_read"
    assert list(project.input.read.common.hint.output_names) == ["order_id"]
