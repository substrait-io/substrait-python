# AGENTS.md

Entry point for AI agents working in the `substrait-python` repository. Read the shared,
human-facing docs first, then keep the notes below in mind.

## Start here

- **[`README.md`](README.md)** — what the project is, the DataFrame API, and the lower-level
  `substrait.proto` / `substrait.builders` layers.
- **[`CONTRIBUTING.md`](CONTRIBUTING.md)** — how the spec relates to this repo, the development
  environment, the lint / format / test command mechanics, and the commit and PR conventions.

This repo *implements* the Substrait spec; it does not define it. Read
[the specification is the source of truth](CONTRIBUTING.md#the-specification-is-the-source-of-truth)
before changing behavior. The failure mode to avoid is filling a gap in the spec with something
plausible and then describing it as spec-defined. When you cannot find the spec's answer, say so
explicitly instead of picking one silently: check the sibling bindings listed at
[Active Libraries](https://substrait.io/community/active_libraries/) for an existing consensus, and
surface what is still unresolved in the PR.

The proto bindings, the standard extension YAMLs, and the ANTLR grammar are **not** vendored here —
they come from the `substrait-protobuf`, `substrait-extensions`, and `substrait-antlr`
distributions pinned in [`pyproject.toml`](pyproject.toml), which is what ties this tree to a spec
version (reported at runtime by `substrait.version.substrait_version`). Changing one of those
inputs means changing the spec, not this repo.

## Conventions & workflow

- **Keep PR descriptions high-signal.** The PR title and body together become the squash-merge
  commit message that `semantic-release` uses to build [`CHANGELOG.md`](CHANGELOG.md) — the body is
  changelog input, not a review scratchpad. Follow
  [`CONTRIBUTING.md`](CONTRIBUTING.md#pull-requests) rather than
  [`.github/pull_request_template.md`](.github/pull_request_template.md), which a PR opened with an
  explicitly supplied body never shows you. Beyond forming a valid conventional commit, leave out
  the noise agents tend to add:
  - **Lists of files touched** — they're in the diff.
  - **Claims that CI-verified things pass** — e.g. "tests pass", "ruff clean". If they didn't, the
    checks would be red.
  - **Process notes that are already implicit** — e.g. "opened as draft pending review".

  Do include the rationale, and for spec-tracking changes the spec version (e.g. `spec v0.99.0`).
  Keep commit bodies free of git trailers (`Signed-off-by`, `Co-authored-by`, tool-attribution
  lines) — `semantic-release` builds the changelog from the commit message, and history here does
  not carry them.
- **A `BREAKING CHANGE:` footer goes last, with nothing after it**, and the title gets a `!`
  (`feat!: …`). The footer text *is* the published ⚠ BREAKING CHANGES note, and the
  conventional-commits parser ends that note only at another footer keyword or an issue reference,
  so any other trailing line is absorbed into it and published verbatim. Prose under a
  `## Breaking change` heading is not a footer and never reaches the release notes at all; see
  [`CONTRIBUTING.md`](CONTRIBUTING.md#breaking-changes).
- **Run `uv run pytest`, `pixi run lint`, and `pixi run format --check` before pushing.** All three
  run in CI, and the test job runs the matrix with `--frozen`, so a dependency change has to land
  with its lock files regenerated.
