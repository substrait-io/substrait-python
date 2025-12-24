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
SUBSTRAIT_HASH=$(git rev-parse --short HEAD)
popd || exit

VERSION=${VERSION//v/}

sed -i "s#__substrait_hash__.*#__substrait_hash__ = \"$SUBSTRAIT_HASH\"#g" src/substrait/__init__.py
sed -i "s#__substrait_version__.*#__substrait_version__ = \"$VERSION\"#g" src/substrait/__init__.py

./gen_proto.sh
