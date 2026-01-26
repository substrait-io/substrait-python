#!/usr/bin/env bash

set -eou pipefail

submodule_dir=./third_party/substrait
extension_dir=./src/substrait/extension_files

# Remove the old extension files
rm -rf "$extension_dir"

# Copy over new yaml files
cp -fr "$submodule_dir"/extensions "$extension_dir"
find "$extension_dir" -type f -exec chmod u+rw {} +

# Ensure there's an __init__.py file in the extension directory
touch $extension_dir/__init__.py
