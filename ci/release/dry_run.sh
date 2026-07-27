#!/usr/bin/env bash
# shellcheck shell=bash
#
# Credential-free release-notes dry run.
#
# Runs the *pinned* semantic-release toolchain in dry-run mode against the real
# repository history (in a throwaway worktree so nothing is mutated) and prints
# the notes it would generate. When a release is actually due, it asserts the
# notes contain sections rather than just a version heading -- guarding the
# regression seen on PR #171, where a floating conventional-changelog preset
# emitted only the heading and silently dropped the Features/Bug Fixes sections.
#
# No GitHub token is needed: RELEASE_DRY_RUN is left at its default so
# .releaserc.mjs omits the @semantic-release/github and @semantic-release/git
# plugins, whose verifyConditions would otherwise demand credentials.
#
# Keep the pinned versions here in sync with ci/release/run.sh.

set -euo pipefail

# semantic-release uses env-ci to detect the branch. Under GitHub Actions on a
# pull_request it resolves GITHUB_REF=refs/pull/N/merge to a PR build and refuses
# to run; clear the Actions markers so env-ci falls back to the worktree's own
# branch below (created fresh from HEAD, so this works from a detached checkout).
unset GITHUB_ACTIONS GITHUB_EVENT_NAME GITHUB_REF GITHUB_HEAD_REF GITHUB_BASE_REF GITHUB_SHA

curdir="$PWD"
worktree="$(mktemp -d)"
branch="$(basename "$worktree")"

git worktree add -q "$worktree"

cleanup() {
  cd "$curdir" || exit 1
  git worktree remove --force "$worktree" >/dev/null 2>&1 || true
  git worktree prune
  git branch -D "$branch" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cd "$worktree"

echo "Running semantic-release dry run against real history (branch ${branch})..."
if notes="$(
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
    --branches "$branch" \
    --repository-url "file://$worktree" 2>&1
)"; then
  sr_exit=0
else
  sr_exit=$?
fi

echo "$notes"

if [[ "$sr_exit" -ne 0 ]]; then
  echo "ERROR: semantic-release dry run failed (exit ${sr_exit})." >&2
  exit 1
fi

if ! grep -qE 'The next release version is' <<<"$notes"; then
  echo "NOTE: no release is due from the current history, so there are no notes to assert."
  echo "OK: semantic-release dry run completed without errors."
  exit 0
fi

# A release is due, so at least one feat/fix/breaking commit exists and the notes
# must carry a matching section. The regression produced only the "## <version>"
# heading (h2) with no "### <section>" (h3) beneath it.
if ! grep -qE '^### ' <<<"$notes"; then
  echo "ERROR: a release is due but the generated notes contain no sections -- only the heading." >&2
  echo "This is the PR #171 regression; check the pinned toolchain in ci/release/run.sh and .releaserc.mjs." >&2
  exit 1
fi

echo "OK: a release is due and the generated notes contain the expected sections."
