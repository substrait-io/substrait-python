"""Named function helpers, generated from the loaded extension registry.

``f`` is a namespace covering *every* function defined by the Substrait default
extensions -- scalar, aggregate and window -- so anything the specification
ships is reachable by name and hides the extension-URN / signature plumbing::

    import substrait.api as sub

    sub.f.sum(sub.col("amount"))
    sub.f.substring(sub.col("name"), 1, 3)
    sub.f.coalesce(sub.col("a"), sub.col("b"))
    sub.f.row_number()

Each helper returns an :class:`~substrait.expr.Expr`. The namespace is built
lazily on first attribute access from :func:`substrait.frame.default_registry`,
and supports ``dir(sub.f)`` for discovery/tab-completion.

Some function names appear in more than one extension (e.g. ``add`` in
``functions_arithmetic``, ``functions_arithmetic_decimal`` and
``functions_datetime``). For those, the correct extension is chosen at resolve
time from the actual argument types, preferring the base extension over its
``decimal``/``approx`` variants. The three names that are Python keywords
(``and``/``or``/``not``) are exposed as ``and_``/``or_``/``not_`` (and remain
reachable via ``getattr(sub.f, "and")``).

Note: operators (``+``, ``>``, ...) coerce bare Python literals to the peer
column's type; the explicit ``f.*`` helpers do not, so pass typed operands
(``2.0``, ``sub.lit(...)``) or a column when a specific overload is required.
"""

from __future__ import annotations

import keyword
from collections import defaultdict
from typing import Any

from substrait.builders.extended_expression import (
    aggregate_function,
    resolve_expression,
    scalar_function,
    window_function,
)
from substrait.expr import Expr
from substrait.extension_registry.function_entry import FunctionType
from substrait.type_inference import infer_extended_expression_schema

_BUILDERS = {
    FunctionType.SCALAR: scalar_function,
    FunctionType.AGGREGATE: aggregate_function,
    FunctionType.WINDOW: window_function,
}


def _safe_name(name: str) -> str:
    return f"{name}_" if keyword.iskeyword(name) else name


def _urn_priority(urn: str) -> int:
    """Rank base extensions ahead of their decimal/approx variants."""
    tail = urn.rsplit(":", 1)[-1]
    return (2 if "approx" in tail else 0) + (1 if "decimal" in tail else 0)


def _single_urn_helper(builder, urn: str, name: str):
    def helper(*args: Any, alias: str | None = None) -> Expr:
        exprs = [Expr._coerce(a).unbound for a in args]
        return Expr(builder(urn, name, expressions=exprs, alias=alias))

    return helper


def _multi_urn_helper(builder, urns: list[str], name: str):
    def helper(*args: Any, alias: str | None = None) -> Expr:
        exprs = [Expr._coerce(a).unbound for a in args]

        def resolve(base_schema, registry):
            bound = [resolve_expression(e, base_schema, registry) for e in exprs]
            signature = [
                typ for b in bound for typ in infer_extended_expression_schema(b).types
            ]
            for urn in urns:
                if registry.lookup_function(urn, name, signature):
                    return builder(urn, name, expressions=bound, alias=alias)(
                        base_schema, registry
                    )
            kinds = [t.WhichOneof("kind") for t in signature]
            raise Exception(
                f"No matching overload for '{name}' across {urns} "
                f"with signature {kinds}"
            )

        return Expr(resolve)

    return helper


def _build_functions(registry) -> dict:
    grouped: dict = defaultdict(lambda: [None, []])  # name -> [function_type, urns]
    for urn, name, ftype in registry.iter_functions():
        grouped[name][0] = ftype
        grouped[name][1].append(urn)

    fns: dict = {}
    for name, (ftype, urns) in grouped.items():
        builder = _BUILDERS[ftype]
        urns = sorted(urns, key=lambda u: (_urn_priority(u), urns.index(u)))
        if len(urns) == 1:
            helper = _single_urn_helper(builder, urns[0], name)
        else:
            helper = _multi_urn_helper(builder, urns, name)
        helper.__name__ = _safe_name(name)
        helper.__doc__ = (
            f"Substrait {ftype.value} function '{name}' "
            f"(extensions: {', '.join(urns)})."
        )
        key = _safe_name(name)
        fns[key] = helper
        if key != name:  # keep the raw keyword name reachable via getattr
            fns[name] = helper
    return fns


class _FunctionNamespace:
    """Lazily-populated namespace of a registry's functions.

    With no registry it enumerates the default extensions; pass a registry (see
    :func:`functions_for`) to expose custom extensions registered on it too.
    """

    def __init__(self, registry=None):
        object.__setattr__(self, "_registry", registry)
        object.__setattr__(self, "_fns", None)

    def _ensure(self) -> dict:
        if self._fns is None:
            registry = self._registry
            if registry is None:
                from substrait.frame import default_registry

                registry = default_registry()
            object.__setattr__(self, "_fns", _build_functions(registry))
        return self._fns

    def __getattr__(self, item: str):
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        fns = self._ensure()
        try:
            return fns[item]
        except KeyError:
            raise AttributeError(f"no Substrait function named {item!r}") from None

    def __contains__(self, item: str) -> bool:
        return item in self._ensure()

    def __dir__(self):
        return sorted(self._ensure())


def functions_for(registry) -> _FunctionNamespace:
    """A function namespace bound to ``registry``.

    Unlike the global ``f`` (which only knows the default extensions), this
    surfaces every function on ``registry`` -- including custom extensions
    registered via ``register_extension_yaml`` / ``register_extension_dict``::

        reg = ExtensionRegistry(load_default_extensions=True)
        reg.register_extension_yaml("my_functions.yaml")
        myf = sub.functions_for(reg)
        myf.my_double(sub.col("x"))
    """
    return _FunctionNamespace(registry)


f = _FunctionNamespace()
