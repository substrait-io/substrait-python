// semantic-release configuration.
//
// This is an ESM (.mjs) config rather than .releaserc.json so the set of
// plugins can depend on RELEASE_DRY_RUN. It defaults to a dry run as a
// fail-safe: the side-effecting plugins (@semantic-release/github and
// @semantic-release/git) are only included when RELEASE_DRY_RUN=false.
// ci/release/run.sh opts in to a real release that way; every other
// invocation -- the credential-free notes check in ci/release/dry_run.sh, or
// a forgotten/typo'd env var -- stays harmless.
//
// The env var is needed on top of --dry-run because --dry-run alone is not
// enough: semantic-release still runs every plugin's verifyConditions step in
// dry-run mode (it skips only prepare, publish, addChannel, success and fail).
// @semantic-release/github's verifyConditions fails without a GITHUB_TOKEN, so
// the side-effecting plugins must be omitted entirely, not merely guarded by
// --dry-run, to allow a credential-free dry run.

const dryRun = process.env.RELEASE_DRY_RUN !== "false";

export default {
  branches: ["main"],
  preset: "conventionalcommits",
  dryRun,
  plugins: [
    [
      "@semantic-release/commit-analyzer",
      {
        // Pre-1.0, matching substrait-java: a breaking change is a minor bump.
        releaseRules: [{ breaking: true, release: "minor" }],
      },
    ],
    "@semantic-release/release-notes-generator",
    [
      "@semantic-release/changelog",
      {
        changelogTitle: "Release Notes\n---",
        changelogFile: "CHANGELOG.md",
      },
    ],
    ...(dryRun
      ? []
      : [
          [
            "@semantic-release/github",
            {
              successComment: false,
            },
          ],
          [
            "@semantic-release/git",
            {
              assets: ["CHANGELOG.md"],
              message: "chore(release): ${nextRelease.version}",
            },
          ],
        ]),
  ],
};
