"""Extension Registry class."""

import itertools
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
    def __init__(self, load_default_extensions=True) -> None:
        self._urn_mapping: dict = defaultdict(dict)  # URN -> anchor ID
        self._urn_id_generator = itertools.count(1)
        self._function_mapping: dict = defaultdict(lambda: defaultdict(list))
        self._id_generator = itertools.count(1)
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

    def register_extension_dict(self, definitions: dict) -> None:
        """Register extensions from a dictionary (parsed YAML).
        Args:
            definitions: The extension definitions dictionary
        """
        unverified_urn = definitions.get("urn")
        if not unverified_urn:
            raise ValueError("Extension definitions must contain a 'urn' field")
        urn = validate_urn_format(unverified_urn)
        self._urn_mapping[urn] = next(self._urn_id_generator)
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
                            anchor=next(self._id_generator),
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

    def lookup_urn(self, urn: str) -> Optional[int]:
        return self._urn_mapping.get(urn, None)


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
