try:
    from ._version import __version__  # noqa: F401
except ImportError:
    pass

__substrait_version__ = "0.42.1"
__substrait_hash__ = "4734478"
__minimum_substrait_version__ = "0.30.0"
