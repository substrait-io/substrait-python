"""Regression test for loading default extensions via a ``MultiplexedPath``.

``importlib.resources.files`` returns a ``Traversable``, not necessarily a
filesystem ``Path``. When ``substrait_extensions.extensions`` resolves as a
namespace package, CPython's resource reader returns a ``MultiplexedPath`` --
which implements ``iterdir``/``open``/``joinpath`` but *not* ``glob``. The
registry used to call ``files(...).glob("functions*.yaml")``, so in that case it
raised ``AttributeError: 'MultiplexedPath' object has no attribute 'glob'``
(observed under the pure-Python WASI guest interpreter). It now iterates with
``iterdir()`` and filters by name, which works for any ``Traversable``.
"""

from importlib.resources import files
from importlib.resources.readers import MultiplexedPath

import substrait.extension_registry.registry as registry_module
from substrait.builders.type import i8
from substrait.extension_registry import ExtensionRegistry


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

    # The default extension set was parsed and registered.
    assert reg._function_mapping
    assert reg.lookup_function(
        urn="extension:io.substrait:functions_arithmetic",
        function_name="add",
        signature=[i8(nullable=False), i8(nullable=False)],
    )
