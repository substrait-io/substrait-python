#!/bin/bash
set -euo pipefail

# Check that all substrait-* packages have the same version
uv sync

antlr_version=$(uv pip show substrait-antlr | grep '^Version:' | awk '{print $2}')
extension_version=$(uv pip show substrait-extensions | grep '^Version:' | awk '{print $2}')
protobuf_version=$(uv pip show substrait-protobuf | grep '^Version:' | awk '{print $2}')

if [ "$protobuf_version" != "$antlr_version" ]; then
    echo "error: substrait-protobuf ($protobuf_version) and substrait-antlr ($antlr_version) versions do not match"
    exit 1
fi

if [ "$protobuf_version" != "$extension_version" ]; then
    echo "error: substrait-protobuf ($protobuf_version) and substrait-extension ($extension_version) versions do not match"
    exit 1
fi
