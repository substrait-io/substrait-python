try:
    from ._version import __version__  # noqa: F401
except ImportError:
    pass

__substrait_version__ = "0.42.0"
__substrait_hash__ = "3251b1f"
__minimum_substrait_version__ = "0.30.0"
