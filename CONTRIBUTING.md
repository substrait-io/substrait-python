# Getting Started
## Get the repo
Fork and clone the repo.
```
git clone https://github.com/<your-fork>/substrait-python.git
cd substrait-python
```

## Development environment
Activate environment with uv.
```
uv sync --extra test
```

# Lint & Format

Run the following pixi tasks to lint and format with ruff.

```
pixi run lint
pixi run format
```

# Test
Run tests in the project's root dir.
```
uv run pytest
```

## Integration tests

`tests/integration/` holds tests that run against third-party Substrait
implementations, which release on their own schedule: pyarrow as a producer whose
output we consume, and DuckDB and DataFusion as consumers of the plans we build.

The default (`addopts` in `pyproject.toml`) deselects `duckdb` and `datafusion`, so
the command above and CI both skip them: handing a lagging consumer a plan built at a
newer spec version can crash the interpreter natively, which no test run can report,
so a red result there is not even reliably a report. **pyarrow runs by default** --
it produces rather than consumes, so it cannot take the process down, and it is the
only place that would notice pyarrow's output shape drifting away from what the
extension-anchor handling assumes.

Select with `-m`, which replaces the default rather than narrowing it:

```
uv run pytest -m integration                     # every integration test
uv run pytest -m duckdb                          # just one integration type
uv run pytest -m "integration and not duckdb"    # everything except one
```

Mind that `-m` **replaces** the default expression rather than narrowing it, so a `-m`
you meant as a restriction can widen the selection: `-m "not pyarrow"` re-enables
DuckDB and DataFusion, which is the one thing the default exists to prevent. To drop
pyarrow for a single run, skip `-m` and use `uv run pytest
--ignore=tests/integration/test_pyarrow_producer.py`; to drop it for good, add
`and not pyarrow` to the `addopts`.

Naming a path does not select a deselected marker either -- `uv run pytest
tests/integration/` still reports the engine tests as `deselected` until you pass a
`-m`.

The per-type markers are `pyarrow`, `duckdb`, and `datafusion`; each integration test
carries `integration` plus its own, so any one of them can be switched on or off
independently as those projects catch up. If a pyarrow release starts failing, add
`and not pyarrow` to the `addopts` rather than deleting the tests -- they record what
changed. New tests in `tests/integration/` need both markers, and any new marker has
to be registered in `[tool.pytest.ini_options]`.
