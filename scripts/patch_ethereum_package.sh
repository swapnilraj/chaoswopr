#!/bin/bash
# Script to create a patched version of ethereum-package with NET_ADMIN capability
#
# Usage: ./scripts/patch_ethereum_package.sh
#
# This script:
# 1. Clones ethereum-package to kurtosis-packages/ethereum-package-patched
# 2. Adds NET_ADMIN capability to all service configs
# 3. Creates a local version that can be used with Kurtosis

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCHED_DIR="$REPO_ROOT/kurtosis-packages/ethereum-package-patched"
ETHEREUM_PACKAGE_REPO="https://github.com/ethpandaops/ethereum-package.git"

echo "Creating patched ethereum-package with NET_ADMIN capability..."

# Step 1: Clone ethereum-package if not already cloned
if [ ! -d "$PATCHED_DIR" ]; then
    echo "Cloning ethereum-package..."
    git clone "$ETHEREUM_PACKAGE_REPO" "$PATCHED_DIR"
else
    echo "Updating existing ethereum-package clone..."
    cd "$PATCHED_DIR"
    git fetch origin
    git reset --hard origin/main
fi

cd "$PATCHED_DIR"

echo "Current directory: $(pwd)"
echo "Applying NET_ADMIN patches..."

# Step 2: Run the automated patcher
python3 "$REPO_ROOT/scripts/auto_patch_net_admin.py" "$PATCHED_DIR"

# Step 3: Create a README explaining the patch
cat > "$PATCHED_DIR/CHAOS_PATCH.md" << 'EOF'
# NET_ADMIN Capability Patch for Chaos Testing

This is a patched version of ethereum-package that adds NET_ADMIN capability
to all containers, enabling tc/netem network fault injection for chaos engineering.

## What Was Changed

All `ServiceConfig` calls in the package have been modified to include:

```starlark
ServiceConfig(
    ...
    capabilities = {"add": ["NET_ADMIN"]},
)
```

## Maintenance

To update this patch when ethereum-package changes:

1. Run `scripts/patch_ethereum_package.sh` to fetch latest upstream
2. Re-apply the NET_ADMIN patches manually to any new service configs
3. Test with chaoswopr integration tests

## Manual Patch Locations

Key files that need capabilities added:

- `src/el/el_launcher.star` - Execution layer clients
- `src/cl/cl_launcher.star` - Consensus layer clients
- `src/*/launcher.star` - Any other service launchers

Search for `ServiceConfig(` and add the capabilities parameter.
EOF

echo ""
echo "============================================"
echo "Patched ethereum-package created at:"
echo "  $PATCHED_DIR"
echo ""
echo "⚠️  MANUAL STEP REQUIRED:"
echo ""
echo "The patch script has identified files containing ServiceConfig calls."
echo "You need to manually add the following to each ServiceConfig:"
echo ""
echo "  capabilities = {\"add\": [\"NET_ADMIN\"]},"
echo ""
echo "See $PATCHED_DIR/CHAOS_PATCH.md for details."
echo ""
echo "Once patched, update your deployer to use:"
echo "  package_path = \"$PATCHED_DIR\""
echo "============================================"
