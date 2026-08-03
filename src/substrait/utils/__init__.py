"""
Utility and debugging functions for Substrait.
"""

from typing import Iterable

import substrait.algebra_pb2 as stalg
import substrait.extensions.extensions_pb2 as ste
import substrait.plan_pb2 as stplan
import substrait.type_pb2 as stp
from google.protobuf.message import Message


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

    Note that anchor collisions between independently numbered inputs are real, so
    that assumption does not hold in general. The builders no longer rely on it:
    they route inputs through ``ExtensionCollector.adopt``, which re-derives anchors
    from ``(urn, name)`` identities instead of merging pre-numbered sets. Retained
    for external callers doing their own merging.
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

    See :func:`merge_extension_urns` on why the builders no longer depend on that
    assumption; this is retained for external callers.
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
        if field.is_repeated:
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


# Every field that holds a function reference, i.e. an index into a plan's
# extension declarations. Matched by name during a descriptor walk rather than
# enumerated per message type, so a reference field added to the protos upstream is
# picked up automatically instead of being silently skipped. Note that this library
# only ever emits the first of these; the others can appear in a plan built
# elsewhere.
_FUNCTION_REFERENCE_FIELDS = frozenset(
    {
        # ScalarFunction / WindowFunction / AggregateFunction / WindowRelFunction
        "function_reference",
        "comparison_function_reference",  # SortField
        "custom_function_reference",  # ComparisonJoinKey.ComparisonType
    }
)


def remap_function_references(msg, remap: dict):
    """A copy of ``msg`` with every function reference remapped (old -> new).

    Used when a plan built elsewhere is folded into the build in progress: the
    incoming plan numbered its functions independently, so
    :meth:`~substrait.extension_registry.ExtensionCollector.adopt` re-derives the
    numbering and this applies the result to the relations and expressions that
    refer to it. Joins ``rebase_reference_ordinals`` and
    ``to_id_based_outer_references`` as a whole-tree rewrite.

    ``msg`` may be any message (a ``Rel``, ``Plan``, or ``Expression``); it is
    returned unchanged when ``remap`` is empty, which is the common case, so callers
    need not special-case the no-op.

    A reference of ``0`` is remapped like any other: the spec marks 0 a valid
    anchor/reference (spelled out in the protos since Substrait v0.83.0), and
    proto3 leaves such a field out of ``ListFields()``, so the fields to rewrite are
    read off the descriptor instead -- see :func:`_remap_own_function_references` for
    how presence decides which of them may be written without inventing a reference
    that was never there.

    A reference packed inside a ``google.protobuf.Any`` is out of reach: the walk
    descends into the wrapper, whose only fields are ``type_url`` and the opaque
    ``value`` bytes, and finds no reference field there. So an
    ``Extension{Single,Multi,Leaf}Rel.detail``, an ``AdvancedExtension.optimization``
    / ``.enhancement``, or a ``ReadRel.ExtensionTable.detail`` that embeds a function
    reference keeps the incoming plan's numbering. That is inherent, not an
    oversight: rewriting the payload means parsing it, which needs the very schema
    ``Any`` withholds -- so whoever produces a packed detail owns the remapping of
    the references inside it.
    """
    if not remap:
        return msg
    out = type(msg)()
    out.CopyFrom(msg)
    _remap_function_references_in_place(out, remap)
    return out


def _remap_own_function_references(msg, remap: dict) -> None:
    """Remap the function-reference fields ``msg`` itself carries (not its children).

    Driven by the descriptor rather than by ``ListFields()``: proto3 omits a
    default-valued scalar from ``ListFields()``, so a set-fields walk cannot see --
    let alone rewrite -- a ``function_reference: 0``, which is a reference the spec
    permits (since Substrait v0.83.0).

    Field presence decides whether a reference may be written blind:

    * the four ``function_reference`` fields (``Expression.ScalarFunction``,
      ``Expression.WindowFunction``, ``AggregateFunction``,
      ``ConsistentPartitionWindowRel.WindowRelFunction``) have no presence, and a
      containing message that is set always denotes a real function -- there is no
      valid ``ScalarFunction`` with no function -- so they are remapped
      unconditionally, 0 included.
    * ``SortField.comparison_function_reference`` (oneof ``sort_kind``) and
      ``ComparisonJoinKey.ComparisonType.custom_function_reference`` (oneof
      ``inner_type``) do have presence, so they are remapped only when their oneof
      selects them. Writing one blind would *invent* it: a ``SortField`` sorting by
      ``direction`` would come out sorting by comparison function instead.

    ``HasField`` cannot serve as the single gate, since it raises on a no-presence
    proto3 scalar; the oneof members are gated on ``WhichOneof`` instead.
    """
    for name in _FUNCTION_REFERENCE_FIELDS:
        field = msg.DESCRIPTOR.fields_by_name.get(name)
        if field is None:
            continue
        oneof = field.containing_oneof
        if oneof is not None and msg.WhichOneof(oneof.name) != name:
            continue
        current = getattr(msg, name)
        # A reference field is singular today; a repeated one added upstream would
        # arrive as a container, which is skipped rather than mis-assigned. See
        # _remap_function_references_in_place for why cardinality is read off the
        # value rather than the descriptor.
        if isinstance(current, int):
            setattr(msg, name, remap.get(current, current))


def _remap_function_references_in_place(msg, remap: dict) -> None:
    _remap_own_function_references(msg, remap)
    # Cardinality is read off the value rather than the descriptor: `label` is
    # deprecated in protobuf 6 while `is_repeated` is absent from older 5.x, and
    # this package supports both.
    #
    # Only *set* submessages are descended into -- an unset one holds nothing to
    # rewrite, and touching it would materialize it. ListFields() snapshots the set
    # fields, so the assignments above are safe to make during iteration.
    for field, value in msg.ListFields():
        if isinstance(value, Message):
            _remap_function_references_in_place(value, remap)
        elif field.message_type is not None:
            # A repeated message field, or a map whose values are messages
            # (ScalarMap/MessageMap expose .values(), repeated fields do not).
            items = value.values() if hasattr(value, "values") else value
            for item in items:
                if isinstance(item, Message):
                    _remap_function_references_in_place(item, remap)


def _iter_direct_subexpressions(msg):
    """Yield the immediate ``Expression`` messages owned by ``msg``.

    Recurses through sub-messages that are neither ``Expression`` nor ``Rel`` (e.g.
    ``FunctionArgument``, ``IfClause``, the ``Subquery`` wrappers), yields each
    ``Expression``-typed field without descending into it, and stops at ``Rel``
    fields (child relations / subquery inputs, handled separately). Discovered from
    the protobuf descriptor so it stays correct as the schema evolves -- a shallow
    scan of top-level ``Expression`` fields would miss e.g. an aggregate measure's
    arguments (``measures[].measure.arguments[].value``) or a sort key
    (``sorts[].expr``).
    """
    for field in msg.DESCRIPTOR.fields:
        if field.message_type is None:
            continue
        if field.message_type.GetOptions().map_entry:
            continue
        full = field.message_type.full_name
        if field.is_repeated:
            values = getattr(msg, field.name)
            if full == "substrait.Expression":
                yield from values
            elif full != "substrait.Rel":
                for value in values:
                    yield from _iter_direct_subexpressions(value)
        elif msg.HasField(field.name):
            if full == "substrait.Expression":
                yield getattr(msg, field.name)
            elif full != "substrait.Rel":
                yield from _iter_direct_subexpressions(getattr(msg, field.name))


def _iter_named_direct_expressions(node):
    """Like :func:`_iter_direct_subexpressions` but yields ``(field_name, expr)``,
    tagging each expression with the name of the top-level field on ``node`` it was
    reached through. Used to tell a join's ``post_join_filter`` (output-scoped) from
    its condition / ``residual_expression`` (combined-inputs-scoped)."""
    for field in node.DESCRIPTOR.fields:
        if field.message_type is None or field.message_type.GetOptions().map_entry:
            continue
        full = field.message_type.full_name
        if full == "substrait.Rel":
            continue
        if field.is_repeated:
            values = getattr(node, field.name)
        elif node.HasField(field.name):
            values = [getattr(node, field.name)]
        else:
            continue
        for value in values:
            if full == "substrait.Expression":
                yield field.name, value
            else:
                for expr in _iter_direct_subexpressions(value):
                    yield field.name, expr


def _iter_rel_expressions(rel: stalg.Rel):
    """Yield the root ``Expression`` messages a relation owns (its own scope): the
    filter condition, project expressions, join condition, aggregate/sort/expand
    expressions, etc. Expressions inside child relations belong to those relations."""
    rel_type = rel.WhichOneof("rel_type")
    if rel_type is None:
        return
    yield from _iter_direct_subexpressions(getattr(rel, rel_type))


def _iter_subquery_rels(expr: stalg.Expression):
    """Yield the input ``Rel``(s) of a subquery expression (``scalar.input``,
    ``set_predicate.tuples``, ``set_comparison.right``, ``in_predicate.haystack``),
    discovered from the descriptor. Empty for a non-subquery expression."""
    if expr.WhichOneof("rex_type") != "subquery":
        return
    variant = expr.subquery.WhichOneof("subquery_type")
    if variant is None:
        return
    inner = getattr(expr.subquery, variant)
    for field in _child_rel_fields(inner):
        if field.is_repeated:
            yield from getattr(inner, field.name)
        elif inner.HasField(field.name):
            yield getattr(inner, field.name)


def _iter_subquery_rels_in_expr(expr: stalg.Expression):
    """Yield every subquery input ``Rel`` reachable from ``expr`` in its own scope
    (i.e. not descending into those inner relations)."""
    yield from _iter_subquery_rels(expr)
    for sub in _iter_direct_subexpressions(expr):
        yield from _iter_subquery_rels_in_expr(sub)


def _walk_rel(rel: stalg.Rel):
    yield rel
    for container, key in _iter_child_rels(rel):
        yield from _walk_rel(_child_rel(container, key))
    for expr in _iter_rel_expressions(rel):
        for inner in _iter_subquery_rels_in_expr(expr):
            yield from _walk_rel(inner)


def iter_plan_rels(plan: stplan.Plan):
    """Yield every ``Rel`` in a Plan: the shared subtrees, the query root, all direct
    child relations, and relations embedded inside ``Expression`` subqueries."""
    for pr in plan.relations:
        kind = pr.WhichOneof("rel_type")
        if kind == "rel":
            yield from _walk_rel(pr.rel)
        elif kind == "root":
            yield from _walk_rel(pr.root.input)


def _rel_node_with_common(rel: stalg.Rel):
    """The active relation-variant submessage of ``rel`` if it carries a
    ``RelCommon``, else ``None`` (a ``ReferenceRel`` has no ``common``)."""
    rel_type = rel.WhichOneof("rel_type")
    if rel_type is None:
        return None
    node = getattr(rel, rel_type)
    if node.DESCRIPTOR.fields_by_name.get("common") is None:
        return None
    return node


def rel_anchor_of(rel: stalg.Rel):
    """The ``RelCommon.rel_anchor`` of ``rel`` if set, else ``None``."""
    node = _rel_node_with_common(rel)
    if node is None or not node.common.HasField("rel_anchor"):
        return None
    return node.common.rel_anchor


def _all_subexpressions(expr: stalg.Expression):
    """Yield every ``Expression`` transitively owned by ``expr`` in its own scope
    (through operators and subquery-wrapping expressions, but not into subquery
    input relations)."""
    for sub in _iter_direct_subexpressions(expr):
        yield sub
        yield from _all_subexpressions(sub)


def _is_steps_out_ref(expr: stalg.Expression) -> bool:
    if expr.WhichOneof("rex_type") != "selection":
        return False
    sel = expr.selection
    return (
        sel.WhichOneof("root_type") == "outer_reference"
        and sel.outer_reference.WhichOneof("outer_reference_type") == "steps_out"
    )


def _plan_has_steps_out(plan: stplan.Plan) -> bool:
    """Whether any ``OuterReference`` in ``plan`` is still offset-based (``steps_out``)
    -- i.e. whether :func:`to_id_based_outer_references` has anything to rewrite. A
    cheap pre-scan so the common (non-correlated) plan skips the copy-and-walk."""
    for rel in iter_plan_rels(plan):
        for expr in _iter_rel_expressions(rel):
            if _is_steps_out_ref(expr) or any(
                _is_steps_out_ref(sub) for sub in _all_subexpressions(expr)
            ):
                return True
    return False


# A join's expression fields bind against two different rows: ``post_join_filter``
# against the join *output* (semantically a Filter above the join), the condition
# and ``residual_expression`` against the *combined* left+right inputs. The join
# relation's own output equals that combined row for every non-reducing join, but a
# reducing join (semi/anti) emits a single side -- so a correlation into its
# condition scope names columns the output drops and has no anchorable relation.
_JOIN_COMBINED_SCOPED_FIELDS = frozenset({"expression", "residual_expression"})


def _is_reducing_join(node) -> bool:
    """Whether a join relation-variant ``node`` emits only one side (semi/anti), so
    its output row differs from its combined left+right condition scope."""
    field = node.DESCRIPTOR.fields_by_name.get("type")
    if field is None or field.enum_type is None:
        return False
    name = field.enum_type.values_by_number.get(node.type)
    return name is not None and ("SEMI" in name.name or "ANTI" in name.name)


def to_id_based_outer_references(plan: stplan.Plan) -> stplan.Plan:
    """A copy of ``plan`` with every offset-based ``OuterReference`` (``steps_out``)
    rewritten to the id-based form (``rel_reference`` naming a
    ``RelCommon.rel_anchor``).

    The binding relation an ``OuterReference`` resolves against is stamped with a
    plan-wide-unique ``rel_anchor`` (``>= 1``, per the Substrait spec), and the
    reference is rewritten to name it; several references to the same scope share one
    anchor, and an anchor already present is reused. References already id-based are
    left unchanged, so the pass is idempotent and tolerates a partially-converted
    input. A plan with nothing to rewrite is returned unchanged (no copy).

    A ``steps_out`` reference resolves against an enclosing query's *row*, which is
    the output of a specific relation, so the relation whose output is that row is
    anchored:

    * a single-input host (``Filter`` / ``Project`` / ...) exposes its **input**'s
      row. If that input is a ``ReferenceRel`` (a ``cache()``-shared subtree, which
      carries no ``RelCommon``), the shared subtree it points at is anchored instead
      -- the ``ReferenceRel`` has no ``emit``, so its output is exactly the subtree's.
      This is the shared-subtree / DAG case that offset-based ``steps_out`` cannot
      address unambiguously.
    * a ``post_join_filter``, or a leaf host's own filter, exposes the **host's**
      output row, so the host is anchored.
    * a join *condition* / ``residual_expression`` exposes the **combined** left+right
      row; the join's own output equals that row for a non-reducing join, so the join
      is anchored. For a *reducing* join (semi/anti) the two differ and no relation
      carries that row -- such a reference is left offset-based (still spec-valid, and
      read by inference), rather than mis-anchored.
    * a ``LateralJoinRel``'s ``rel_anchor`` is reserved (per the Substrait spec) for
      its right input's reference to the current *left* row, so it does **not** name
      the join's output row. A ``steps_out`` correlation into a lateral join's output
      therefore cannot be anchored on it and is left offset-based, rather than
      aliasing (and corrupting) the left-row anchor.

    Raises only if a resolvable binding carries no ``RelCommon`` at all (e.g. an
    ``UpdateRel``), which no correlated-subquery shape produces.
    """
    if not _plan_has_steps_out(plan):
        return plan

    out = stplan.Plan()
    out.CopyFrom(plan)

    subtrees = plan_subtrees(out)
    existing = [
        a for a in (rel_anchor_of(r) for r in iter_plan_rels(out)) if a is not None
    ]
    counter = max(existing) if existing else 0
    anchor_by_id: dict = {}

    def anchor_for(binding: stalg.Rel) -> int:
        nonlocal counter
        # A ReferenceRel is a plan-global pointer with no RelCommon of its own; its
        # output is the shared subtree's, so anchor the subtree instead.
        while binding.WhichOneof("rel_type") == "reference":
            binding = subtrees[binding.reference.subtree_ordinal]
        found = rel_anchor_of(binding)
        if found is not None:
            return found
        key = id(binding)
        if key in anchor_by_id:
            return anchor_by_id[key]
        node = _rel_node_with_common(binding)
        if node is None:
            raise Exception(
                "cannot resolve an outer reference into a "
                f"{binding.WhichOneof('rel_type')!r} relation to an id-based "
                "rel_reference: it carries no RelCommon to hold a rel_anchor"
            )
        counter += 1
        node.common.rel_anchor = counter
        anchor_by_id[key] = counter
        return counter

    def _binding_is_lateral_join(binding: stalg.Rel) -> bool:
        # A LateralJoinRel's rel_anchor is reserved (per the Substrait spec) for its
        # right input's reference to the current *left* row, so it does not denote
        # the join's output row and must not be reused to anchor a correlation into
        # that output. Unwrap a ReferenceRel to the subtree it points at first.
        while binding.WhichOneof("rel_type") == "reference":
            binding = subtrees[binding.reference.subtree_ordinal]
        return binding.WhichOneof("rel_type") == "lateral_join"

    def convert_expr(expr, scope, binding):
        rex = expr.WhichOneof("rex_type")
        if rex == "selection":
            sel = expr.selection
            if sel.WhichOneof("root_type") == "outer_reference":
                oref = sel.outer_reference
                if oref.WhichOneof("outer_reference_type") == "steps_out":
                    steps = oref.steps_out
                    if not 1 <= steps <= len(scope):
                        raise Exception(
                            f"outer reference steps_out={steps} escapes its "
                            f"{len(scope)} enclosing query scope(s)"
                        )
                    target = scope[-steps]
                    # None marks a combined-inputs scope with no anchorable relation
                    # (a reducing join's condition). A lateral join's rel_anchor is
                    # reserved for its right input's left-row reference, so it cannot
                    # double as the output-row anchor a correlation here would need.
                    # Both are left offset-based (spec-valid, read by inference).
                    if target is not None and not _binding_is_lateral_join(target):
                        oref.rel_reference = anchor_for(target)
        elif rex == "subquery":
            for inner in _iter_subquery_rels(expr):
                convert_rel(inner, scope + [binding])
        for sub in _iter_direct_subexpressions(expr):
            convert_expr(sub, scope, binding)

    def convert_rel(rel, scope):
        children = list(_iter_child_rels(rel))
        rel_type = rel.WhichOneof("rel_type")
        node = getattr(rel, rel_type) if rel_type is not None else None
        if node is not None:
            # The relation whose output row a subquery here would see one level up:
            # a single-input host exposes its input; a leaf or multi-input host its
            # own output -- except a reducing join's combined-inputs-scoped fields,
            # whose scope no relation's output carries (binding None -> left as-is).
            single_input = _child_rel(*children[0]) if len(children) == 1 else None
            reducing = single_input is None and _is_reducing_join(node)
            for name, expr in _iter_named_direct_expressions(node):
                if single_input is not None:
                    binding = single_input
                elif reducing and name in _JOIN_COMBINED_SCOPED_FIELDS:
                    binding = None
                else:
                    binding = rel
                convert_expr(expr, scope, binding)
        for container, key in children:
            convert_rel(_child_rel(container, key), scope)

    for pr in out.relations:
        kind = pr.WhichOneof("rel_type")
        if kind == "rel":
            convert_rel(pr.rel, [])
        elif kind == "root":
            convert_rel(pr.root.input, [])
    return out


def merge_extensions_into(target, *sources):
    """Merge the extension URNs and declarations of ``sources`` into ``target`` in place.

    Appends any extension URNs / declarations carried by ``sources`` whose identity
    is not already present on ``target``, deduplicating with the same keys as
    :func:`merge_extension_urns` / :func:`merge_extension_declarations` (URN string,
    resp. ``(extension URN reference, name)``).

    No longer used by the builders or the DataFrame layer, which let the build's
    ``ExtensionCollector`` accumulate declarations once instead; retained for
    external callers assembling plans by hand.

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
