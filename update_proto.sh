#!/bin/bash

if [[ -z "$1" ]]; then
    echo "Usage: bash update.sh <version>" 1>&2
    echo ""
    echo "Example: bash update.sh v0.34.0" 1>&2
    exit 1
fi

VERSION=$1

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
