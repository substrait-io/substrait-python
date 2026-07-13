#!/usr/bin/env bash
# shellcheck shell=bash
#
# Credential-free release-notes regression check.
#
# Reproduces the failure seen on PR #171: with a floating release toolchain the
# release-notes-generator emitted only the version heading and silently dropped
# the "Features" / "Bug Fixes" sections. This builds a throwaway git repo with
# known feat/fix commits, runs the *pinned* semantic-release in dry-run mode,
# and asserts the generated notes actually contain those sections.
#
# It needs no GitHub token: RELEASE_DRY_RUN is left at its default so
# .releaserc.mjs omits the @semantic-release/github and @semantic-release/git
# plugins, whose verifyConditions would otherwise demand credentials.
#
# Keep the pinned versions here in sync with ci/release/run.sh.

set -euo pipefail

# semantic-release uses env-ci to detect the branch/PR context. Under GitHub
# Actions that resolves GITHUB_REF=refs/pull/N/merge to a PR build, so it decides
# the branch isn't "main" and computes no release -- leaving the notes empty and
# this check falsely failing. Clear the Actions markers so env-ci falls back to
# the throwaway repo's own git branch (main) below, matching a local run.
unset GITHUB_ACTIONS GITHUB_EVENT_NAME GITHUB_REF GITHUB_HEAD_REF GITHUB_BASE_REF GITHUB_SHA

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

workdir="$(mktemp -d)"
cleanup() { rm -rf "$workdir"; }
trap cleanup EXIT

cp "$repo_root/.releaserc.mjs" "$workdir/.releaserc.mjs"

cd "$workdir"
git -c init.defaultBranch=main init -q
git config user.email "release-check@substrait.io"
git config user.name "release check"
git config commit.gpgsign false
git config tag.gpgsign false

# A baseline release to compute the next version against, then two commits of
# each releasable type so both sections are expected in the notes.
git commit -q --allow-empty -m "chore: baseline"
git tag v0.0.0
git commit -q --allow-empty -m "feat: add a first capability"
git commit -q --allow-empty -m "feat: add a second capability"
git commit -q --allow-empty -m "fix: correct a first defect"
git commit -q --allow-empty -m "fix: correct a second defect"

echo "Running semantic-release dry run against synthetic history..."
notes="$(
  npx --yes \
    -p "semantic-release@25.0.5" \
    -p "@semantic-release/commit-analyzer@13.0.1" \
    -p "@semantic-release/release-notes-generator@14.1.1" \
    -p "@semantic-release/changelog@6.0.3" \
    -p "@semantic-release/github@12.0.8" \
    -p "@semantic-release/git@10.0.1" \
    -p "conventional-changelog-conventionalcommits@9.3.1" \
    semantic-release \
    --ci false \
    --dry-run \
    --branches main \
    --repository-url "file://$workdir" 2>&1
)"

echo "$notes"

fail=0
for section in "Features" "Bug Fixes"; do
  if ! grep -qE "^#+ ${section}\$" <<<"$notes"; then
    echo "ERROR: release notes are missing the '${section}' section." >&2
    fail=1
  fi
done

if [[ "$fail" -ne 0 ]]; then
  echo "Release-notes generation is broken -- likely an unpinned or incompatible" >&2
  echo "toolchain version. See ci/release/run.sh and .releaserc.mjs." >&2
  exit 1
fi

echo "OK: generated notes contain the expected Features and Bug Fixes sections."
