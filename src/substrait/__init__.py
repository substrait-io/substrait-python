try:
    from ._version import __version__  # noqa: F401
except ImportError:
    pass

__substrait_version__ = "0.66.1"
__substrait_hash__ = "ff013aa"
__minimum_substrait_version__ = "0.30.0"
