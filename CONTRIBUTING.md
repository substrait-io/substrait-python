# Getting Started
## Get the repo
Fork and clone the repo.
```
git clone --recursive https://github.com/<your-fork>/substrait-python.git
cd substrait-python
```

## Development environment
Activate environment with uv.
```
uv sync --extra test
```

## Update the substrait submodule locally
You can run update-submodule task to pull in latest substrait from upstream.
```
pixi run update-submodule <version>
```

Or you can update submodule and run code generation at the same time with
```
pixi run update-substrait
```

This might be necessary if you are updating an existing checkout.
```
git submodule sync --recursive
git submodule update --init --recursive
```

# Code generation

You can run the full code generation using the following command or use the individual commands to selectively regenerate the generated code. This does not update the Substrait Git submodule. You can use pixi environment defined in pyproject.toml which contains all dependencies needed for code generation.

```
pixi run codegen
```

## Extension Copying

Copy the core function extensions into substrait-python

```
pixi run copy-extensions
```

## Antlr grammar

Substrait uses antlr grammar to derive output types of extension functions. Make sure java is installed and ANTLR_JAR environment variable is set. Take a look at .devcontainer/Dockerfile for example setup.

```
pixi run antlr
```

## Extensions stubs

Substrait uses jsonschema to describe the data model for extension files.

```
pixi run codegen-extensions
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
