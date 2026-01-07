#!/bin/bash
if ! git diff --quiet --exit-code src/substrait/gen/; then
    echo "Code generation produced changes. Generated code is out of sync!"
    echo ""
    git diff src/substrait/gen/
    echo ""
    echo "To fix this, run:"
    echo "  pixi run codegen"
    echo "Then commit the changes."
    exit 1
fi