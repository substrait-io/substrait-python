"""Extension Registry class."""

import re
from collections import defaultdict
from importlib.resources import files as importlib_files
from pathlib import Path
from typing import Optional, Union

import yaml
from substrait.type_pb2 import Type

from substrait.simple_extension_utils import build_simple_extensions

from .function_entry import FunctionEntry, FunctionType

# Format: extension:<organization>:<name>
# Example: extension:io.substrait:functions_arithmetic
URN_PATTERN = re.compile(r"^extension:[^:]+:[^:]+$")


class ExtensionRegistry:
    """A catalog of extension functions, keyed by URN.

    Plan-independent: the registry knows which functions exist and what signatures
    they accept, but assigns no anchors. Extension anchors are plan-local in
    Substrait, so they belong to a single build rather than to the catalog -- see
    :class:`~substrait.extension_registry.ExtensionCollector`.
    """

    def __init__(self, load_default_extensions=True) -> None:
        self._urns: set = set()
        self._function_mapping: dict = defaultdict(lambda: defaultdict(list))
        # {type_url: detail class} for user-defined extension relations, so an
        # extension relation's output schema can be derived during inference.
        self._extension_relations: dict = {}
        if load_default_extensions:
            for fpath in importlib_files("substrait_extensions.extensions").glob(  # type: ignore
                "functions*.yaml"
            ):
                self.register_extension_yaml(fpath)

    def register_extension_yaml(
        self,
        fname: Union[str, Path],
    ) -> None:
        """Register extensions from a YAML file.
        Args:
            fname: Path to the YAML file
        """
        fname = Path(fname)
        with open(fname) as f:  # type: ignore
            extension_definitions = yaml.safe_load(f)
        self.register_extension_dict(extension_definitions)

    def register_extension_relation(self, detail_cls) -> None:
        """Register an extension-relation detail class (by its ``type_url``).

        Enables schema inference for ``ExtensionLeaf/Single/MultiRel`` built with
        an instance of ``detail_cls``: inference reconstructs the detail from the
        plan's ``Any`` and calls its ``derive_schema``. See
        :mod:`substrait.dataframe.extension_relations`. Registration is scoped to
        this ``ExtensionRegistry`` instance, so inference must be given this same
        registry (as it is when a plan is built or re-inferred through it).
        """
        self._extension_relations[detail_cls.type_url] = detail_cls

    def lookup_extension_relation(self, type_url: str):
        """The extension-relation detail class registered for ``type_url``, or None."""
        return self._extension_relations.get(type_url)

    def register_extension_dict(self, definitions: dict) -> None:
        """Register extensions from a dictionary (parsed YAML).
        Args:
            definitions: The extension definitions dictionary
        """
        unverified_urn = definitions.get("urn")
        if not unverified_urn:
            raise ValueError("Extension definitions must contain a 'urn' field")
        urn = validate_urn_format(unverified_urn)
        self._urns.add(urn)
        simple_extensions = build_simple_extensions(definitions)

        # Helper to register functions by type
        def register_functions_by_type(
            functions_list: list, func_type: FunctionType
        ) -> None:
            if not functions_list:
                return

            for function in functions_list:
                self._function_mapping[urn][function.name].extend(
                    [
                        FunctionEntry(
                            urn=urn,
                            name=function.name,
                            impl=impl,
                            function_type=func_type,
                        )
                        for impl in function.impls
                    ]
                )

        # Register each function type
        register_functions_by_type(
            simple_extensions.scalar_functions or [], FunctionType.SCALAR
        )
        register_functions_by_type(
            simple_extensions.aggregate_functions or [], FunctionType.AGGREGATE
        )
        register_functions_by_type(
            simple_extensions.window_functions or [], FunctionType.WINDOW
        )

    def _find_matching_functions(
        self,
        function_name: str,
        signature: tuple[Type] | list[Type],
        urns: list[str] | None = None,
    ) -> list[tuple[FunctionEntry, Type]]:
        """Helper method to find matching functions across specified URNs."""
        matches = []
        urns_to_search = (
            urns if urns is not None else list(self._function_mapping.keys())
        )
        for urn in urns_to_search:
            if (
                urn not in self._function_mapping
                or function_name not in self._function_mapping[urn]
            ):
                continue
            functions = self._function_mapping[urn][function_name]
            for f in functions:
                rtn = f.satisfies_signature(signature)
                if rtn is not None:
                    matches.append((f, rtn))
        return matches

    # TODO add an optional return type check
    def lookup_function(
        self,
        urn: str,
        function_name: str,
        signature: tuple[Type] | list[Type],
    ) -> Optional[tuple[FunctionEntry, Type]]:
        """Look up a function within a specific URN."""
        matches = self._find_matching_functions(function_name, signature, [urn])
        return matches[0] if matches else None

    def list_functions(
        self, urn: str, function_name: str, signature: tuple[Type] | list[Type]
    ) -> list[tuple[FunctionEntry, Type]]:
        """List all matching functions within a specific URN."""
        return self._find_matching_functions(function_name, signature, [urn])

    def list_functions_across_urns(
        self, function_name: str, signature: tuple[Type] | list[Type]
    ) -> list[tuple[FunctionEntry, Type]]:
        """List all matching functions across all URNs."""
        return self._find_matching_functions(function_name, signature)

    def find_function(
        self,
        function_name: str,
        signature: tuple[Type] | list[Type],
        urns: Optional[list[str]] = None,
    ) -> Optional[tuple[FunctionEntry, Type]]:
        """Find the best-matching function for ``function_name`` across ``urns``.

        Searches ``urns`` in order (every registered URN when ``None``) and returns
        the first ``(FunctionEntry, output_type)`` whose overload satisfies
        ``signature``, or ``None``. The winning extension URN is ``entry.urn``.

        Generalizes :meth:`lookup_function` (a single URN) and
        :meth:`list_functions_across_urns` (every URN) to an ordered subset, so a
        caller resolving a name that lives in several extensions -- preferring, say,
        the base arithmetic extension over its decimal variant -- needs one call
        rather than a per-URN ``lookup_function`` loop.
        """
        matches = self._find_matching_functions(function_name, signature, urns)
        return matches[0] if matches else None

    def has_urn(self, urn: str) -> bool:
        """Whether ``urn`` has been registered."""
        return urn in self._urns

    def urns(self) -> "list[str]":
        """The registered extension URNs, sorted lexicographically."""
        return sorted(self._urns)

    def iter_functions(self):
        """Yield ``(urn, name, function_type)`` for every registered function.

        One tuple per ``(urn, name)`` group (overloads are collapsed). Useful for
        discovering the full set of available functions, e.g. to build a
        function-helper namespace.
        """
        for urn, names in self._function_mapping.items():
            for name, entries in names.items():
                if entries:
                    yield urn, name, entries[0].function_type


def validate_urn_format(urn: str) -> str:
    """Validate that a URN follows the expected format.
    Expected format: extension:<organization>:<name>
    Example: extension:io.substrait:functions_arithmetic
    Args:
        urn: The URN to validate
    Raises:
        ValueError: If the URN format is invalid
    """
    if not URN_PATTERN.match(urn):
        raise ValueError(
            f"Invalid URN format: '{urn}'. "
            f"Expected format: extension:<organization>:<name> "
            f"(e.g., 'extension:io.substrait:functions_arithmetic')"
        )
    return urn
