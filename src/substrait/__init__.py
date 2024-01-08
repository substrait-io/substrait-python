try:
    from ._version import __version__  # noqa: F401
except ImportError:
    pass

__substrait_version__ = "0.41.0"
__substrait_hash__ = "c7d7e9c"
__minimum_substrait_version__ = "0.30.0"
