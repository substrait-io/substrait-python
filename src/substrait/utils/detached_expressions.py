"""Reading and writing detached expression subtrees (spec v0.105.0).

Protobuf parsers cap how deeply messages may nest: upb (the Python runtime),
protobuf-java and C++ all reject a message nested more than 100 levels below the
one being parsed. Every expression level costs several message levels -- a nested
struct is ``Expression`` -> ``Nested`` -> ``Struct`` -> ``Expression`` -- so a
plan with an expression only ~33 levels deep can already be unreadable.

The spec's workaround is `bounded expression nesting`_: a producer moves expression
subtrees into ``detached_expressions`` on the containing ``PlanRel`` or
``ExtendedExpression`` and leaves a ``detached_expression_ordinal`` reference in
their place. Detachment is encoding-only; resolving the ordinals recovers the same
logical tree.

* :func:`detach_expressions` is the producer side: it cuts expressions that would
  otherwise exceed a nesting budget, so the serialized message parses under the
  default limits. A message within budget is returned unchanged.
* :func:`resolve_detached_expressions` is the consumer side: it inlines every
  ordinal, validating the spec's rules, so the rest of this library -- schema
  inference, display, the builders -- sees ordinary expression trees.

Both walk the message through its protobuf descriptor, so every relation and
expression kind is covered, and both are iterative, so trees deeper than Python's
recursion limit are fine. Neither looks inside a ``google.protobuf.Any``: its
payload is opaque bytes here.

.. _bounded expression nesting:
   https://substrait.io/serialization/binary_serialization/#bounded-expression-nesting
"""

import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.plan_pb2 as stplan
from google.protobuf.message import Message

# The default parse recursion limit of protobuf-java, C++ and upb: the deepest
# submessage may sit this many levels below the message being parsed.
DEFAULT_MAX_DEPTH = 100

_EXPRESSION = "substrait.Expression"
_ANY = "google.protobuf.Any"
_ORDINAL = "detached_expression_ordinal"
_TABLE = "detached_expressions"


def _children(msg: Message, *, skip_table: bool = False):
    """Yield ``(child, levels)`` for each set submessage of ``msg``.

    ``levels`` is how many message levels below ``msg`` the child sits on the
    wire: 1, or 2 for a map value (the map entry is a message of its own).
    ``google.protobuf.Any`` payloads are opaque and not descended into, and
    ``skip_table`` leaves out a container's own ``detached_expressions``.
    """
    if msg.DESCRIPTOR.full_name == _ANY:
        return
    for field, value in msg.ListFields():
        if field.message_type is None or (skip_table and field.name == _TABLE):
            continue
        if isinstance(value, Message):
            yield value, 1
        elif field.message_type.GetOptions().map_entry:
            # A map whose values are messages; scalar-valued maps hold none.
            for item in value.values():
                if isinstance(item, Message):
                    yield item, 2
        else:
            for item in value:
                yield item, 1


def _containers(msg):
    """The ``(container, depth)`` pairs that own detached expressions in ``msg``."""
    if isinstance(msg, stplan.Plan):
        return [(pr, 1) for pr in msg.relations]
    if isinstance(msg, (stplan.PlanRel, stee.ExtendedExpression)):
        return [(msg, 0)]
    raise TypeError(
        "detached expressions live on a Plan, PlanRel or ExtendedExpression, "
        f"not a {type(msg).__name__}"
    )


def _copy(msg):
    out = type(msg)()
    out.CopyFrom(msg)
    return out


def _is_ordinal(expr: stalg.Expression) -> bool:
    return expr.WhichOneof("rex_type") == _ORDINAL


def _contains_ordinal(container) -> bool:
    stack = [container]
    while stack:
        msg = stack.pop()
        if msg.DESCRIPTOR.full_name == _EXPRESSION and _is_ordinal(msg):
            return True
        stack.extend(child for child, _ in _children(msg))
    return False


def _contains_any(container) -> bool:
    stack = [container]
    while stack:
        msg = stack.pop()
        if msg.DESCRIPTOR.full_name == _ANY:
            return True
        stack.extend(child for child, _ in _children(msg))
    return False


def resolve_detached_expressions(msg):
    """A copy of ``msg`` with every ``detached_expression_ordinal`` inlined.

    ``msg`` is a ``Plan`` (each of its ``PlanRel`` is resolved against its own
    table), a ``PlanRel`` or an ``ExtendedExpression``. Resolution starts from
    the relation or referred expressions and follows ordinals transitively,
    enforcing the spec's rules on that reachable portion; a violation raises
    ``ValueError``:

    1. an ordinal indexes its own container's ``detached_expressions``;
    2. each entry is referenced at most once;
    3. references are acyclic;
    4. an entry is not itself an ordinal (its children may be).

    Unreachable entries are neither resolved nor validated.

    The resolved table is then cleared -- except in a container that carries a
    ``google.protobuf.Any`` payload. An extension payload may reference entries
    by ordinal, and since it is opaque here its references cannot be followed, so
    the table is kept intact for it, as the spec requires. The inlined entries
    are then merely unreachable, which the spec allows.

    ``msg`` is returned unchanged when it holds no ordinals, which is the common
    case, so callers need not check first.
    """
    if not any(getattr(c, _TABLE) or _contains_ordinal(c) for c, _ in _containers(msg)):
        return msg
    out = _copy(msg)
    for container, _ in _containers(out):
        table = getattr(container, _TABLE)
        used = set()
        stack = list(_children(container, skip_table=True))
        while stack:
            node, _ = stack.pop()
            if node.DESCRIPTOR.full_name == _EXPRESSION and _is_ordinal(node):
                ordinal = node.detached_expression_ordinal
                if ordinal >= len(table):
                    raise ValueError(
                        f"detached expression ordinal {ordinal} is out of range: "
                        f"the container has {len(table)} detached expressions"
                    )
                if ordinal in used:
                    # With every entry inlined at most once, a cycle shows up here
                    # too: following it back reaches an entry already in use.
                    raise ValueError(
                        f"detached expression {ordinal} is referenced more than "
                        "once, or by a cycle"
                    )
                entry = table[ordinal]
                if _is_ordinal(entry):
                    raise ValueError(
                        f"detached expression {ordinal} is itself an ordinal "
                        f"({entry.detached_expression_ordinal})"
                    )
                used.add(ordinal)
                node.CopyFrom(entry)
            stack.extend(_children(node))
        if not _contains_any(container):
            container.ClearField(_TABLE)
    return out


def _height(msg: Message) -> int:
    """How many message levels ``msg``'s deepest submessage sits below it."""
    deepest = 0
    stack = [(msg, 0)]
    while stack:
        node, depth = stack.pop()
        deepest = max(deepest, depth)
        stack.extend((child, depth + levels) for child, levels in _children(node))
    return deepest


def detach_expressions(msg, *, max_depth: int = DEFAULT_MAX_DEPTH):
    """A copy of ``msg`` whose expressions nest at most ``max_depth`` levels deep.

    ``msg`` is a ``Plan``, ``PlanRel`` or ``ExtendedExpression``; depth is counted
    in protobuf message levels below ``msg`` itself, the way parsers count it, and
    the default matches their default limit. A message already within budget is
    returned unchanged, so its serialization is byte-identical.

    Otherwise the walk goes top-down. An expression whose subtree would end below
    ``max_depth``, and which itself sits deeper than half the budget (and than the
    container's entries), is moved to
    the end of its container's ``detached_expressions`` and replaced by its
    ordinal; the moved entry is then processed from its new position, right under
    the container. Cutting at half the budget leaves chunks about half the budget
    deep rather than one entry per level past the limit. Entries come out in
    pre-order, so a child's ordinal is larger than its parent's. Entries already in
    the table keep their positions, so existing ordinals still find their targets.

    Only expressions are detached. Nesting inside literals, types, field
    reference paths, masks or relation trees (see ``ReferenceRel``), and inside
    ``google.protobuf.Any`` payloads, is left as is, so such a message can still
    exceed ``max_depth``: the result is best effort, since the limit belongs to
    the consumer, and some raise it.

    ``max_depth=0`` detaches every expression that can be, which is handy for
    testing a consumer against the detached form.
    """
    out = _copy(msg)
    containers = _containers(out)
    if _height(out) <= max_depth:
        return out
    for container, base in containers:
        _detach_in_place(container, base, max_depth)
    return out


def _detach_in_place(container, base: int, max_depth: int) -> None:
    table = getattr(container, _TABLE)
    entry_depth = base + 1
    # Only expressions below the entry roots are cut, so an entry root is never
    # detached again however small the budget.
    threshold = max(max_depth // 2, entry_depth)

    # Index the tree once: ``nodes[i]`` is a submessage and ``children[i]`` its
    # ``(index, levels)`` pairs. Holding every wrapper keeps the tree stable while
    # it is rewritten. The relation tree comes first, then the existing entries.
    nodes, children = [], []

    def add(msg):
        nodes.append(msg)
        children.append([])
        return len(nodes) - 1

    roots = [
        (add(child), base + levels)
        for child, levels in _children(container, skip_table=True)
    ]
    roots += [(add(entry), entry_depth) for entry in table]
    stack = [i for i, _ in roots]
    while stack:
        i = stack.pop()
        for child, levels in _children(nodes[i]):
            j = add(child)
            children[i].append((j, levels))
            stack.append(j)

    # Children are indexed after their parent, so a reverse sweep sees them first.
    height = [0] * len(nodes)
    for i in reversed(range(len(nodes))):
        height[i] = max((levels + height[j] for j, levels in children[i]), default=0)

    # Choose the cuts top-down. A cut only changes depths below it, so every
    # choice can be made against the subtree heights of the uncut tree. Each cut's
    # subtree is walked straight after it is chosen, which numbers them in
    # pre-order.
    cuts = []
    stack = [(i, depth, True) for i, depth in reversed(roots)]
    while stack:
        i, depth, is_root = stack.pop()
        node = nodes[i]
        if (
            not is_root
            and node.DESCRIPTOR.full_name == _EXPRESSION
            and depth > threshold
            # An ordinal is already as shallow as an expression gets; detaching it
            # would make an entry that is itself an ordinal.
            and not _is_ordinal(node)
        ):
            if depth + height[i] <= max_depth:
                continue
            cuts.append(i)
            depth = entry_depth
        stack.extend((j, depth + levels, False) for j, levels in reversed(children[i]))

    # Materialize the deepest cuts first, so each entry copies only its own chunk:
    # the cuts below it are already ordinals.
    first = len(table)
    for _ in cuts:
        table.add()
    for k in reversed(range(len(cuts))):
        node = nodes[cuts[k]]
        table[first + k].CopyFrom(node)
        node.Clear()
        node.detached_expression_ordinal = first + k
