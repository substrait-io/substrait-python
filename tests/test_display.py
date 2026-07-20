import substrait.type_pb2 as stt

from substrait.builders.extended_expression import literal
from substrait.builders.plan import fetch, read_named_table, virtual_table
from substrait.builders.type import boolean, i64
from substrait.extension_registry import ExtensionRegistry
from substrait.utils.display import PlanPrinter

registry = ExtensionRegistry(load_default_extensions=False)

struct = stt.Type.Struct(
    types=[i64(nullable=False), boolean()], nullability=stt.Type.NULLABILITY_REQUIRED
)
named_struct = stt.NamedStruct(names=["id", "flag"], struct=struct)


def _printer() -> PlanPrinter:
    return PlanPrinter(use_colors=False)


def test_stringify_virtual_table_renders_row_expressions():
    rows = [
        [literal(1, i64(nullable=False)), literal(True, boolean())],
        [literal(2, i64(nullable=False)), literal(False, boolean())],
    ]
    plan = virtual_table(rows, named_struct)(registry)

    out = _printer().stringify_plan(plan)

    assert "read: virtual_table" in out
    assert "rows: 2" in out
    assert "row[0]:" in out
    assert "row[1]:" in out
    # Row expressions are rendered as literals.
    assert "literal: 1" in out
    assert "literal: False" in out


def test_stringify_fetch_with_offset_and_count():
    table = read_named_table("t", named_struct)
    plan = fetch(table, offset=literal(10, i64()), count=literal(5, i64()))(registry)

    out = _printer().stringify_plan(plan)

    assert "fetch: offset=10, count=5" in out


def test_stringify_fetch_unset_offset_and_count():
    table = read_named_table("t", named_struct)
    # offset unset defaults to 0; count=None means "all remaining rows".
    plan = fetch(table, offset=None, count=None)(registry)

    out = _printer().stringify_plan(plan)

    assert "fetch: offset=0, count=all" in out
