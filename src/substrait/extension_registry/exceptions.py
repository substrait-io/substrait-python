# Custom exceptions
#
class UnrecognizedSubstraitTypeError(Exception):
    """Raised when an unrecognized Substrait type is encountered."""


class UnhandledParameterizedTypeError(Exception):
    """Raised when an unhandled ANTLR parameterized type context is encountered."""
