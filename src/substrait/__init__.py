try:
    from ._version import __version__  # noqa: F401
except ImportError:
    pass

__substrait_version__ = "0.52.0"
__substrait_hash__ = "a68c1ac"
__minimum_substrait_version__ = "0.30.0"
