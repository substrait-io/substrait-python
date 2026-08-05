"""Per-build collection of plan-local extension anchors.

Extension anchors (``function_anchor``, ``extension_urn_anchor``) are *plan-local*
in Substrait: they are an artifact of serializing a plan, not durable identifiers.
The durable identity of a function is its ``(urn, name)`` pair. This module owns
the mapping between the two for the duration of a single build, which is what
keeps :class:`~substrait.extension_registry.ExtensionRegistry` free to be a pure
catalog.

Anchor 0 is an ordinary anchor here. The spec marks 0 a valid anchor/reference
(spelled out in the protos since Substrait v0.83.0), and
:func:`substrait.utils.remap_function_references` rewrites a reference of 0 like
any other, so an incoming declaration at anchor 0 is renumbered along with
the rest instead of being preserved. Emission stays 1-based, because those same
protos ask producers to "prefer non-zero values for ergonomics". That wording
covers function, type and URN anchors only -- ``type_variation_anchor`` still
reserves 0 for the system-preferred variation, so nothing here should be read as a
claim about type variations.
"""

import contextlib
import contextvars
import functools
import itertools
from typing import Optional, Union

import substrait.extended_expression_pb2 as stee
import substrait.extensions.extensions_pb2 as ste
import substrait.plan_pb2 as stplan

# Identity of a function as declared in a plan: (extension URN, function name).
# The name is the compound form carried by SimpleExtensionDeclaration (e.g.
# "add:i64_i64"), which is what makes an identity resolvable without the catalog.
# The URN is None for a declaration that names no resolvable extension URN.
FunctionIdentity = tuple[Optional[str], str]

ExtensionCarrier = Union[stplan.Plan, stee.ExtendedExpression]


def _identity_text(identity: FunctionIdentity) -> str:
    """A ``(urn, name)`` identity as it reads in an error message."""
    urn, name = identity
    return f"{name!r} (urn {urn!r})" if urn is not None else f"{name!r} (no URN)"


class ExtensionCollector:
    """Owns the plan-local extension anchors for a single build.

    Function references are allocated on first use, numbered from 1 in the order
    they are first referenced -- 0 is a reference the spec accepts but asks
    producers to avoid, so it is read on input (see :meth:`adopt`) and never
    emitted. URN anchors are *not* allocated during the build: nothing outside
    ``SimpleExtensionDeclaration`` refers to one, so they are derived in
    :meth:`write_into` from the order the declarations were collected.
    """

    def __init__(self) -> None:
        self._references: dict[FunctionIdentity, int] = {}
        self._reference_generator = itertools.count(1)

    def function_reference(self, urn: str, name: str) -> int:
        """The reference for ``(urn, name)``, allocating one on first use."""
        identity = (urn, name)
        reference = self._references.get(identity)
        if reference is None:
            reference = next(self._reference_generator)
            self._references[identity] = reference
        return reference

    def adopt(self, carrier: ExtensionCarrier) -> dict[int, int]:
        """Take over the extension declarations of an incoming plan or expression.

        Reads ``carrier``'s declarations back to ``(urn, name)`` identities and
        allocates this build's reference for each, returning the
        ``{old reference: new reference}`` remap its relations/expressions need.
        Pass the result to
        :func:`substrait.utils.remap_function_references`; it is empty (identity)
        whenever the incoming numbering already agrees with ours, which is the
        common case.

        Every incoming reference is re-derived rather than trusted, so two
        independently built inputs meeting at a multi-input relation cannot
        disagree about what a reference number means. Identities come from the
        declaration itself, so a function absent from the catalog is carried
        through unchanged rather than rejected. Anchor 0 takes part in that like any
        other anchor -- which matters for the real-world producer that motivated
        this: pyarrow's ``serialize_expressions`` numbers densely from 0 and writes
        a bare ``extension_function { name: "add" }`` naming no URN, so it identifies
        as ``(None, "add")`` and its ``function_reference: 0`` is rewritten to
        whatever this build assigns. Two such expressions folded into one build
        therefore get two distinct anchors rather than colliding at 0.

        Raises ``ValueError`` if ``carrier`` itself declares two different functions
        at one anchor: no remap can resolve a reference to that anchor, and silently
        picking one is exactly the ambiguity this collector exists to prevent.
        """
        urns_by_anchor = {u.extension_urn_anchor: u.urn for u in carrier.extension_urns}
        remap = {}
        identity_by_anchor: dict[int, FunctionIdentity] = {}
        for declaration in carrier.extensions:
            mapping_type = declaration.WhichOneof("mapping_type")
            if mapping_type != "extension_function":
                # Type / type-variation declarations are not collected yet; see
                # merge_extension_declarations for the same gap.
                raise NotImplementedError(
                    f"cannot collect extension declaration of type {mapping_type!r}; "
                    f"only 'extension_function' declarations are supported so far"
                )
            function = declaration.extension_function
            # An unresolvable URN reference still yields a usable identity: the
            # function name alone. Anchors stay collision-free either way.
            urn = urns_by_anchor.get(function.extension_urn_reference)
            identity = (urn, function.name)
            # An anchor declared twice with the same identity is merely redundant,
            # but two identities at one anchor make every reference to it ambiguous,
            # and the remap below can only send that anchor to one of them. Anchor 0
            # is checked with the rest: an expression can legitimately reference 0,
            # so two functions declared there are exactly as unresolvable as at any
            # other anchor.
            previous = identity_by_anchor.setdefault(function.function_anchor, identity)
            if previous != identity:
                raise ValueError(
                    "ambiguous extension declarations: function_anchor "
                    f"{function.function_anchor} is declared both as "
                    f"{_identity_text(previous)} and as {_identity_text(identity)} "
                    "in one input, so a reference to it names neither"
                )
            new = self.function_reference(urn, function.name)
            if new != function.function_anchor:
                remap[function.function_anchor] = new
        return remap

    def write_into(self, carrier: ExtensionCarrier) -> None:
        """Emit the collected extensions onto ``carrier``, replacing what is there.

        URN anchors are assigned here, numbered from 1 in the order the emitted
        declarations first name them, so a plan's URN anchors are as dense and
        plan-local as its function references, and declarations agreeing on a URN
        share its one anchor. A declaration whose identity named no resolvable URN
        gets no ``extension_urn_reference`` at all; because URN anchors start at 1,
        that unset field -- which reads back as 0, a value the spec does allow as a
        reference -- still matches no anchor in the emitted table, so it cannot be
        misread as naming the first URN.

        Emits function declarations only, because those are the only ones
        :meth:`adopt` collects -- it refuses a type or type-variation declaration
        rather than dropping it, so nothing reaches here that this cannot write back.
        Teaching the collector to carry those means extending both methods together:
        their anchors (``type_anchor``, ``type_variation_anchor``) are plan-local in
        the same way, so re-deriving them on the way in without emitting them here
        would lose them silently. See #247.
        """
        urn_anchors: dict[str, int] = {}
        urn_anchor_generator = itertools.count(1)

        def anchor_for_urn(urn: str) -> int:
            anchor = urn_anchors.get(urn)
            if anchor is None:
                anchor = next(urn_anchor_generator)
                urn_anchors[urn] = anchor
            return anchor

        declarations = []
        for (urn, name), reference in self._references.items():
            function = ste.SimpleExtensionDeclaration.ExtensionFunction(
                function_anchor=reference, name=name
            )
            if urn is not None:
                function.extension_urn_reference = anchor_for_urn(urn)
            declarations.append(
                ste.SimpleExtensionDeclaration(extension_function=function)
            )

        carrier.ClearField("extension_urns")
        carrier.extension_urns.extend(
            ste.SimpleExtensionURN(extension_urn_anchor=anchor, urn=urn)
            for urn, anchor in urn_anchors.items()
        )
        carrier.ClearField("extensions")
        carrier.extensions.extend(declarations)


# The ExtensionCollector for the build currently in progress, or None outside a
# build. Ambient rather than threaded through resolver signatures, following the
# other per-build state the builders already carry this way (_rel_anchor_counter
# in builders.extended_expression, outer_schemas / anchor_scope in type_inference).
_collector: contextvars.ContextVar = contextvars.ContextVar("_collector", default=None)


def current_collector() -> Optional[ExtensionCollector]:
    """The collector for the build in progress, or None outside a build."""
    return _collector.get()


def function_reference(urn: str, name: str) -> int:
    """This build's reference for the function ``(urn, name)``.

    Convenience over ``current_collector().function_reference(...)`` for builders,
    which always run inside a scope.
    """
    collector = _collector.get()
    if collector is None:
        raise RuntimeError(
            "no build in progress: extension anchors are plan-local, so a builder "
            "must resolve inside a build_scope() (builders are wrapped in "
            "build_scoped(), which enters one)"
        )
    return collector.function_reference(urn, name)


@contextlib.contextmanager
def build_scope():
    """Enter the current build, creating a collector if this is the outermost one.

    Yields ``(collector, owns_scope)``. ``owns_scope`` is True only for the
    outermost resolver of a build -- the one responsible for writing the collected
    extensions onto its output. Nested resolvers get the same collector and write
    nothing, which is what lets a build accumulate extensions once instead of
    re-merging them at every level.
    """
    collector = _collector.get()
    if collector is not None:
        yield collector, False
        return
    collector = ExtensionCollector()
    token = _collector.set(collector)
    try:
        yield collector, True
    finally:
        _collector.reset(token)


def build_scoped(resolve):
    """Wrap a builder's resolver so it participates in a build scope.

    The outermost resolver of a build writes the collected extension declarations
    onto whatever it returns; nested ones leave those fields empty for it to fill.
    Signature-agnostic, since plan resolvers take ``(registry)`` and expression
    resolvers take ``(base_schema, registry)``.
    """

    @functools.wraps(resolve)
    def wrapper(*args, **kwargs):
        with build_scope() as (collector, owns_scope):
            resolved = resolve(*args, **kwargs)
            if owns_scope:
                collector.write_into(resolved)
            return resolved

    return wrapper
