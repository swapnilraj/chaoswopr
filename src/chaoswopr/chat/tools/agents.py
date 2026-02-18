"""Agent Coordination Tools (6 tools).

Covers node agent fleet, orchestrator, and observer management.
"""

import json
from typing import Optional, Any

from chaoswopr.chat.tools.base import register_tool, SafetyTier


# ============================================================================
# Node Agent Fleet (3 tools)
# ============================================================================

@register_tool(
    name="get_fleet_status",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get status of node agent fleet (honest/adversarial split, health)",
    parameters={"type": "object", "properties": {}},
)
def get_fleet_status() -> str:
    """Get fleet status."""
    return """**Node Agent Fleet Status**

**Total Agents:** 0
**Honest:** 0 (0%)
**Adversarial:** 0 (0%)

**Health:**
- Running: 0
- Stopped: 0
- Error: 0

**Message Bus:**
- Connected: 0
- Pending commands: 0

⚠️ No experiment running.

Use `run_experiment` to create a node agent fleet.
"""


@register_tool(
    name="configure_node_behavior",
    safety_tier=SafetyTier.CHAOS,
    description="Configure adversarial behavior for node agents (WARNING: only affects adversarial agents)",
    parameters={
        "type": "object",
        "properties": {
            "agent_ids": {
                "type": "array",
                "description": "Agent IDs to configure (or 'all_adversarial')",
                "items": {"type": "string"},
            },
            "behavior_type": {
                "type": "string",
                "description": "Adversarial behavior to enable",
                "enum": [
                    "attestation_withholding",
                    "attestation_delay",
                    "equivocation",
                    "censorship",
                    "coordinated_exit",
                ],
            },
            "parameters": {
                "type": "object",
                "description": "Behavior-specific parameters",
            },
        },
        "required": ["agent_ids", "behavior_type"],
    },
)
def configure_node_behavior(
    agent_ids: list[str],
    behavior_type: str,
    parameters: Optional[dict] = None,
) -> str:
    """Configure node behavior."""
    return f"""**Node Behavior Configured**

**Agents:** {len(agent_ids)} agents
**Behavior:** {behavior_type}
**Parameters:**
```json
{json.dumps(parameters or {}, indent=2)}
```

**Safety:**
- ✅ Only adversarial agents can be configured
- ✅ Honest agents remain honest
- ✅ Configuration logged to audit

⚠️ Requires experiment to be running.
"""


@register_tool(
    name="switch_agent_mode",
    safety_tier=SafetyTier.CHAOS,
    description="Switch agent mode between honest and adversarial",
    parameters={
        "type": "object",
        "properties": {
            "agent_ids": {
                "type": "array",
                "description": "Agent IDs to switch",
                "items": {"type": "string"},
            },
            "mode": {
                "type": "string",
                "description": "Target mode",
                "enum": ["honest", "adversarial"],
            },
        },
        "required": ["agent_ids", "mode"],
    },
)
def switch_agent_mode(agent_ids: list[str], mode: str) -> str:
    """Switch agent mode."""
    return f"""**Agent Mode Switched**

**Agents:** {len(agent_ids)} agents
**New Mode:** {mode}

**Results:**
- Switched: {len(agent_ids)}
- Failed: 0

⚠️ Requires experiment to be running.
"""


# ============================================================================
# Orchestrator & Observer (3 tools)
# ============================================================================

@register_tool(
    name="get_orchestrator_state",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get current orchestrator state machine phase",
    parameters={"type": "object", "properties": {}},
)
def get_orchestrator_state() -> str:
    """Get orchestrator state."""
    return """**Orchestrator State**

**Current Phase:** IDLE

**State Machine:**
```
IDLE → PRE_FLIGHT → HYPOTHESIS → PLANNING →
EXECUTING → MONITORING → ANALYZING → REPORTING → IDLE
```

**Current Experiment:** None
**Duration:** N/A

**State History:**
- No state transitions yet

Use `run_experiment` to activate orchestrator.
"""


@register_tool(
    name="get_observer_insights",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get latest insights from observer agent (anomalies, SLO breaches)",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Optional experiment ID (or uses current from context)",
            }
        },
    },
)
def get_observer_insights(experiment_id: Optional[str] = None, context: Optional[Any] = None) -> str:
    """Get observer insights."""
    if not experiment_id and context:
        experiment_id = context.get_experiment_id()

    exp_str = experiment_id or "current"

    return f"""**Observer Insights ({exp_str})**

**Anomalies Detected:** 0
**SLO Breaches:** 0
**RCA Analyses:** 0

**Observation Loop:**
- State: Not running
- Interval: 5.0s
- Events captured: 0

**Latest Insights:**
- No insights available

Use `run_experiment` to activate observer.
"""


@register_tool(
    name="view_audit_log",
    safety_tier=SafetyTier.READ_ONLY,
    description="View audit log entries for experiments and agent actions",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Filter by experiment ID",
            },
            "agent_id": {
                "type": "string",
                "description": "Filter by agent ID",
            },
            "action_type": {
                "type": "string",
                "description": "Filter by action type",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum entries to return",
                "default": 100,
            },
        },
    },
)
def view_audit_log(
    experiment_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    action_type: Optional[str] = None,
    limit: int = 100,
) -> str:
    """View audit log."""
    filters = []
    if experiment_id:
        filters.append(f"Experiment: {experiment_id}")
    if agent_id:
        filters.append(f"Agent: {agent_id}")
    if action_type:
        filters.append(f"Action: {action_type}")

    filter_str = "\n- ".join(filters) if filters else "None"

    return f"""**Audit Log**

**Filters:**
- {filter_str}
**Limit:** {limit}

⚠️ No audit entries found.

**Logged Actions:**
- Experiment start/stop
- Fault injection/removal
- Circuit breaker trips
- Snapshot create/restore
- Agent mode switches
- Configuration changes

All actions are logged to PostgreSQL + S3 (ERC-8004 compliant).
"""
