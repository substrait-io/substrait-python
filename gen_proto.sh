#!/usr/bin/env bash

set -eou pipefail

namespace=pysubstrait
submodule_dir=./third_party/substrait
src_dir="$submodule_dir"/proto
tmp_dir=./proto
dest_dir=./src/substrait/proto

# Prefix the protobuf files with a unique configuration to prevent namespace conflicts
# with other substrait packages. Save output to the work dir.
python "$submodule_dir"/tools/proto_prefix.py "$tmp_dir" "$namespace" "$src_dir"

# Remove the old python protobuf files
rm -rf "$dest_dir"

# Generate the new python protobuf files
buf generate
protol --in-place --create-package --python-out "$dest_dir" buf

# Remove the temporary work dir
rm -rf "$tmp_dir"
