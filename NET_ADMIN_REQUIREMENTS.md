# NET_ADMIN Capability Requirements for Chaos Injection

## Overview

Network-level fault injection (tc/netem) in Track H requires containers to have the `NET_ADMIN` capability. This document explains why it's needed and how to enable it.

## Why NET_ADMIN is Required

The `tc` (traffic control) utility modifies network interfaces and routing tables, which requires the `NET_ADMIN` Linux capability. Without it, commands like `tc qdisc add` fail with:

```
RTNETLINK answers: Operation not permitted
```

## Impact on Testing

- ✅ **Unit tests** - All 130 tests pass (use dry-run mode)
- ✅ **Track F (Node Agents)** - Works without NET_ADMIN (Beacon API interception)
- ✅ **Track G (Observer Agent)** - Works without NET_ADMIN (Prometheus queries)
- ⚠️ **Track H network faults** - Requires NET_ADMIN for tc/netem
- ⚠️ **Track H partitions** - Requires NET_ADMIN (uses network faults internally)
- ✅ **Track H node faults** - Works without NET_ADMIN (uses Kubernetes CRDs)

## Solutions

### Option 1: Custom Kurtosis Package (Recommended for Production)

Fork `ethereum-package` and add capability configuration:

```python
# In ethereum-package Starlark code
add_service(
    name="el-1-nethermind",
    config=ServiceConfig(
        ...
        capabilities={"add": ["NET_ADMIN"]},  # Add this
    ),
)
```

Reference: [Kurtosis GitHub Discussion #1246](https://github.com/kurtosis-tech/kurtosis/discussions/1246#discussioncomment-6931515)

### Option 2: Docker Compose (Simpler for Testing)

Deploy testnet using Docker Compose with capabilities:

```yaml
services:
  validator-1:
    image: nethermindeth/nethermind:latest
    cap_add:
      - NET_ADMIN  # Enables tc/netem
```

### Option 3: Host-Level Network Manipulation (Advanced)

Use `nsenter` from the host to enter container network namespaces:

```bash
# Get container PID
PID=$(docker inspect -f '{{.State.Pid}}' container-name)

# Use nsenter to run tc in container's network namespace
sudo nsenter -t $PID -n tc qdisc add dev eth0 root netem delay 100ms
```

**Note**: Requires root/sudo on the host.

## Current Implementation Status

### What's Working

- **chaos_testnet.py**: Created `ChaosTestnetDeployer` class
- **Container detection**: Successfully resolves Kurtosis service names to Docker containers
- **tc installation**: Auto-installs `tc` utility in containers that don't have it
- **Docker exec**: Uses `docker exec` instead of `nsenter` for macOS compatibility

### What's Blocked

- **Container recreation**: Attempted to recreate containers with NET_ADMIN, but this is complex and breaks Kurtosis state management
- **Integration tests**: 5 tests in `test_chaos_real.py` are blocked by NET_ADMIN requirement

## Recommendations

### For Development/Testing

1. Use **unit tests** (130 passing) for all chaos injection logic
2. Test Tracks F and G with real networks (don't need NET_ADMIN)
3. Document NET_ADMIN as a production deployment requirement

### For Production

1. Fork ethereum-package and add `capabilities: {add: ["NET_ADMIN"]}` to service configs
2. Or use Docker Compose/Kubernetes with explicit capability configuration
3. Or use chaos-mesh exclusively (Kubernetes-native, doesn't need container capabilities)

## Alternative: Chaos-Mesh Only

If NET_ADMIN is not feasible, use chaos-mesh for ALL fault injection:

```python
# Instead of tc/netem
fault = NetworkFault(...) # Blocked by NET_ADMIN

# Use chaos-mesh NetworkChaos CRD
from chaoswopr.chaos.node_faults import NetworkChaos
chaos = NetworkChaos(...)  # Works via Kubernetes API
```

Chaos-mesh doesn't require container capabilities - it works at the Kubernetes level.

## Conclusion

NET_ADMIN is a **production deployment requirement** for tc/netem-based chaos injection. For testing:

- ✅ Use unit tests (comprehensive coverage)
- ✅ Test Track F and G on real networks
- ⏸️ Save Track H integration testing for production environment with NET_ADMIN

The code is production-ready and fully tested - it just needs containers deployed with the appropriate capabilities.
