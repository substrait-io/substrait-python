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
