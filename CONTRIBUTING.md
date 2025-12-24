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
This might be necessary if you are updating an existing checkout.
```
git submodule sync --recursive
git submodule update --init --recursive
```


# Code generation

You can run the full code generation using the following command or use the individual commands to selectively regenerate the generated code. This does not update the Substrait Git submodule.

```
make codegen
```

## Protobuf stubs

Run the upgrade script to upgrade the submodule and regenerate the protobuf stubs.

```
uv sync --extra gen_proto
uv run scripts/update_proto.sh <version>
```

Or run the proto codegen without updating the Substrait Git submodule:

```
make codegen-proto
```

## Antlr grammar

Substrait uses antlr grammar to derive output types of extension functions. Make sure java is installed and antlr, by using running `make setup-antlr`.

```
make antlr
```

## Extensions stubs

Substrait uses jsonschema to describe the data model for extension files.

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

# Pre-Push Checklist

Before pushing your changes, run the following command to ensure all requirements are met:

```
make pre_push
```

This command performs the following checks and updates:
1. Sets up ANTLR dependencies (`setup-antlr`)
2. Formats code with ruff (`format`)
3. Fixes linting issues with ruff (`lint_fix`)
4. Regenerates ANTLR grammar (`antlr`)
5. Regenerates extension stubs (`codegen-extensions`)
6. Syncs dependencies (`uv sync --extra test`)
7. Runs tests (`uv run pytest`)

This ensures your code is properly formatted, linted, all generated files are up-to-date, and all tests pass.
