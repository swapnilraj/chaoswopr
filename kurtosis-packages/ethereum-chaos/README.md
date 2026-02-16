# NET_ADMIN Solution for Chaos Injection

This directory contains the solution for enabling NET_ADMIN capability in Docker containers for tc/netem-based chaos injection.

## Problem

Network-level fault injection using `tc` (traffic control) requires containers to have the `NET_ADMIN` Linux capability. The standard ethereum-package from ethpandaops doesn't include this capability by default for security reasons, causing chaos injection to fail with:

```
RTNETLINK answers: Operation not permitted
```

## Solution

We use a **patched local version** of ethereum-package that adds `capabilities = {"add": ["NET_ADMIN"]}` to all ServiceConfig calls. This enables tc/netem fault injection without requiring runtime container manipulation.

### Why This Approach?

1. **Container recreation doesn't work** - Stopping and recreating containers breaks Kurtosis state management
2. **Runtime capability addition not supported** - Docker doesn't allow adding capabilities to running containers
3. **Capabilities must be set at creation time** - The only reliable way is to add them in ServiceConfig

### Implementation

The solution consists of three components:

1. **scripts/patch_ethereum_package.sh** - Creates a local patched version of ethereum-package
2. **scripts/auto_patch_net_admin.py** - Automatically modifies .star files to add capabilities
3. **src/chaoswopr/infrastructure/testnet/chaos_testnet.py** - Deploys using the patched package

## Usage

### Step 1: Create Patched Package

Run the patch script to create a local version with NET_ADMIN:

```bash
./scripts/patch_ethereum_package.sh
```

This will:
- Clone ethereum-package to `kurtosis-packages/ethereum-package-patched/`
- Automatically add `capabilities = {"add": ["NET_ADMIN"]}` to all ServiceConfig calls
- Create a `CHAOS_PATCH.md` file documenting the changes

### Step 2: Deploy Chaos Testnet

Use the `ChaosTestnetDeployer` which automatically uses the patched package:

```python
from chaoswopr.infrastructure.testnet.chaos_testnet import create_chaos_testnet

# Deploy with NET_ADMIN enabled
deployer, result = create_chaos_testnet(
    node_count=4,
    enclave_name="my-chaos-test",
    use_patched_package=True,  # Default is True
)

if result.success:
    print("Testnet deployed with NET_ADMIN capability")
    # Ready for chaos injection
```

### Step 3: Inject Faults

Now you can use network fault injection without permission errors:

```python
from chaoswopr.chaos.network_faults import PacketLossFault

# This will work because containers have NET_ADMIN
fault = PacketLossFault(
    target_service="el-1-nethermind",
    loss_percentage=20.0,
    interface="eth0",
)

fault.inject()  # Success! No "Operation not permitted"
```

## Maintenance

When ethereum-package updates:

1. Re-run `./scripts/patch_ethereum_package.sh` to fetch latest upstream
2. The autopatcher will re-apply NET_ADMIN patches
3. Test with chaoswopr integration tests
4. Commit the updated patched package

## Technical Details

### What Gets Patched?

All ServiceConfig calls in ethereum-package .star files:

```starlark
# Before
ServiceConfig(
    image = "nethermindeth/nethermind:latest",
    ports = {...},
    ...
)

# After
ServiceConfig(
    image = "nethermindeth/nethermind:latest",
    ports = {...},
    ...
    capabilities = {"add": ["NET_ADMIN"]},
)
```

### Why Not Fork ethereum-package?

Forking requires:
- Maintaining a separate GitHub fork
- Keeping it in sync with upstream
- Managing merge conflicts

Our approach:
- Keeps patches in our repo as scripts
- Easy to regenerate when upstream changes
- No GitHub fork maintenance

### Alternative: Chaos-Mesh Only

If NET_ADMIN is not feasible in your environment, use chaos-mesh exclusively:

```python
from chaoswopr.chaos.node_faults import NetworkChaos

# Chaos-mesh doesn't need NET_ADMIN (works at K8s level)
chaos = NetworkChaos(
    name="packet-loss-test",
    namespace="default",
    selector={"app": "nethermind"},
    action="loss",
    loss={"loss": "20", "correlation": "0"},
)
```

Chaos-mesh requires Kubernetes but doesn't need container capabilities.

## Troubleshooting

### Patched package not found

**Error**: `WARNING: Patched ethereum-package not found`

**Solution**: Run `./scripts/patch_ethereum_package.sh` to create it

### Autopatcher fails

**Error**: Python script exits with errors

**Solution**: Check you have Python 3.7+ and the patched directory exists

### Fault injection still fails with "Operation not permitted"

**Possible causes**:
1. Using upstream package instead of patched version - check `use_patched_package=True`
2. Patched package not deployed correctly - verify with `docker inspect <container> | grep CapAdd`
3. SELinux/AppArmor blocking - may need host-level configuration

### Verify NET_ADMIN is enabled

Check a deployed container:

```bash
# Find container
docker ps | grep nethermind

# Check capabilities
docker inspect <container-id> | grep CapAdd
# Should show: "CapAdd": ["NET_ADMIN"]
```

## References

- [Kurtosis GitHub Discussion #1246](https://github.com/kurtosis-tech/kurtosis/discussions/1246#discussioncomment-6931515) - Original NET_ADMIN capability discussion
- [NET_ADMIN_REQUIREMENTS.md](../../NET_ADMIN_REQUIREMENTS.md) - Detailed technical explanation
- [TRACK_H_STATUS.md](../../TRACK_H_STATUS.md) - Implementation status

## License

Same as chaoswopr project. The patched ethereum-package retains its original Apache 2.0 license from ethpandaops.
