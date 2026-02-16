# Quick Start: Enabling NET_ADMIN for Chaos Injection

This guide shows you how to enable NET_ADMIN capability for tc/netem-based chaos injection in 3 simple steps.

## TL;DR

```bash
# 1. Create patched ethereum-package
./scripts/patch_ethereum_package.sh

# 2. Deploy testnet (Python)
from chaoswopr.infrastructure.testnet.chaos_testnet import create_chaos_testnet
deployer, result = create_chaos_testnet(node_count=4)

# 3. Inject faults (no permission errors!)
from chaoswopr.chaos.network_faults import PacketLossFault
fault = PacketLossFault("el-1-nethermind", loss_percentage=20.0)
fault.inject()  # ✅ Works!
```

## Why Do We Need This?

Network-level fault injection using `tc` (traffic control) requires the `NET_ADMIN` Linux capability. Without it, chaos injection fails with:

```
RTNETLINK answers: Operation not permitted
```

The standard ethereum-package doesn't include this capability by default for security.

## Step-by-Step Setup

### Step 1: Create Patched Package (One-Time Setup)

Run the patch script to create a local version of ethereum-package with NET_ADMIN:

```bash
cd /path/to/chaoswopr
./scripts/patch_ethereum_package.sh
```

This script will:
- Clone ethereum-package to `kurtosis-packages/ethereum-package-patched/`
- Automatically modify all Starlark (.star) files to add NET_ADMIN capability
- Create documentation in `CHAOS_PATCH.md`

**Expected output:**
```
Creating patched ethereum-package with NET_ADMIN capability...
Cloning ethereum-package...
Applying NET_ADMIN patches...
Patching complete:
  - 15 files patched
  - 3 files skipped (already patched or no ServiceConfig)
```

**Time:** ~30 seconds

### Step 2: Deploy Testnet with NET_ADMIN

Use the `ChaosTestnetDeployer` which automatically uses the patched package:

```python
from chaoswopr.infrastructure.testnet.chaos_testnet import create_chaos_testnet

# Deploy 4-node testnet with NET_ADMIN enabled
deployer, result = create_chaos_testnet(
    node_count=4,
    enclave_name="chaos-test",
    use_patched_package=True,  # This is the default
)

if result.success:
    print("✅ Testnet deployed with NET_ADMIN capability")
else:
    print(f"❌ Deployment failed: {result.error_message}")
```

**Time:** ~5 minutes for 4-node testnet

### Step 3: Verify NET_ADMIN is Enabled

Check that containers have the capability:

```bash
# Find a container
docker ps | grep nethermind

# Check capabilities
docker inspect <container-id> --format='{{.HostConfig.CapAdd}}'
# Should show: [NET_ADMIN]
```

### Step 4: Run Chaos Injection

Now you can inject faults without permission errors:

```python
from chaoswopr.chaos.network_faults import PacketLossFault, NetworkLatencyFault
from chaoswopr.chaos.partition import NetworkPartition

# Packet loss
fault = PacketLossFault(
    target_service="el-1-nethermind",
    loss_percentage=20.0,
)
fault.inject()  # ✅ Success!

# Network latency
latency = NetworkLatencyFault(
    target_service="el-2-nethermind",
    delay_ms=200.0,
    jitter_ms=50.0,
)
latency.inject()  # ✅ Success!

# Network partition
partition = NetworkPartition(
    islands=[
        ["el-1-nethermind", "cl-1-prysm"],
        ["el-2-nethermind", "cl-2-prysm"],
    ],
    mode="CLEAN",
)
partition.create()  # ✅ Success!
```

## Maintenance

### Updating to Latest ethereum-package

When ethereum-package releases updates:

```bash
# Re-run patch script to fetch latest
./scripts/patch_ethereum_package.sh

# Test with chaos injection
python -m pytest tests/integration_real/test_chaos_real.py
```

The autopatcher will re-apply NET_ADMIN patches to any new or modified files.

## Troubleshooting

### "Patched package not found" warning

**Symptom:** Warning message during deployment about missing patched package

**Solution:** Run `./scripts/patch_ethereum_package.sh` to create it

### Chaos injection still fails with "Operation not permitted"

**Symptom:** tc commands fail even with patched package

**Possible causes:**
1. Deployed without `use_patched_package=True` - check your deployment code
2. Autopatcher didn't run correctly - check script output
3. SELinux/AppArmor blocking - may need host configuration

**Debug steps:**
```bash
# 1. Check if container has NET_ADMIN
docker inspect <container> | grep CapAdd

# 2. Test tc manually
docker exec <container> tc qdisc add dev eth0 root netem delay 100ms

# 3. Check Kurtosis logs
kurtosis enclave inspect chaos-test
```

### Autopatcher reports errors

**Symptom:** Python script exits with errors

**Solution:**
- Check Python version: `python3 --version` (need 3.7+)
- Check patched directory exists: `ls kurtosis-packages/ethereum-package-patched/`
- Re-run patch script: `./scripts/patch_ethereum_package.sh`

## Alternative: Chaos-Mesh Only

If NET_ADMIN setup is not feasible in your environment, use chaos-mesh exclusively:

```python
from chaoswopr.chaos.node_faults import NetworkChaos

# Chaos-mesh doesn't need NET_ADMIN (works at Kubernetes level)
chaos = NetworkChaos(
    name="packet-loss-test",
    namespace="default",
    selector={"app": "nethermind"},
    action="loss",
    loss={"loss": "20", "correlation": "0"},
)
```

**Requirements:**
- Kubernetes cluster (not Docker)
- chaos-mesh installed: `kubectl apply -f https://mirrors.chaos-mesh.org/latest/chaos-mesh.yaml`

## Next Steps

- Read [NET_ADMIN_REQUIREMENTS.md](./NET_ADMIN_REQUIREMENTS.md) for technical details
- See [kurtosis-packages/ethereum-chaos/README.md](./kurtosis-packages/ethereum-chaos/README.md) for complete documentation
- Run [tests/integration_real/test_chaos_real.py](./tests/integration_real/test_chaos_real.py) to verify everything works

## Summary

✅ **Step 1:** Run `./scripts/patch_ethereum_package.sh` (one-time, ~30 seconds)
✅ **Step 2:** Use `ChaosTestnetDeployer` with `use_patched_package=True`
✅ **Step 3:** Inject faults without permission errors!

The NET_ADMIN solution is fully automated and maintainable - no manual container manipulation required.
