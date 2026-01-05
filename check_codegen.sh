#!/bin/bash
if ! git diff --quiet --exit-code src/substrait/gen/; then
    echo "Code generation produced changes. Generated code is out of sync!"
    echo ""
    git diff src/substrait/gen/
    echo ""
    echo "To fix this, run:"
    echo "  make codegen"
    echo "Then commit the changes."
    exit 1
fi