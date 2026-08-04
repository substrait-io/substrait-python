import substrait.algebra_pb2 as stalg
import substrait.type_pb2 as stt

from substrait.builders.extended_expression import column, literal
from substrait.builders.plan import (
    filter,
    materialize,
    read_named_table,
    select,
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
