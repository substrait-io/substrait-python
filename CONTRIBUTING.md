# Contributing to Substrait Python

This page provides some orientation and recommendations on how to get the best results when engaging with the community.

1. [Contributor License Agreement](#contributor-license-agreement)
2. [The specification is the source of truth](#the-specification-is-the-source-of-truth)
3. [Getting started](#getting-started)
4. [Lint & format](#lint--format)
5. [Testing](#testing)
6. [Commit conventions](#commit-conventions)
7. [Pull requests](#pull-requests)

## Contributor License Agreement

Substrait requires all contributors to sign the [Contributor License Agreement (CLA)](https://cla-assistant.io/substrait-io/substrait) before their contributions can be merged. A GitHub app checks this on every pull request and guides new contributors through signing it.

## The specification is the source of truth

Substrait Python is an implementation of the [Substrait specification](https://substrait.io/); it does not define Substrait semantics. Review behavioral changes against the spec — the spec text and the `.proto` comments in [`substrait-io/substrait`](https://github.com/substrait-io/substrait) for the version this tree targets.

That version is pinned by the `substrait-protobuf`, `substrait-extensions` and `substrait-antlr` requirements in [`pyproject.toml`](pyproject.toml), which is also where the proto bindings, the standard extension YAMLs and the ANTLR grammar come from — none of them are vendored here. The three are kept in lockstep by [`check_substrait_package_versions.sh`](check_substrait_package_versions.sh) (run in CI by [`version-checks.yml`](.github/workflows/version-checks.yml)), and the version they agree on is what `substrait.version.substrait_version` reports at runtime.

Where the spec is genuinely unclear, don't settle it here. Survey the ecosystem for an existing consensus first. The closest comparison is the sibling language bindings listed under [Active Libraries](https://substrait.io/community/active_libraries/) — `substrait-go`, `substrait-java` and `substrait-rs` solve the same modeling problem at the same layer, so how they represent a construct is directly relevant; that page also separates active bindings from inactive ones, and an inactive binding's choice is weaker evidence. For questions about runtime semantics rather than modeling, the engines under [Powered by Substrait](https://substrait.io/community/powered_by/) (Acero, DataFusion, DuckDB, Gluten, Velox) are the better reference.

If they agree, follow that de facto consensus and say so in the PR. If they disagree, or none of them cover the case, raise a clarification issue in [`substrait-io/substrait`](https://github.com/substrait-io/substrait/issues) or bring it to the [community](https://substrait.io/community/) channels rather than encoding a guess — and record the open question in the PR so the assumption stays reviewable.

## Getting started

### Get the repo

Fork and clone the repo.

```
git clone https://github.com/<your-fork>/substrait-python.git
cd substrait-python
```

### Development environment

Create the environment with [uv](https://docs.astral.sh/uv/).

```
uv sync
```

That is enough to run the full test suite: the `dev` dependency group, which carries `pytest` along with the optional runtime dependencies the tests exercise (`substrait-antlr`, `pyyaml`, `sqloxide`, `deepdiff`, `duckdb`, `datafusion`), is synced by default.

The two extras exist for consumers of the published package rather than for development, and can be added with `uv sync --extra <name>`:

* **`extensions`** — `substrait-antlr` and `pyyaml`, needed for the extension registry to resolve function overloads against the standard Substrait extensions.
* **`sql`** — `sqloxide` and `deepdiff`, needed by the `substrait.sql` front end.

## Lint & format

Run the following pixi tasks to lint and format with ruff.

```
pixi run lint
pixi run format
```

Both are checked in CI, where the formatter runs as `pixi run format --check`. Use the pixi tasks rather than a separately installed ruff: the version is pinned under `[tool.pixi.dependencies]` in [`pyproject.toml`](pyproject.toml), and a different one may disagree about formatting. There is also a [`pre-commit`](https://pre-commit.com/) config wiring the same ruff lint and format hooks, if you prefer to have them run on commit.

## Testing

Run tests in the project's root dir.

```
uv run pytest
```

Narrow the run with a path or `-k` while iterating, e.g. `uv run pytest tests/dataframe -k lateral`.

A clean run does not cover everything: the round-trips through DuckDB and DataFusion are left out by default, because those consumers lag the pinned spec. `pytest` reports them as `deselected` rather than as skips — see [Integration tests](#integration-tests) below for how to opt in.

The [examples](examples) run standalone, e.g. `uv run examples/builder_example.py`. CI runs four of them — `builder`, `duckdb`, `adbc`, `pyarrow` — on every PR ([`example.yml`](.github/workflows/example.yml)); `dataframe_example.py` and `narwhals_example.py` are outside that matrix, so changes to the DataFrame or Narwhals layers need those run by hand. Several examples are [PEP 723](https://peps.python.org/pep-0723/) scripts (a `# /// script` block declaring their own dependencies), which `uv run` executes in a separate environment built from the working tree rather than in your synced `.venv`.

Tests run in CI ([`test.yml`](.github/workflows/test.yml)) as `uv run --frozen pytest` across Python 3.10–3.13 on Linux, macOS and Windows. Because of `--frozen`, a change to dependencies has to land together with a regenerated [`uv.lock`](uv.lock) — and [`pixi.lock`](pixi.lock) when it affects the lint environment — or CI will fail on the stale lock file rather than on your change.

### Integration tests

[`tests/integration`](tests/integration) holds the tests that run against third-party Substrait implementations, which release on their own schedule: pyarrow as a producer whose output this library consumes, and DuckDB and DataFusion as consumers of the plans it builds.

The default (`addopts` in [`pyproject.toml`](pyproject.toml)) deselects `duckdb` and `datafusion`, so a plain `uv run pytest` — and CI — leaves them out: handing a lagging consumer a plan built at a newer spec version can crash the interpreter natively, which no test run can report, so a red result there is not even reliably a report. **pyarrow runs by default** — it produces rather than consumes, so it cannot take the process down, and it is the only place that would notice pyarrow's output shape drifting away from what the extension-anchor handling assumes.

Select with `-m`:

```
uv run pytest -m integration                     # every integration test
uv run pytest -m duckdb                          # just one integration type
uv run pytest -m "integration and not duckdb"    # everything except one
```

Mind that `-m` **replaces** the default expression rather than narrowing it, so a `-m` you meant as a restriction can widen the selection: `-m "not pyarrow"` re-enables DuckDB and DataFusion, which is the one thing the default exists to prevent. To drop pyarrow for a single run, skip `-m` and use `uv run pytest --ignore=tests/integration/test_pyarrow_producer.py`; to drop it for good, add `and not pyarrow` to the `addopts`. Naming a path does not select a deselected marker either — `uv run pytest tests/integration/` still reports the engine tests as `deselected` until you pass a `-m`.

The per-type markers are `pyarrow`, `duckdb`, and `datafusion`; each integration test carries `integration` plus its own, so any one of them can be switched on or off independently as those projects catch up. If a pyarrow release starts failing, add `and not pyarrow` to the `addopts` rather than deleting the tests — they record what changed. New tests in `tests/integration/` need both markers, and any new marker has to be registered in `[tool.pytest.ini_options]`.

## Commit conventions

Substrait Python follows [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/) for commit message structure, and releases are automated from it (see [RELEASING.md](RELEASING.md)). Because pull requests are squash-merged, the message that ends up in history is built from the PR rather than from your local commits: please ensure that your PR title and description together form a valid commit message. The [PR Title Check](.github/workflows/pr_title.yml) workflow lints exactly that pair with commitlint and comments on the PR when it does not conform.

Examples of commit messages can be seen [here](https://www.conventionalcommits.org/en/v1.0.0/#examples).

## Pull requests

Pull requests are squash-merged, and the **PR title and description become the commit message** that `semantic-release` parses to build [`CHANGELOG.md`](CHANGELOG.md) and the release notes. The title is the subject and the description is the body. [`.github/pull_request_template.md`](.github/pull_request_template.md) restates that where you write the description.

Because the description is changelog input rather than a review scratchpad, leave out anything the diff and the CI checks already show:

* **Lists of files touched** — they are in the diff.
* **Claims that CI-verified things pass** — "tests pass", "ruff clean". If they didn't, the checks would be red.
* **Process notes that are already implicit** — "opened as draft pending review".

Do include the rationale, and for spec-tracking changes the spec version (e.g. `spec v0.99.0`). Keep the body free of git trailers (`Signed-off-by:`, `Co-authored-by:`) and tool-attribution lines; this project's history does not carry them.

### Breaking changes

Mark a breaking change twice: with `!` after the type and scope in the title (`feat!: …`), and with a `BREAKING CHANGE:` footer in the description. The `!` drives the version bump; the footer text is what populates the ⚠ BREAKING CHANGES section of the release notes, so describe what breaks and what consumers should do instead. Only a real footer counts — breaking-change prose under a `## Breaking change` heading is ordinary body text, and the note then degrades to a bare repeat of the subject line, which tells consumers nothing about how to migrate.

Keep that footer **last, with nothing after it** — below the rationale and below any `Closes #NNN` line. The conventional-commits parser ends a `BREAKING CHANGE` note only at another footer keyword or an issue reference; anything else trailing it, whether prose, an attribution line, or a stray comment marker, is absorbed into the note and published verbatim. ([`.releaserc.mjs`](.releaserc.mjs) strips trailing git trailers such as `Signed-off-by:` for exactly this reason, but it matches only `Key: value` trailers, so it cannot recognize prose.) Putting the footer last also means the squash-merge message can be trimmed to just the subject and the footer in a single cut.

Write the footer as unwrapped paragraphs. GitHub renders a single newline as a line break, so a hard-wrapped footer reaches the release notes broken mid-sentence.

Note that this project is pre-1.0: a breaking change produces a **minor** bump, not a major one, matching the [Substrait versioning policy](https://substrait.io/spec/versioning/) and substrait-java. See [RELEASING.md](RELEASING.md) for the rest of the release process.
