try:
    from ._version import __version__  # noqa: F401
except ImportError:
    pass

__substrait_version__ = "0.44.0"
__substrait_hash__ = "2e12da1"
__minimum_substrait_version__ = "0.30.0"
