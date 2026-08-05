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
    "build_scope",
    "build_scoped",
    "current_collector",
    "function_reference",
    "FunctionType",
    "normalize_substrait_type_names",
    "_check_integer_constraint",
    "types_equal",
    "_bind_type_parameter",
    "covers",
    "UnrecognizedSubstraitTypeError",
    "UnhandledParameterizedTypeError",
]
