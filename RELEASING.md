# Releasing substrait-python

Given that you are a Substrait committer or PMC member and have the appropriate permissions, releasing a new version of substrait-python is done by simply creating new Github Release through the UI:

1. Go to https://github.com/substrait-io/substrait-python/releases
2. Click `Draft a new release`
3. Enter the version to be released in the `Tag` field prefixed with a lower case `v`, e.g. `v0.99.0`. Then click `Create new tag` which tells Github to create the tag on publication of the release.
4. Click `Generate release notes` which will automatically populate the release title and release notes fields.
5. If you are happy with the release notes and you are ready for an immediate release simply click `Publish release` otherwise save the release as a draft for later.
6. Monitor the Github Actions release build for the newly created release and tag.
