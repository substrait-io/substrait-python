#!/usr/bin/env bash

set -eou pipefail

namespace=proto
submodule_dir=./third_party/substrait
src_dir="$submodule_dir"/proto
tmp_dir=./buf_work_dir
dest_dir=./src/substrait/gen
extension_dir=./src/substrait/extensions

# Prefix the protobuf files with a unique configuration to prevent namespace conflicts
# with other substrait packages. Save output to the work dir.
python "$submodule_dir"/tools/proto_prefix.py "$tmp_dir" "$namespace" "$src_dir"

# Remove the old python protobuf files
rm -rf "$dest_dir"

# Generate the new python protobuf files
buf generate
protol --in-place --create-package --python-out "$dest_dir" buf

# Remove the old extension files
rm -rf "$extension_dir"

# Copy over new yaml files
cp -fr "$submodule_dir"/extensions "$extension_dir"
find "$extension_dir" -type f -exec chmod u+rw {} +

# Ensure there's an __init__.py file in the extension directory
touch $extension_dir/__init__.py

# Remove the temporary work dir
rm -rf "$tmp_dir"
