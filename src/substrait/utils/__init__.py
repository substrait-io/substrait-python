"""
Utility and debugging functions for Substrait.
"""

from typing import Iterable

import substrait.algebra_pb2 as stalg
import substrait.extensions.extensions_pb2 as ste
import substrait.plan_pb2 as stplan
import substrait.type_pb2 as stp


def type_num_names(typ: stp.Type):
    kind = typ.WhichOneof("kind")
    if kind == "struct":
        lengths = [type_num_names(t) for t in typ.struct.types]
        return sum(lengths) + 1
    elif kind == "list":
        return type_num_names(typ.list.type)
    elif kind == "map":
        return type_num_names(typ.map.key) + type_num_names(typ.map.value)
    else:
        return 1


def merge_extension_urns(*extension_urns: Iterable[ste.SimpleExtensionURN]):
    """Merges multiple sets of SimpleExtensionURN objects into a single set.
    The order of extensions is kept intact, while duplicates are discarded.
    Assumes that there are no collisions (different extensions having identical anchors).
    """
    seen_urns = set()
    ret = []

    for urns in extension_urns:
        for urn in urns:
            if urn.urn not in seen_urns:
                seen_urns.add(urn.urn)
                ret.append(urn)

    return ret


def merge_extension_declarations(
    *extension_declarations: Iterable[ste.SimpleExtensionDeclaration],
):
    """Merges multiple sets of SimpleExtensionDeclaration objects into a single set.
    The order of extension declarations is kept intact, while duplicates are discarded.
    Assumes that there are no collisions (different extension declarations having identical anchors).
    """

    seen_extension_functions = set()
    ret = []

    for declarations in extension_declarations:
        for declaration in declarations:
            if declaration.WhichOneof("mapping_type") == "extension_function":
                ext_func = declaration.extension_function

                ident = (
                    ext_func.extension_urn_reference,
                    ext_func.name,
                )
                if ident not in seen_extension_functions:
                    seen_extension_functions.add(ident)
                    ret.append(declaration)
            else:
                # TODO handle extension type / type-variation declarations.
                mapping_type = declaration.WhichOneof("mapping_type")
                raise NotImplementedError(
                    f"cannot merge extension declaration of type {mapping_type!r}; "
                    f"only 'extension_function' declarations are supported so far"
                )

    return ret


def plan_subtrees(plan: stplan.Plan):
    """The leading shared-subtree relations of a Plan.

    A ``Plan`` carries its shared subtrees (the common subplans a ``ReferenceRel``
    points at) in-band as the leading ``rel`` entries of ``relations``; the query
    root is the trailing ``root`` entry. ``subtree_ordinal`` indexes into this
    ordered list. This is the single definition of "what is a shared subtree of a
    plan", reused by the builders and by schema inference.
    """
    return [pr.rel for pr in plan.relations if pr.WhichOneof("rel_type") == "rel"]


def _child_rel_fields(node):
    """The names of ``node``'s child-``Rel`` fields, discovered from the protobuf
    descriptor (any field whose message type is ``substrait.Rel``).

    Derived rather than hand-listed so the set stays correct as the schema evolves
    -- e.g. ``FilterRel.input``, ``JoinRel.{left,right}``, ``SetRel.inputs``,
    ``DdlRel.view_definition``. Relations with no child ``Rel`` (``ReadRel``,
    ``ReferenceRel``, ``UpdateRel``, ...) yield nothing. Note this covers only
    *direct* child relations; relations embedded inside ``Expression`` subqueries
    are self-contained (see :func:`inline_reference_rels`) and are not walked here.
    """
    return [
        f
        for f in node.DESCRIPTOR.fields
        if f.message_type is not None and f.message_type.full_name == "substrait.Rel"
    ]


def _iter_child_rels(rel: stalg.Rel):
    """Yield ``(container, index_or_None)`` for each child ``Rel`` of ``rel``.

    ``index`` is the position for a repeated field (``set.inputs``) or ``None`` for
    a singular field; ``container`` is the repeated field or the parent message so
    callers can read/replace the child in place.
    """
    rel_type = rel.WhichOneof("rel_type")
    if rel_type is None:
        return
    node = getattr(rel, rel_type)
    for field in _child_rel_fields(node):
        if field.label == field.LABEL_REPEATED:
            children = getattr(node, field.name)
            for i in range(len(children)):
                yield children, i
        elif node.HasField(field.name):
            yield node, field.name


def _child_rel(container, key):
    return container[key] if isinstance(key, int) else getattr(container, key)


def rebase_reference_ordinals(rel: stalg.Rel, remap: dict) -> stalg.Rel:
    """A copy of ``rel`` with every nested ``ReferenceRel.subtree_ordinal`` remapped
    (old -> new) per ``remap``. Recurses through direct child relations only."""
    out = stalg.Rel()
    out.CopyFrom(rel)
    _rebase_reference_ordinals_in_place(out, remap)
    return out


def _rebase_reference_ordinals_in_place(rel: stalg.Rel, remap: dict) -> None:
    if rel.WhichOneof("rel_type") == "reference":
        old = rel.reference.subtree_ordinal
        rel.reference.subtree_ordinal = remap.get(old, old)
        return
    for container, key in _iter_child_rels(rel):
        _rebase_reference_ordinals_in_place(_child_rel(container, key), remap)


def inline_reference_rels(rel: stalg.Rel, subtrees) -> stalg.Rel:
    """A copy of ``rel`` with every ``ReferenceRel`` replaced by (a recursive inline
    of) the shared subtree it points at, yielding a self-contained relation.

    Used to embed a subquery whose plan carries shared subtrees: a ``ReferenceRel``
    is plan-global, so it cannot survive inside an ``Expression.Subquery`` (which
    holds only a bare ``Rel``, with no place for the plan's subtree list). Inlining
    de-references the subquery so the emitted plan is valid. ``subtrees`` must be
    acyclic (builder-produced subtrees only reference earlier ones)."""
    if rel.WhichOneof("rel_type") == "reference":
        return inline_reference_rels(subtrees[rel.reference.subtree_ordinal], subtrees)
    out = stalg.Rel()
    out.CopyFrom(rel)
    _inline_reference_rels_in_place(out, subtrees)
    return out


def _inline_reference_rels_in_place(rel: stalg.Rel, subtrees) -> None:
    for container, key in _iter_child_rels(rel):
        child = _child_rel(container, key)
        if child.WhichOneof("rel_type") == "reference":
            child.CopyFrom(
                inline_reference_rels(
                    subtrees[child.reference.subtree_ordinal], subtrees
                )
            )
        else:
            _inline_reference_rels_in_place(child, subtrees)


def merge_extensions_into(target, *sources):
    """Merge the extension URNs and declarations of ``sources`` into ``target`` in place.

    Appends any extension URNs / declarations carried by ``sources`` whose identity
    is not already present on ``target``, deduplicating with the same keys as
    :func:`merge_extension_urns` / :func:`merge_extension_declarations` (URN string,
    resp. ``(extension URN reference, name)``). This is the identity used by
    ``builders.plan._merge_extensions``, so the DataFrame/Expr layer and the plan
    builders agree on when extensions collapse.

    ``target`` and each ``source`` are messages carrying repeated ``extension_urns``
    and ``extensions`` fields (a ``Plan`` or an ``ExtendedExpression``). Unlike the
    functions above, this mutates ``target`` rather than returning a new list, for
    callers that have already materialized the message they are accumulating into.
    """
    merged_urns = merge_extension_urns(
        target.extension_urns, *(s.extension_urns for s in sources)
    )
    merged_extensions = merge_extension_declarations(
        target.extensions, *(s.extensions for s in sources)
    )
    target.ClearField("extension_urns")
    target.extension_urns.extend(merged_urns)
    target.ClearField("extensions")
    target.extensions.extend(merged_extensions)
