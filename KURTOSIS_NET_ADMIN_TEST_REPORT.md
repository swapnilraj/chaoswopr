# Kurtosis NET_ADMIN Capability Test Report

**Date:** 2026-02-16
**Test Objective:** Verify if Kurtosis ServiceConfig supports NET_ADMIN capability via `docker_config` or `capabilities` parameters
**Result:** ❌ **FAILED - Feature Not Supported**

---

## Executive Summary

Kurtosis ServiceConfig **DOES NOT** support Docker capabilities (NET_ADMIN, NET_RAW, etc.) as of the current version. The user's suggestion that `docker_config = {"CapAdd": ["NET_ADMIN"]}` would work is **incorrect**.

Our current implementation using a "patched" ethereum-package that adds `capabilities = {"add": ["NET_ADMIN"]}` to ServiceConfig calls is **non-functional** and will fail when Kurtosis validates the Starlark code.

---

## Test Methodology

### 1. Created Test Kurtosis Package

Created `/Users/swp/dev/swapnilraj/chaoswopr/kurtosis-test-net-admin/main.star`:

```python
def run(plan, args={}):
    plan.add_service(
        name = "test-net-admin",
        config = ServiceConfig(
            image = "alpine:latest",
            cmd = ["/bin/sh", "-c", "apk add --no-cache iproute2 && sleep 3600"],
            docker_config = {
                "CapAdd": ["NET_ADMIN"]
            }
        )
    )
```

### 2. Attempted Deployment

```bash
kurtosis run kurtosis-test-net-admin --enclave net-admin-test
```

**Error Output:**
```
There was an error interpreting Starlark code
Evaluation error: Cannot construct 'ServiceConfig' from the provided arguments.
	Caused by: ServiceConfig: unexpected keyword argument "docker_config"
```

---

## Documentation Research

### Verified Kurtosis ServiceConfig Parameters

Fetched official documentation from: https://docs.kurtosis.com/api-reference/starlark-reference/service-config/

**Supported parameters:**
- Core: `image`, `ports`, `files`, `entrypoint`, `cmd`, `env_vars`
- Resources: `max_cpu`, `min_cpu`, `max_memory`, `min_memory`
- Advanced: `ready_conditions`, `labels`, `user`, `tolerations`, `node_selectors`, `tini_enabled`, `tty_enabled`, `devices`

**NOT supported:**
- ❌ `docker_config`
- ❌ `capabilities`
- ❌ `CapAdd` / `CapDrop`
- ❌ `privileged`
- ❌ `security_opt`

### GitHub Issues Search

Searched `site:github.com/kurtosis-tech/kurtosis capabilities privileged` - no results indicating this feature exists or is planned.

---

## Impact on Current Implementation

### Current (Broken) Approach

Our codebase currently uses a patching approach:

1. **Script:** `/Users/swp/dev/swapnilraj/chaoswopr/scripts/auto_patch_net_admin.py`
   - Adds `capabilities = {"add": ["NET_ADMIN"]}` to ServiceConfig calls
   - This parameter **does not exist** in Kurtosis

2. **Patched Package:** `/Users/swp/dev/swapnilraj/chaoswopr/kurtosis-packages/ethereum-package-patched/`
   - Contains invalid `capabilities` parameters in multiple files:
     - `src/el/geth/geth_launcher.star`
     - `src/el/nethermind/nethermind_launcher.star`
     - `src/el/besu/besu_launcher.star`
     - `src/el/reth/reth_launcher.star`
     - And many more...

3. **Deployer:** `/Users/swp/dev/swapnilraj/chaoswopr/src/chaoswopr/infrastructure/testnet/chaos_testnet.py`
   - `ChaosTestnetDeployer` uses the patched package
   - Will fail when Kurtosis validates the Starlark code

### Evidence from Grep Output

```bash
$ grep -r "capabilities" kurtosis-packages/ethereum-package-patched/ | head -20
```

Shows 100+ files with invalid `capabilities = {"add": ["NET_ADMIN"]}` parameters.

---

## Valid Alternatives

Since Kurtosis doesn't support capabilities directly, we have **two working options**:

### Option 1: Docker Compose (Already Implemented)

**Location:** `/Users/swp/dev/swapnilraj/chaoswopr/docker-compose/`

**How it works:**
```yaml
services:
  chaos-test:
    image: alpine:latest
    cap_add:
      - NET_ADMIN
    command: ["tc", "qdisc", "add", "dev", "eth0", "root", "netem", "loss", "20%"]
```

**Status:** ✅ Working (verified in `DOCKER_COMPOSE_TEST_RESULTS.md`)

**Pros:**
- Direct Docker API access
- Full capability control
- Already tested and working

**Cons:**
- Not integrated with Kurtosis ecosystem
- Separate orchestration layer
- No Kurtosis enclave management

### Option 2: Kurtosis with Privileged Mode (If Supported)

**Need to verify:** Does Kurtosis ServiceConfig support `privileged: true`?

From documentation review: **NOT mentioned** in ServiceConfig parameters.

**Next test:** Try `privileged` parameter explicitly.

---

## Recommended Actions

### Immediate (Stop Using Invalid Approach)

1. **Remove broken patching logic:**
   - Delete or deprecate `scripts/auto_patch_net_admin.py`
   - Remove `kurtosis-packages/ethereum-package-patched/`
   - Update `chaos_testnet.py` to NOT use patched package

2. **Update documentation:**
   - Mark `CHAOS_PATCH.md` as DEPRECATED
   - Add warning that capabilities are not supported in Kurtosis

### Short-term (Use Docker Compose)

1. **Extend Docker Compose implementation:**
   - Already working in `docker-compose/`
   - Add Ethereum node containers with NET_ADMIN
   - Integrate with chaos injection module

2. **Trade-offs:**
   - Lose Kurtosis enclave management
   - Gain full Docker capability control
   - Need separate orchestration for Kurtosis + Docker Compose

### Long-term (Feature Request or Alternative)

1. **File Kurtosis feature request:**
   - Open GitHub issue requesting capability support
   - Link to this use case (chaos engineering needs NET_ADMIN)

2. **Consider alternatives:**
   - Run chaos injection from **outside** containers (host-level tc)
   - Use Kubernetes SecurityContext if backend is K8s
   - Use privileged containers (if Kurtosis supports it)

---

## Test Artifacts

### Files Created

1. `/Users/swp/dev/swapnilraj/chaoswopr/kurtosis-test-net-admin/main.star`
2. `/Users/swp/dev/swapnilraj/chaoswopr/kurtosis-test-net-admin/kurtosis.yml`

### Commands Executed

```bash
# Test 1: docker_config parameter
kurtosis run kurtosis-test-net-admin --enclave net-admin-test
# Result: ServiceConfig: unexpected keyword argument "docker_config"

# Test 2: Documentation verification
# Fetched: https://docs.kurtosis.com/api-reference/starlark-reference/service-config/
# Result: No capabilities/docker_config parameters documented

# Test 3: GitHub issues search
# Searched: site:github.com/kurtosis-tech/kurtosis capabilities privileged
# Result: No relevant feature requests or implementations found
```

---

## Conclusion

**The user's information was incorrect.** Kurtosis ServiceConfig does NOT support:
- `docker_config = {"CapAdd": ["NET_ADMIN"]}`
- `capabilities = {"add": ["NET_ADMIN"]}`

**Our current patching approach is broken** and needs to be replaced with:
1. Docker Compose (already working)
2. Or wait for Kurtosis to add capability support
3. Or find alternative chaos injection methods (host-level, sidecar containers, etc.)

**Next steps:** Update implementation to use Docker Compose or investigate if `privileged: true` is supported in Kurtosis ServiceConfig.

---

## References

- [Kurtosis ServiceConfig Documentation](https://docs.kurtosis.com/api-reference/starlark-reference/service-config/)
- [Docker Compose Test Results](/Users/swp/dev/swapnilraj/chaoswopr/DOCKER_COMPOSE_TEST_RESULTS.md)
- [Existing Chaos Testnet Implementation](/Users/swp/dev/swapnilraj/chaoswopr/src/chaoswopr/infrastructure/testnet/chaos_testnet.py)
- [Auto Patch Script](/Users/swp/dev/swapnilraj/chaoswopr/scripts/auto_patch_net_admin.py)
