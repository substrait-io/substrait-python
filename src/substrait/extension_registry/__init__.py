"""Extension Registry module."""

from .registry import ExtensionRegistry
from .function_entry import FunctionEntry, FunctionType
from .signature_checker_helpers import (
    normalize_substrait_type_names,
    _check_integer_constraint,
    types_equal,
    _bind_type_parameter,
    covers,
)
from .exceptions import UnrecognizedSubstraitTypeError, UnhandledParameterizedTypeError

__all__ = [
    "ExtensionRegistry",
    "FunctionEntry",
    "FunctionType",
    "normalize_substrait_type_names",
    "_check_integer_constraint",
    "types_equal",
    "_bind_type_parameter",
    "covers",
    "UnrecognizedSubstraitTypeError",
    "UnhandledParameterizedTypeError",
]
