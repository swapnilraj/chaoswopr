"""Approval workflow UI components for ChaosWopr chat interface.

Provides Streamlit components for different safety tiers:
- Tier 3: Infrastructure approval (deploy, scale, destroy)
- Tier 4: Chaos approval (experiments, fault injection)
- Tier 5: Safety override approval (kill switch, restore)
"""

import streamlit as st
from typing import Any, Optional

from chaoswopr.chat.tools.base import SafetyTier


def request_approval(
    tool_name: str,
    arguments: dict,
    context: Any,
) -> bool:
    """Request user approval for a tool execution based on safety tier.

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments
        context: ConversationContext instance

    Returns:
        True if approved, False if denied
    """
    from chaoswopr.chat.tools.base import TOOLS_REGISTRY

    tool_def = TOOLS_REGISTRY.get(tool_name)
    if not tool_def:
        return False

    safety_tier = tool_def["safety_tier"]

    if safety_tier == SafetyTier.READ_ONLY or safety_tier == SafetyTier.DESIGN:
        # No approval needed
        return True

    elif safety_tier == SafetyTier.INFRASTRUCTURE:
        return show_infrastructure_approval(tool_name, arguments)

    elif safety_tier == SafetyTier.CHAOS:
        return show_chaos_approval(tool_name, arguments)

    elif safety_tier == SafetyTier.SAFETY_OVERRIDE:
        return show_override_approval(tool_name, arguments)

    return False


def show_infrastructure_approval(tool_name: str, arguments: dict) -> bool:
    """Show approval UI for infrastructure operations.

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments

    Returns:
        True if approved
    """
    with st.expander("🚀 **Infrastructure Operation - Approval Required**", expanded=True):
        st.markdown(f"### {tool_name}")

        # Show operation details
        if tool_name == "deploy_testnet":
            num_validators = arguments.get("num_validators", 256)
            num_nodes = num_validators // 128
            st.markdown(f"""
**Operation:** Deploy Ethereum Testnet

**Configuration:**
- Validators: {num_validators} ({num_nodes} nodes × 128 validators)
- Clients: {num_nodes} Geth + {num_nodes} Lighthouse
- Estimated time: 5-8 minutes
- Services: Prometheus, Grafana, Beacon APIs

**Impact:**
- Resource usage: ~{num_nodes * 2}GB RAM, ~{num_nodes * 4} CPU cores
- No destruction of existing resources
            """)

        elif tool_name == "destroy_testnet":
            enclave_name = arguments.get("enclave_name", "unknown")
            st.warning(f"""
**Operation:** Destroy Testnet

**Target:** `{enclave_name}`

**Impact:**
- ⚠️ All services will be stopped
- ⚠️ All data will be lost
- ⚠️ Cannot be undone

**Action:** This will permanently delete the testnet enclave.
            """)

        elif tool_name == "scale_testnet":
            target_validators = arguments.get("target_validators", 256)
            st.markdown(f"""
**Operation:** Scale Testnet

**Target:** {target_validators} validators

**Impact:**
- Testnet will be redeployed with new configuration
- Existing state will be lost
- Estimated time: 5-10 minutes
            """)

        else:
            # Generic infrastructure operation
            st.markdown(f"""
**Operation:** {tool_name}

**Arguments:**
```json
{arguments}
```

**Impact:** This operation will modify infrastructure resources.
            """)

        # Approval buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve", key=f"approve_{tool_name}", type="primary"):
                st.success("Operation approved!")
                return True
        with col2:
            if st.button("❌ Cancel", key=f"cancel_{tool_name}"):
                st.warning("Operation canceled")
                return False

    return False


def show_chaos_approval(tool_name: str, arguments: dict) -> bool:
    """Show approval UI for chaos operations (experiments, fault injection).

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments

    Returns:
        True if approved
    """
    with st.expander("⚠️ **Chaos Operation - Confirmation Required**", expanded=True):
        st.markdown(f"### {tool_name}")

        # Extract common parameters
        blast_radius = arguments.get("blast_radius_percent") or arguments.get("target_percent", 0)
        dry_run = arguments.get("dry_run", True)

        # Validation checks
        safety_checks = []

        # Blast radius check
        if blast_radius <= 33:
            safety_checks.append("✅ Blast radius within safety limit (≤33%)")
        else:
            safety_checks.append(f"❌ Blast radius exceeds limit: {blast_radius}% > 33%")

        # Dry-run check
        if dry_run:
            safety_checks.append("🔄 Dry-run mode enabled (simulation only)")
        else:
            safety_checks.append("⚠️ REAL EXECUTION (not a simulation)")

        # Show operation details
        if tool_name == "run_experiment":
            scenario_name = arguments.get("scenario_name", "custom")
            duration = arguments.get("max_duration_seconds", 900) // 60
            st.markdown(f"""
**Operation:** Run Chaos Experiment

**Scenario:** {scenario_name}
**Blast Radius:** {blast_radius}% of nodes
**Duration:** ~{duration} minutes
**Monitoring Interval:** {arguments.get("monitoring_interval_seconds", 5.0)}s

**Safety Checks:**
""")
            for check in safety_checks:
                st.markdown(f"- {check}")

        elif tool_name.startswith("inject_"):
            fault_type = arguments.get("fault_type", "unknown")
            duration = arguments.get("duration_seconds", 0)
            duration_str = f"{duration}s" if duration > 0 else "until manually removed"

            st.markdown(f"""
**Operation:** Inject Fault

**Fault Type:** {fault_type}
**Target:** {blast_radius}% of nodes
**Duration:** {duration_str}

**Parameters:**
```json
{arguments}
```

**Safety Checks:**
""")
            for check in safety_checks:
                st.markdown(f"- {check}")

        else:
            # Generic chaos operation
            st.markdown(f"""
**Operation:** {tool_name}

**Arguments:**
```json
{arguments}
```

**Safety Checks:**
""")
            for check in safety_checks:
                st.markdown(f"- {check}")

        # Require confirmation checkbox for real execution
        if not dry_run:
            st.error("⚠️ **WARNING: Real Execution**")
            confirm = st.checkbox(
                "I understand this is a REAL operation that will affect the testnet",
                key=f"confirm_{tool_name}",
            )
            if not confirm:
                st.warning("Please confirm to proceed")
                return False

        # Approval buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Execute", key=f"approve_{tool_name}", type="primary"):
                st.success("Operation approved!")
                return True
        with col2:
            if st.button("❌ Cancel", key=f"cancel_{tool_name}"):
                st.warning("Operation canceled")
                return False

    return False


def show_override_approval(tool_name: str, arguments: dict) -> bool:
    """Show approval UI for safety override operations.

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments

    Returns:
        True if approved
    """
    with st.expander("🛑 **SAFETY OVERRIDE - Confirmation Required**", expanded=True):
        st.markdown(f"### {tool_name}")

        st.error("⚠️ **WARNING: Safety Override Operation**")

        # Show operation details
        if tool_name == "restore_snapshot":
            snapshot_id = arguments.get("snapshot_id", "unknown")
            st.markdown(f"""
**Operation:** Restore Snapshot

**Snapshot ID:** `{snapshot_id}`

**This will:**
1. Stop all running experiments
2. Remove all active faults
3. Restore testnet state to snapshot
4. Overwrite current state

**⚠️ Current state will be lost. This cannot be undone.**
            """)

        elif tool_name == "remove_all_faults":
            st.markdown("""
**Operation:** Remove All Faults

**This will:**
1. Remove ALL active fault injections
2. Restore normal network/node operation
3. Write audit log entry

**Note:** This does not stop the experiment - use `stop_experiment` for that.
            """)

        elif tool_name == "stop_experiment":
            experiment_id = arguments.get("experiment_id", "current")
            st.markdown(f"""
**Operation:** Stop Experiment

**Experiment ID:** `{experiment_id}`

**This will:**
1. Halt the orchestrator
2. Stop all node agents
3. Remove all active faults
4. Generate final report

**Note:** This is a forceful stop. Recovery phase will be skipped.
            """)

        else:
            # Generic safety override
            st.markdown(f"""
**Operation:** {tool_name}

**Arguments:**
```json
{arguments}
```

**This is a safety-critical operation that overrides normal protections.**
            """)

        # Require typed confirmation
        st.warning("Type **CONFIRM** to proceed:")
        user_input = st.text_input(
            "Confirmation",
            key=f"confirm_{tool_name}",
            label_visibility="collapsed",
        )

        if user_input == "CONFIRM":
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🛑 Execute Override", key=f"approve_{tool_name}", type="primary"):
                    st.success("Override approved!")
                    return True
            with col2:
                if st.button("❌ Cancel", key=f"cancel_{tool_name}"):
                    st.warning("Operation canceled")
                    return False
        else:
            st.info("Approval disabled until confirmation entered")

    return False


def validate_blast_radius(target_percent: float, max_percent: float = 33.0) -> tuple[bool, str]:
    """Validate blast radius is within safety limits.

    Args:
        target_percent: Requested blast radius
        max_percent: Maximum allowed (default 33%)

    Returns:
        (is_valid, message) tuple
    """
    if target_percent <= max_percent:
        return True, f"✅ Blast radius {target_percent}% is within limit (≤{max_percent}%)"
    else:
        return False, f"❌ Blast radius {target_percent}% exceeds limit of {max_percent}%"
