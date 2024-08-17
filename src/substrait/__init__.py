try:
    from ._version import __version__  # noqa: F401
except ImportError:
    pass

__substrait_version__ = "0.54.0"
__substrait_hash__ = "93c8339"
__minimum_substrait_version__ = "0.30.0"
