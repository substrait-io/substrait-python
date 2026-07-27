#!/usr/bin/env bash
# shellcheck shell=bash

set -euo pipefail

# Versions are pinned deliberately: a floating conventional-changelog preset
# silently dropped the Features/Bug Fixes sections from the generated notes.
# ci/release/dry_run.sh guards against a regression when these are bumped.
# RELEASE_DRY_RUN=false opts .releaserc.mjs in to a real release (it defaults
# to a dry run as a fail-safe).
RELEASE_DRY_RUN=false npx --yes \
  -p "semantic-release@25.0.5" \
  -p "@semantic-release/commit-analyzer@13.0.1" \
  -p "@semantic-release/release-notes-generator@14.1.1" \
  -p "@semantic-release/changelog@6.0.3" \
  -p "@semantic-release/github@12.0.8" \
  -p "@semantic-release/git@10.0.1" \
  -p "conventional-changelog-conventionalcommits@9.3.1" \
  semantic-release --ci
