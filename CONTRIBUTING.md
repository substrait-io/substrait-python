# Getting Started
## Get the repo
Fork and clone the repo.
```
git clone https://github.com/<your-fork>/substrait-python.git
cd substrait-python
```

## Development environment
Set up the environment with uv. This installs the default `dev` dependency
group, which includes everything needed to run the tests.
```
uv sync
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

# Documentation
The user guide lives in `docs/` and is built with [Zensical](https://zensical.org);
the API reference under `docs/reference/` is generated from the package
docstrings via mkdocstrings. Configuration is in `zensical.toml`.

Preview it locally with live reload, or build the static site into `./site`:
```
pixi run docs-serve   # or: uv run --group docs zensical serve
pixi run docs-build   # or: uv run --group docs zensical build
```

When editing docstrings that appear in the reference, prefer Markdown (fenced
code blocks and backticked names) over reStructuredText so they render cleanly.
Every pull request runs a docs build-check; versioned docs are published to
GitHub Pages on release (see `.github/workflows/docs-deploy.yml`).
