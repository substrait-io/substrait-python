# Getting Started
## Get the repo
Fork and clone the repo.
```
git clone --recursive https://github.com/<your-fork>/substrait-python.git
cd substrait-python
```

## Development environment
Activate environmen with uv.
```
uv sync --extra test
```

## Update the substrait submodule locally
This might be necessary if you are updating an existing checkout.
```
git submodule sync --recursive
git submodule update --init --recursive
```


# Code generation

## Protobuf stubs

Run the upgrade script to upgrade the submodule and regenerate the protobuf stubs.

```
uv sync --extra gen_proto
uv run ./update_proto.sh <version>
```

## Antlr grammar

Substrait uses antlr grammar to derive output types of extension functions. Make sure java is installed and ANTLR_JAR environment variable is set. Take a look at .devcontainer/Dockerfile for example setup.

```
make antlr
```

## Extensions stubs

Substrait uses jsonschema to describe data model for extension files.

```
make codegen-extensions
```

# Lint & Format

Run the following make commands to lint and format with ruff.

```
make lint
make format
```

# Test
Run tests in the project's root dir.
```
uv sync --extra test
uv run pytest
```
