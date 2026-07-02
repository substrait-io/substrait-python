# Releasing substrait-python

Releases of substrait-python are **fully automated** using
[semantic-release](https://semantic-release.gitbook.io/) and follow the same model
as the other Substrait projects (e.g. substrait-java).

The [Semantic Release](.github/workflows/semantic-release.yml) workflow runs on a
weekly schedule (2 AM UTC on Sundays). It inspects the [Conventional
Commits](https://www.conventionalcommits.org/en/v1.0.0/) merged since the last
release, computes the next version, updates `CHANGELOG.md`, creates the `vX.Y.Z`
git tag, and publishes a GitHub Release with auto-generated notes.

Creating the tag triggers the [Release and Publish](.github/workflows/release.yml)
workflow, which builds the package (the version is derived from the tag via
`setuptools_scm`) and publishes it to [PyPI](https://pypi.org/project/substrait/)
using Trusted Publishing.

As a result, there is nothing to do by hand for a normal release — just make sure
your PR titles/commit messages follow the Conventional Commits specification (this
is enforced by the [PR Title Check](.github/workflows/pr_title.yml) workflow).

## Triggering an off-cycle release

If you need a release before the next scheduled run (and you are a Substrait
committer or PMC member with the appropriate permissions):

1. Go to https://github.com/substrait-io/substrait-python/actions/workflows/semantic-release.yml
2. Click `Run workflow` and select the `main` branch.
3. Monitor the workflow run, then the triggered `Release and Publish` run, to
   confirm the new version reaches PyPI.

If there are no release-worthy commits since the last release (only `chore`, `docs`,
`ci`, etc.), semantic-release will report that no release is necessary and do
nothing.

## Versioning

Version bumps are derived from commit types:

| Commit type                                  | Version bump |
| -------------------------------------------- | ------------ |
| `fix:`                                       | patch        |
| `feat:`                                      | minor        |
| breaking change (`feat!:`, `BREAKING CHANGE`)| minor        |

substrait-python follows semantic versioning as described for the Substrait
specification here: https://substrait.io/spec/versioning/. Because the project is
pre-1.0, breaking changes produce a **minor** bump rather than a major one (matching
substrait-java).
