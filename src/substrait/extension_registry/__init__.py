"""Extension Registry module."""

from .collector import (
    ExtensionCollector,
    build_scope,
    build_scoped,
    current_collector,
    function_reference,
)
from .exceptions import UnhandledParameterizedTypeError, UnrecognizedSubstraitTypeError
from .function_entry import FunctionEntry, FunctionType
from .registry import ExtensionRegistry
from .signature_checker_helpers import (
    _bind_type_parameter,
    _check_integer_constraint,
    covers,
    normalize_substrait_type_names,
    types_equal,
)

__all__ = [
    "ExtensionCollector",
    "ExtensionRegistry",
    "FunctionEntry",
    "FunctionType",
    "UnhandledParameterizedTypeError",
    "UnrecognizedSubstraitTypeError",
    "_bind_type_parameter",
    "_check_integer_constraint",
    "build_scope",
    "build_scoped",
    "covers",
    "current_collector",
    "function_reference",
    "normalize_substrait_type_names",
    "types_equal",
]
