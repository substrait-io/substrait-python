"""Extension anchor consistency across the SQL translator.

The translator materializes a Plan at *every* step and builds a set operation's two
sides as independent plans before merging them (see ``sql_to_substrait.translate``).
Because extension anchors are plan-local, each side numbers its functions from 1
independently -- so folding one plan into another has to re-derive those numbers
rather than trust them. These are plan-only assertions, deliberately not behind the
engine round-trip skip that covers the rest of this directory.
"""

import substrait.type_pb2 as stt

from substrait.extension_registry import ExtensionRegistry
from substrait.sql.sql_to_substrait import convert

I64 = stt.Type(i64=stt.Type.I64(nullability=stt.Type.NULLABILITY_REQUIRED))


def schema_resolver(name: str) -> stt.NamedStruct:
    return stt.NamedStruct(
        names=["a", "b"],
        struct=stt.Type.Struct(
            types=[I64, I64], nullability=stt.Type.NULLABILITY_REQUIRED
        ),
    )


def _declarations(plan):
    return {
        d.extension_function.function_anchor: d.extension_function.name
        for d in plan.extensions
    }


def _function_references(plan):
    """Every function reference appearing anywhere in ``plan``'s relations."""
    found = []

    def walk(message):
        for field, value in message.ListFields():
            if field.name == "function_reference" and isinstance(value, int):
                found.append(value)
            elif field.message_type is not None:
                items = value if hasattr(value, "__len__") else [value]
                for item in items:
                    if hasattr(item, "ListFields"):
                        walk(item)

    for plan_rel in plan.relations:
        walk(plan_rel)
    return found


def test_union_branches_get_distinct_anchors():
    """Each side of the union numbers its own function 1; the merge must renumber
    one of them rather than let two functions share an anchor."""
    registry = ExtensionRegistry(load_default_extensions=True)
    plan = convert(
        "SELECT a + b FROM t UNION ALL SELECT a - b FROM t",
        "generic",
        schema_resolver,
        registry,
    )

    declarations = _declarations(plan)
    anchors = [d.extension_function.function_anchor for d in plan.extensions]
    assert len(anchors) == len(set(anchors)), f"anchors collide: {anchors}"
    assert set(declarations.values()) == {"add:i64_i64", "subtract:i64_i64"}

    # Every reference in the tree must resolve to a declared function.
    references = _function_references(plan)
    assert references, "expected the union's branches to reference functions"
    assert all(reference in declarations for reference in references)
    # ...and both branches' functions must actually be referenced.
    assert {declarations[reference] for reference in references} == {
        "add:i64_i64",
        "subtract:i64_i64",
    }


def test_urn_anchors_are_distinct_across_branches():
    """Two branches drawing on different extension URNs must not share a URN anchor."""
    registry = ExtensionRegistry(load_default_extensions=True)
    plan = convert(
        "SELECT a + b FROM t UNION ALL SELECT a FROM t WHERE a > b",
        "generic",
        schema_resolver,
        registry,
    )

    urn_anchors = [u.extension_urn_anchor for u in plan.extension_urns]
    assert len(urn_anchors) == len(set(urn_anchors)), (
        f"URN anchors collide: {urn_anchors}"
    )
    assert len(plan.extension_urns) == 2, [u.urn for u in plan.extension_urns]

    # Each declaration must point at a URN the plan actually declares.
    declared = {u.extension_urn_anchor for u in plan.extension_urns}
    for declaration in plan.extensions:
        assert declaration.extension_function.extension_urn_reference in declared
