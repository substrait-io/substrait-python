"""Reading and writing detached subtrees (spec v0.105.0).

Protobuf parsers cap how deeply messages may nest: upb (the Python runtime),
protobuf-java and C++ all reject a message nested more than 100 levels below the
one being parsed. Every expression level costs several message levels -- a nested
struct is ``Expression`` -> ``Nested`` -> ``Struct`` -> ``Expression`` -- so a
plan with an expression only ~33 levels deep can already be unreadable.

The spec's workaround is `bounded expression nesting`_: a producer moves subtrees
into a table on the containing ``PlanRel`` or ``ExtendedExpression`` -- expressions
into ``detached_expressions`` -- and leaves an ordinal reference in their place
(``detached_expression_ordinal``). Detachment is encoding-only; resolving the
ordinals recovers the same logical tree.

* :func:`detach` is the producer side: it cuts expressions that would otherwise
  exceed a nesting budget, so the serialized message parses under the default
  limits. A message within budget is returned as is.
* :func:`resolve_detached` is the consumer side: it inlines every ordinal,
  validating the spec's rules, so the rest of this library -- schema inference,
  display, the builders -- sees ordinary trees.

Both walk the message through its protobuf descriptor, so every relation and
expression kind is covered, and both are iterative, so trees deeper than Python's
recursion limit are fine. Neither looks inside a ``google.protobuf.Any``: its
payload is opaque bytes here.

.. _bounded expression nesting:
   https://substrait.io/serialization/binary_serialization/#bounded-expression-nesting
"""

from dataclasses import dataclass

import substrait.algebra_pb2 as stalg
import substrait.extended_expression_pb2 as stee
import substrait.plan_pb2 as stplan
import substrait.type_pb2 as stt
from google.protobuf.message import Message

# The default parse recursion limit of protobuf-java, C++ and upb: the deepest
# submessage may sit this many levels below the message being parsed.
DEFAULT_MAX_DEPTH = 100

_ANY = "google.protobuf.Any"


@dataclass(frozen=True)
class _Table:
    """One kind of detachable subtree: its message type, the oneof member that
    holds an ordinal in place of a subtree, and the container field holding the
    detached entries. Each table is resolved on its own: an ordinal of one kind
    only ever indexes the table of that kind."""

    label: str
    message: type
    oneof: str
    ordinal: str
    field: str

    @property
    def full_name(self) -> str:
        return self.message.DESCRIPTOR.full_name

    @property
    def tag(self) -> bytes:
        """The ordinal field's wire tag (a varint, wire type 0)."""
        value = self.message.DESCRIPTOR.fields_by_name[self.ordinal].number << 3
        out = bytearray()
        while value > 0x7F:
            out.append(value & 0x7F | 0x80)
            value >>= 7
        out.append(value)
        return bytes(out)


_EXPRESSIONS = _Table(
    "expression",
    stalg.Expression,
    "rex_type",
    "detached_expression_ordinal",
    "detached_expressions",
)
_TABLES = (_EXPRESSIONS,)
_TABLE_BY_MESSAGE = {table.full_name: table for table in _TABLES}
_TABLE_FIELDS = frozenset(table.field for table in _TABLES)
_TAGS = tuple(table.tag for table in _TABLES)

# Stands in for a resolved entry that has to keep its position. Nothing can
# validly reference it, so its content only has to be a valid expression.
_PLACEHOLDER = stalg.Expression(
    literal=stalg.Expression.Literal(
        null=stt.Type(bool=stt.Type.Boolean(nullability=stt.Type.NULLABILITY_NULLABLE))
    )
)


def _declaration_index(item) -> int:
    return item[0].index


def _children(msg: Message, *, skip_tables: bool = False):
    """Yield ``(child, levels)`` for each set submessage of ``msg``.

    ``levels`` is how many message levels below ``msg`` the child sits on the
    wire: 1, or 2 for a map value (the map entry is a message of its own).
    ``google.protobuf.Any`` payloads are opaque and not descended into, and
    ``skip_tables`` leaves out a container's own detached tables.

    Fields come in declaration order, not field-number order (which
    ``ListFields`` uses), so the cuts :func:`detach` makes are numbered the way
    substrait-java numbers them.
    """
    if msg.DESCRIPTOR.full_name == _ANY:
        return
    for field, value in sorted(msg.ListFields(), key=_declaration_index):
        if field.message_type is None or (skip_tables and field.name in _TABLE_FIELDS):
            continue
        if isinstance(value, Message):
            yield value, 1
        elif hasattr(value, "values"):
            # A map (repeated fields have no .values()); only message-valued maps
            # hold submessages.
            for item in value.values():
                if isinstance(item, Message):
                    yield item, 2
        else:
            for item in value:
                yield item, 1


def _find(root: Message, predicate, *, skip_tables: bool = False) -> bool:
    """Whether ``predicate`` holds for ``root`` or any submessage below it."""
    stack = [root]
    while stack:
        msg = stack.pop()
        if predicate(msg):
            return True
        stack.extend(
            child
            for child, _ in _children(msg, skip_tables=skip_tables and msg is root)
        )
    return False


def _containers(msg):
    """The ``(container, depth)`` pairs that own detached tables in ``msg``."""
    if isinstance(msg, stplan.Plan):
        return [(pr, 1) for pr in msg.relations]
    if isinstance(msg, (stplan.PlanRel, stee.ExtendedExpression)):
        return [(msg, 0)]
    raise TypeError(
        "detached subtrees live on a Plan, PlanRel or ExtendedExpression, "
        f"not a {type(msg).__name__}"
    )


def _copy(msg):
    out = type(msg)()
    out.CopyFrom(msg)
    return out


def _ordinal_table(msg: Message):
    """The table ``msg`` refers into, if it is an ordinal reference, else None."""
    table = _TABLE_BY_MESSAGE.get(msg.DESCRIPTOR.full_name)
    if table is not None and msg.WhichOneof(table.oneof) == table.ordinal:
        return table
    return None


def _is_any(msg: Message) -> bool:
    return msg.DESCRIPTOR.full_name == _ANY


def _holds_ordinals(container) -> bool:
    """Whether ``container``'s relation or referred expressions hold an ordinal.

    Screened on the wire bytes first: serialization is canonical, so if no
    ordinal field's tag occurs in them there is no ordinal, and that is decided
    in native code. Only when a tag's bytes do occur -- an ordinal, or the same
    bytes inside some other value -- does the descriptor walk settle it.
    """
    data = container.SerializeToString()
    if not any(tag in data for tag in _TAGS):
        return False
    return _find(container, _ordinal_table, skip_tables=True)


def resolve_detached(msg):
    """``msg`` with every detached ordinal inlined.

    ``msg`` is a ``Plan`` (each of its ``PlanRel`` is resolved against its own
    tables), a ``PlanRel`` or an ``ExtendedExpression``. Resolution starts from
    the relation or referred expressions and follows ordinals transitively,
    enforcing the spec's rules on that reachable portion; a violation raises
    ``ValueError``:

    1. an ordinal indexes its own container's table of its kind;
    2. each entry is referenced at most once;
    3. references are acyclic;
    4. an entry is not itself an ordinal (its children may be).

    Unreachable entries are neither resolved nor validated.

    A container's tables are then cleared -- unless it carries a
    ``google.protobuf.Any`` payload. An extension payload may reference entries
    the relation tree does not, and since it is opaque here its references
    cannot be followed, so those entries keep their ordinals, as the spec
    requires. The entries resolved here are a different matter: each entry is
    referenced at most once, so no payload can validly refer to one of them. The
    trailing run of them is dropped, which renumbers nothing, and any left in
    place are replaced by a null literal, so none still points into that run.

    ``msg`` itself is returned when it holds no ordinals, which is the common
    case, so callers need not check first. Otherwise the result is a copy.
    """
    if not any(_holds_ordinals(container) for container, _ in _containers(msg)):
        return msg
    out = _copy(msg)
    for container, _ in _containers(out):
        _resolve_in_place(container)
    return out


def _has_entries(msg) -> bool:
    return any(
        getattr(container, table.field)
        for container, _ in _containers(msg)
        for table in _TABLES
    )


def resolve_present_tables(msg):
    """:func:`resolve_detached`, skipped when ``msg`` has no detached entries.

    For this library's own hot paths: the builders and schema inference run it
    on every step, on messages that almost never carry a table. Skipping the
    check there leaves an ordinal with no table unvalidated, but nothing can
    consume one: schema inference rejects it.
    """
    return resolve_detached(msg) if _has_entries(msg) else msg


def resolve_for_building(msg):
    """:func:`resolve_present_tables`, for a message a builder is about to build on.

    A builder lifts the relation tree or the expression into a new container,
    and the tables do not travel with it. Entries that outlive resolution -- kept
    for a ``google.protobuf.Any`` payload that may reference them -- would be
    lost, leaving the payload's ordinals pointing at nothing or, inside a
    subquery, at the enclosing container's entries, so that raises
    ``ValueError`` instead.
    """
    out = resolve_present_tables(msg)
    if _has_entries(out):
        raise ValueError(
            "cannot build on a message whose detached entries an extension "
            "payload may still reference: they would not travel with it"
        )
    return out


def _resolve_in_place(container) -> None:
    tables = {table: getattr(container, table.field) for table in _TABLES}
    used = {table: set() for table in _TABLES}
    has_any = False
    stack = [child for child, _ in _children(container, skip_tables=True)]
    while stack:
        node = stack.pop()
        if _is_any(node):
            has_any = True
            continue
        table = _ordinal_table(node)
        if table is not None:
            entries = tables[table]
            ordinal = getattr(node, table.ordinal)
            if ordinal >= len(entries):
                raise ValueError(
                    f"detached {table.label} ordinal {ordinal} is out of range: the "
                    f"container has {len(entries)} detached {table.label}s"
                )
            if ordinal in used[table]:
                # With every entry inlined at most once, a cycle shows up here
                # too: following it back reaches an entry already in use.
                raise ValueError(
                    f"detached {table.label} {ordinal} is referenced more than "
                    "once, or by a cycle"
                )
            entry = entries[ordinal]
            if _ordinal_table(entry) is table:
                raise ValueError(
                    f"detached {table.label} {ordinal} is itself an ordinal "
                    f"({getattr(entry, table.ordinal)})"
                )
            used[table].add(ordinal)
            node.CopyFrom(entry)
        stack.extend(child for child, _ in _children(node))

    # An Any in an entry nothing here reached may still be live: a payload can
    # reference that entry.
    has_any = has_any or any(
        _find(entries[i], _is_any)
        for table, entries in tables.items()
        for i in range(len(entries))
        if i not in used[table]
    )
    for table, entries in tables.items():
        if not has_any:
            container.ClearField(table.field)
            continue
        while entries and len(entries) - 1 in used[table]:
            del entries[-1]
        for i in used[table]:
            if i < len(entries):
                entries[i].CopyFrom(_PLACEHOLDER)


def detach(msg, *, max_depth: int = DEFAULT_MAX_DEPTH):
    """``msg`` with its expressions nesting at most ``max_depth`` levels deep.

    ``msg`` is a ``Plan``, ``PlanRel`` or ``ExtendedExpression``; depth is counted
    in protobuf message levels below ``msg`` itself, the way parsers count it, and
    the default matches their default limit. A message with nothing to detach is
    returned itself, so its serialization is unchanged; otherwise the result is a
    copy.

    The walk goes top-down, through the existing entries first and then the
    relation or referred expressions, each in field declaration order -- the
    order substrait-java uses, so both produce the same encoding. An expression
    whose subtree would end below ``max_depth``, and which itself sits deeper than
    half the budget (and than the container's entries), is moved to the end of
    its container's ``detached_expressions`` and replaced by its ordinal; the
    moved entry is then processed from its new position, right under the
    container. Cutting at half the budget leaves chunks about half the budget
    deep rather than one entry per level past the limit. Entries come out in
    pre-order, so a child's ordinal is larger than its parent's. Entries already
    in the table keep their positions, so existing ordinals still find their
    targets.

    Only expressions are detached. Nesting inside literals, types, field
    reference paths, masks or relation trees (see ``ReferenceRel``), and inside
    ``google.protobuf.Any`` payloads, is left as is, so such a message can still
    exceed ``max_depth``: the result is best effort, since the limit belongs to
    the consumer, and some raise it.

    ``max_depth=0`` detaches every expression that can be, which is handy for
    testing a consumer against the detached form.
    """
    # Cutting works on a copy. Copying is native and cheap next to the walk, and
    # this way the walk runs only once.
    out = _copy(msg)
    cut = False
    for container, base in _containers(out):
        cut = _detach_in_place(container, base, max_depth) or cut
    return out if cut else msg


def _detach_in_place(container, base: int, max_depth: int) -> bool:
    """Cut ``container``'s over-deep subtrees; whether anything was cut."""
    tables = {table: getattr(container, table.field) for table in _TABLES}
    entry_depth = base + 1
    # Only subtrees below the entry roots are cut, so an entry root is never
    # detached again however small the budget.
    threshold = max(max_depth // 2, entry_depth)

    # Index the tree once: ``nodes[i]`` is a submessage and ``children[i]`` its
    # ``(index, levels)`` pairs. Holding every wrapper keeps the tree stable while
    # it is rewritten. The existing entries come first, then the relation tree.
    nodes, children = [], []

    def add(msg):
        nodes.append(msg)
        children.append([])
        return len(nodes) - 1

    roots = [
        (add(entry), entry_depth) for entries in tables.values() for entry in entries
    ]
    roots += [
        (add(child), base + levels)
        for child, levels in _children(container, skip_tables=True)
    ]
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
    # subtree is walked straight after it is chosen, so ``cuts`` is in pre-order
    # and each table's ordinals are handed out in that order.
    cuts = []
    next_ordinal = {table: len(entries) for table, entries in tables.items()}
    stack = [(i, depth, True) for i, depth in reversed(roots)]
    while stack:
        i, depth, is_root = stack.pop()
        node = nodes[i]
        table = _TABLE_BY_MESSAGE.get(node.DESCRIPTOR.full_name)
        if (
            table is not None
            and not is_root
            and depth > threshold
            # An ordinal is already as shallow as a subtree gets; detaching it
            # would make an entry that is itself an ordinal.
            and _ordinal_table(node) is None
        ):
            if depth + height[i] <= max_depth:
                continue
            cuts.append((i, table, next_ordinal[table]))
            next_ordinal[table] += 1
            depth = entry_depth
        stack.extend((j, depth + levels, False) for j, levels in reversed(children[i]))

    # Materialize the deepest cuts first, across tables, so each entry copies only
    # its own chunk: the cuts below it are already ordinals.
    for table, entries in tables.items():
        for _ in range(next_ordinal[table] - len(entries)):
            entries.add()
    for i, table, ordinal in reversed(cuts):
        node = nodes[i]
        tables[table][ordinal].CopyFrom(node)
        node.Clear()
        setattr(node, table.ordinal, ordinal)
    return bool(cuts)
