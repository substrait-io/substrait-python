try:
    from ._version import __version__  # noqa: F401
except ImportError:
    pass

__substrait_version__ = "0.56.0"
__substrait_hash__ = "bc4d6fb"
__minimum_substrait_version__ = "0.30.0"
