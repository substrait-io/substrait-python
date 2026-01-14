#!/bin/bash

if ! command -v curl > /dev/null 2>&1; then
    echo "curl is required to grab the latest version tag"
fi

VERSION=$(curl -s https://api.github.com/repos/substrait-io/substrait/releases/latest | grep 'tag_name' | cut -d '"' -f 4)

echo "Updating substrait submodule..."
git submodule update --remote third_party/substrait

DIR=$(cd "$(dirname "$0")" && pwd)
pushd "${DIR}"/third_party/substrait/ || exit
git checkout "$VERSION"
popd || exit
