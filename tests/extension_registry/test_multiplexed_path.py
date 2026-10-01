"""Regression tests for loading default extensions off a non-``Path`` resource.

``importlib.resources.files`` returns a ``Traversable``, not necessarily a
filesystem ``Path``. The registry must load the bundled extension YAMLs
regardless of which concrete ``Traversable`` the resource reader hands back:

* ``MultiplexedPath`` -- returned for a *namespace* package (no ``__init__.py``).
  It implements ``iterdir``/``open``/``joinpath`` but *not* ``glob``, so the old
  ``files(...).glob("functions*.yaml")`` raised
  ``AttributeError: 'MultiplexedPath' object has no attribute 'glob'`` (observed
  under the pure-Python WASI guest interpreter).
* ``zipfile.Path`` -- returned for a zip-imported package. It is not an
  ``os.PathLike``, so ``register_extension_yaml``'s ``Path(fname)`` raised
  ``TypeError``; ``as_file`` now materialises a real path first.
"""

import zipfile
from importlib.resources import files

import substrait.extension_registry.registry as registry_module
from substrait.builders.type import i8
from substrait.extension_registry import ExtensionRegistry

try:  # Python 3.11+
    from importlib.resources.readers import MultiplexedPath
except ModuleNotFoundError:  # Python 3.10
    from importlib.readers import MultiplexedPath


def _assert_defaults_loaded(reg: ExtensionRegistry) -> None:
    """The default extension set was parsed and registered."""
    assert reg._function_mapping
    assert reg.lookup_function(
        urn="extension:io.substrait:functions_arithmetic",
        function_name="add",
        signature=[i8(nullable=False), i8(nullable=False)],
    )


def test_load_default_extensions_via_multiplexed_path(monkeypatch):
    # Wrap the real extensions directory in a MultiplexedPath so ``files()``
    # yields exactly what it would for a namespace package. Guard the premise:
    # MultiplexedPath must not expose ``glob`` (otherwise this test proves
    # nothing).
    ext_dir = files("substrait_extensions.extensions")
    multiplexed = MultiplexedPath(ext_dir)
    assert not hasattr(multiplexed, "glob")

    monkeypatch.setattr(registry_module, "importlib_files", lambda _pkg: multiplexed)

    # Previously raised AttributeError here; must now load cleanly.
    reg = ExtensionRegistry(load_default_extensions=True)
    _assert_defaults_loaded(reg)


def test_load_default_extensions_via_zipfile_path(monkeypatch, tmp_path):
    # Mirror a zip-imported install: copy the real YAMLs into a zip and resolve
    # ``files()`` to a zipfile.Path over the archive. The entries are not
    # os.PathLike, so register_extension_yaml's ``Path(fname)`` would raise
    # TypeError without the ``as_file`` materialisation.
    ext_dir = files("substrait_extensions.extensions")
    archive = tmp_path / "substrait_extensions.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for child in ext_dir.iterdir():
            if child.name.endswith(".yaml"):
                zf.writestr(f"extensions/{child.name}", child.read_bytes())

    zip_dir = zipfile.Path(archive, "extensions/")
    monkeypatch.setattr(registry_module, "importlib_files", lambda _pkg: zip_dir)

    # Previously raised TypeError in register_extension_yaml; must now load.
    reg = ExtensionRegistry(load_default_extensions=True)
    _assert_defaults_loaded(reg)
