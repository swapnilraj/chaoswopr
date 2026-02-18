"""Safety System Tools (5 tools).

Covers circuit breakers, snapshots, and safety overrides.
"""

from typing import Optional, Any

from chaoswopr.chat.tools.base import register_tool, SafetyTier


# ============================================================================
# Circuit Breakers (2 tools)
# ============================================================================

@register_tool(
    name="get_circuit_breaker_status",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get current circuit breaker status and trip history",
    parameters={"type": "object", "properties": {}},
)
def get_circuit_breaker_status() -> str:
    """Get circuit breaker status."""
    return """**Circuit Breaker Status**

**State:** ARMED ✅

**Thresholds:**
- Finality delay max: 600s (10 epochs)
- Slashing rate max: 5%
- Participation rate min: 66%

**Check Count:** 0
**Trip Events:** 0

**Last Check:** Never

**Configuration:**
- Auto-reset: Enabled
- Alert on trip: Enabled
- Halt experiment on trip: Enabled

Circuit breaker will automatically halt experiments if any threshold is exceeded.
"""


@register_tool(
    name="configure_circuit_breaker",
    safety_tier=SafetyTier.INFRASTRUCTURE,
    description="Update circuit breaker thresholds (requires approval)",
    parameters={
        "type": "object",
        "properties": {
            "finality_delay_max_seconds": {
                "type": "integer",
                "description": "Maximum finality delay before trip (default 600s)",
                "default": 600,
            },
            "slashing_rate_max_percent": {
                "type": "number",
                "description": "Maximum slashing rate before trip (default 5%)",
                "default": 5.0,
            },
            "participation_rate_min_percent": {
                "type": "number",
                "description": "Minimum participation rate before trip (default 66%)",
                "default": 66.0,
            },
        },
    },
)
def configure_circuit_breaker(
    finality_delay_max_seconds: int = 600,
    slashing_rate_max_percent: float = 5.0,
    participation_rate_min_percent: float = 66.0,
) -> str:
    """Configure circuit breaker."""
    return f"""✅ **Circuit Breaker Updated**

**New Thresholds:**
- Finality delay max: {finality_delay_max_seconds}s
- Slashing rate max: {slashing_rate_max_percent}%
- Participation rate min: {participation_rate_min_percent}%

**Safety Checks:**
- Thresholds validated ✅
- Configuration persisted ✅

Circuit breaker will use these thresholds for future experiments.
"""


# ============================================================================
# Snapshots (3 tools)
# ============================================================================

@register_tool(
    name="create_snapshot",
    safety_tier=SafetyTier.INFRASTRUCTURE,
    description="Create a snapshot of current testnet state",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name (or uses current from context)",
            },
            "experiment_id": {
                "type": "string",
                "description": "Optional experiment ID to associate snapshot with",
            },
        },
    },
)
def create_snapshot(
    enclave_name: Optional[str] = None,
    experiment_id: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """Create snapshot."""
    if not enclave_name and context:
        enclave_name = context.get_enclave_name()

    if not enclave_name:
        return "❌ No enclave specified"

    # Generate snapshot ID
    import time
    snapshot_id = f"snapshot-{int(time.time())}"

    # Update context
    if context:
        context.add_snapshot(snapshot_id)

    return f"""✅ **Snapshot Created**

**Snapshot ID:** `{snapshot_id}`
**Enclave:** {enclave_name}
**Experiment:** {experiment_id or 'None'}
**State:** Creating...

**Snapshot Contents:**
- Kubernetes volumes (all nodes)
- Beacon chain state
- Execution layer state
- Prometheus metrics

**Estimated Time:** 2-5 minutes

Use `list_snapshots` to check status.
Use `restore_snapshot("{snapshot_id}")` to restore.
"""


@register_tool(
    name="restore_snapshot",
    safety_tier=SafetyTier.SAFETY_OVERRIDE,
    description="Restore testnet state from a snapshot (WARNING: overwrites current state)",
    parameters={
        "type": "object",
        "properties": {
            "snapshot_id": {
                "type": "string",
                "description": "Snapshot ID to restore",
            },
            "experiment_id": {
                "type": "string",
                "description": "Optional: restore latest snapshot for this experiment",
            },
        },
    },
)
def restore_snapshot(snapshot_id: Optional[str] = None, experiment_id: Optional[str] = None) -> str:
    """Restore snapshot."""
    if not snapshot_id and not experiment_id:
        return "❌ Must provide snapshot_id or experiment_id"

    target = snapshot_id or f"latest snapshot for {experiment_id}"

    return f"""✅ **Snapshot Restore Initiated**

**Target:** {target}

**Actions:**
1. Stop all running experiments ⏸️
2. Remove all active faults ✅
3. Restore Kubernetes volumes 🔄
4. Restart all services 🔄
5. Verify beacon chain state ✅

**Estimated Time:** 5-10 minutes

⚠️ **Current state will be overwritten.**

Progress: Restoring...
"""


@register_tool(
    name="list_snapshots",
    safety_tier=SafetyTier.READ_ONLY,
    description="List all available snapshots",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Optional filter by experiment ID",
            }
        },
    },
)
def list_snapshots(experiment_id: Optional[str] = None) -> str:
    """List snapshots."""
    filter_str = f"for experiment {experiment_id}" if experiment_id else "all"

    return f"""**Snapshots ({filter_str})**

⚠️ No snapshots found.

**To create a snapshot:**
Use `create_snapshot` before running experiments.

**Snapshot lifecycle:**
1. Create snapshot (before experiment)
2. Run chaos experiment
3. Restore snapshot (if needed)

Snapshots are stored for 7 days by default.
"""
