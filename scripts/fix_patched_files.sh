#!/bin/bash
# Quick fix script to correct the syntax errors in patched files
# The autopatcher added capabilities in the wrong place

set -euo pipefail

PATCHED_DIR="/Users/swp/dev/swapnilraj/chaoswopr/kurtosis-packages/ethereum-package-patched"

echo "Fixing syntax errors in patched Starlark files..."

# Find all .star files with the bad pattern and fix them
find "$PATCHED_DIR" -name "*.star" -type f -print0 | while IFS= read -r -d '' file; do
    if grep -q "^    capabilities = {\"add\": \[\"NET_ADMIN\"\]},$" "$file"; then
        echo "Fixing: $file"

        # Remove the standalone capabilities line
        sed -i '' '/^    capabilities = {"add": \["NET_ADMIN"\]},$/d' "$file"

        # Add capabilities inside config_args dict (before the return statement)
        sed -i '' '/return ServiceConfig(\*\*config_args)/i\
    config_args["capabilities"] = {"add": ["NET_ADMIN"]}
' "$file"
    fi
done

echo "✅ Fixed all syntax errors"
