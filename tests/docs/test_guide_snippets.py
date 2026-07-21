"""Execute every documentation guide script.

The pages under ``docs/`` do not contain code inline: each ``python`` fence is a
``pymdownx.snippets`` include (``--8<-- "examples/guide/<page>.py:section"``)
pulling from a runnable script in ``examples/guide/``. Rendering those pages
(``zensical build``) only *includes* the code -- it never runs it -- so a snippet
that goes stale against the API would render fine while being broken.

This test closes that gap: it runs every ``examples/guide/*.py`` script end to
end, so a documented example that no longer builds a valid plan fails CI instead
of silently shipping. ``check_paths = true`` in ``zensical.toml`` separately
guarantees the ``--8<--`` paths and section names still resolve.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE_DIR = REPO_ROOT / "examples" / "guide"

GUIDE_SCRIPTS = sorted(GUIDE_DIR.glob("*.py"))


def test_guide_scripts_are_discovered():
    """Guard against silently testing nothing if the directory moves/empties."""
    assert GUIDE_SCRIPTS, f"no guide scripts found under {GUIDE_DIR}"


@pytest.mark.parametrize("script", GUIDE_SCRIPTS, ids=lambda p: p.name)
def test_guide_script_runs(script: Path):
    """Each guide script must execute cleanly (exit 0) against the real API."""
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"{script.relative_to(REPO_ROOT)} failed (exit {result.returncode}).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
