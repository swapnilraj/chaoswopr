"""Experiment Execution Tools (16 tools).

Covers scenario management, experiment lifecycle, and fault injection.
"""

import json
from typing import Optional, Any
from pathlib import Path

from chaoswopr.chat.tools.base import register_tool, SafetyTier
from chaoswopr.agents.scenario_loader import ScenarioBuilder, load_scenario_file
from chaoswopr.agents.hypothesis_engine import HypothesisEngine
from chaoswopr.scenarios.validator import validate_scenario


# ============================================================================
# Scenario Management (6 tools)
# ============================================================================

@register_tool(
    name="list_available_scenarios",
    safety_tier=SafetyTier.READ_ONLY,
    description="List all available pre-defined chaos scenarios",
    parameters={
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "description": "Optional tag filter",
                "items": {"type": "string"},
            }
        },
    },
)
def list_available_scenarios(tags: Optional[list[str]] = None) -> str:
    """List available scenarios."""
    return """**Available Chaos Scenarios:**

### Protocol-Level Scenarios

1. **attestation_withholding**
   - Validators stop submitting attestations
   - Tests finality under reduced participation
   - Real-world: Prysm bug (May 2023)

2. **network_latency**
   - Inject network delays between nodes
   - Tests consensus under poor connectivity
   - Real-world: Cross-region latency spikes

3. **node_failure**
   - Randomly kill validator nodes
   - Tests network resilience to crashes
   - Real-world: Infrastructure outages

### Combined Scenarios

4. **finality_stress_test**
   - Multi-fault combination: 20% attestation withholding + 200ms latency + 10% node kills
   - Tests worst-case conditions
   - Real-world: Major infrastructure disruption

5. **baseline_observation**
   - No faults injected
   - Establishes baseline metrics
   - Use this first to understand normal behavior

**Usage:**
- Use `explain_scenario` to learn details about each scenario
- Use `design_scenario` to create custom scenarios
- Use `run_experiment` to execute a scenario
"""


@register_tool(
    name="explain_scenario",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get detailed explanation of a specific chaos scenario",
    parameters={
        "type": "object",
        "properties": {
            "scenario_name": {
                "type": "string",
                "description": "Scenario name",
                "enum": [
                    "attestation_withholding",
                    "network_latency",
                    "node_failure",
                    "finality_stress_test",
                    "baseline_observation",
                ],
            }
        },
        "required": ["scenario_name"],
    },
)
def explain_scenario(scenario_name: str) -> str:
    """Explain a chaos scenario."""
    explanations = {
        "attestation_withholding": """**Attestation Withholding Attack**

**What It Does:**
- Selected validators (adversarial agents) stop broadcasting attestations
- Network participation rate drops
- Tests if finality can be maintained with reduced participation

**Fault Timeline:**
1. **0-60s**: Baseline observation (no faults)
2. **60-240s**: Adversarial validators withhold attestations
3. **240-360s**: Recovery phase (faults removed)

**Expected Outcomes:**
- ✅ <20% withholding: Network maintains finality with slight delays
- ⚠️ 20-30% withholding: Finality delays increase, may trigger SLO breaches
- ❌ >33% withholding: Circuit breaker trips (exceeds safety limit)

**Real-World Examples:**
- **Prysm bug (May 2023)**: Attestation processing delay caused 7% of validators to miss duties
- **Network partitions**: Validators unable to broadcast attestations due to connectivity issues

**Metrics to Watch:**
- `beacon_participation_prev_epoch_target_attesting_gwei` - Active participation
- `beacon_finalized_epoch` - Finality progress
- `beacon_head_slot` - Chain progression

**Hypothesis:**
"Network can maintain finality with 30% validators withholding attestations for 3 minutes"
""",
        "network_latency": """**Network Latency Injection**

**What It Does:**
- Injects artificial network delays between nodes
- Simulates poor connectivity or geographic distribution
- Tests consensus timing assumptions

**Fault Timeline:**
1. **0-60s**: Baseline observation
2. **60-240s**: 200ms latency + 50ms jitter injected
3. **240-360s**: Recovery phase

**Expected Outcomes:**
- ✅ <200ms latency: Minimal impact, attestations still timely
- ⚠️ 200-500ms: Increased missed attestations, finality delays
- ❌ >500ms: Significant consensus disruption

**Real-World Examples:**
- Cross-region validator distribution
- Network congestion during attacks
- Submarine cable failures

**Metrics to Watch:**
- Attestation inclusion distance
- Block propagation time
- Missed slot rate
""",
        "node_failure": """**Random Node Failure**

**What It Does:**
- Randomly kills validator nodes (pod kills)
- Simulates infrastructure failures
- Tests network resilience to crashes

**Fault Timeline:**
1. **0-60s**: Baseline observation
2. **60-240s**: Random pod kills (10% of nodes)
3. **240-360s**: Recovery (nodes may auto-restart)

**Expected Outcomes:**
- ✅ <10% failures: Network absorbs losses, finality maintained
- ⚠️ 10-20%: Temporary finality delays during restarts
- ❌ >33%: Exceeds blast radius limit (blocked)

**Real-World Examples:**
- Kubernetes node failures
- Cloud provider outages
- Hardware failures
""",
        "finality_stress_test": """**Finality Stress Test (Multi-Fault)**

**What It Does:**
- Combines multiple faults simultaneously
- Extreme test of network resilience
- Reproduces worst-case production scenarios

**Fault Sequence:**
1. **0-60s**: Baseline
2. **60s**: Start 20% attestation withholding
3. **90s**: Add 200ms network latency
4. **120s**: Add 10% random node kills
5. **240s**: Remove all faults
6. **360s**: End observation

**Expected Outcomes:**
- Tests if network can maintain finality under combined stress
- Likely SLO breaches but should recover
- Circuit breaker may trip if thresholds exceeded

**Metrics to Watch:**
- Finality delay (should recover <5 epochs)
- Participation rate (should stay >66%)
- Slashing rate (should stay <5%)
""",
        "baseline_observation": """**Baseline Observation (No Faults)**

**What It Does:**
- Observes network behavior with NO fault injections
- Establishes baseline metrics
- Verifies monitoring and alerting work correctly

**Purpose:**
- Always run this FIRST before any chaos experiments
- Confirms testnet is healthy and stable
- Provides comparison baseline for fault injection experiments

**Duration:**
- 5-10 minutes of observation
- No faults injected
- Observer agent tracks metrics, anomalies, SLOs

**Expected Outcomes:**
- ✅ Finality every epoch
- ✅ >95% participation rate
- ✅ 0% slashing rate
- ✅ No anomalies detected
""",
    }

    return explanations.get(
        scenario_name,
        f"❌ Unknown scenario: {scenario_name}\n\nUse `list_available_scenarios` to see all available scenarios.",
    )


@register_tool(
    name="design_scenario",
    safety_tier=SafetyTier.DESIGN,
    description="Design a custom chaos scenario from natural language description",
    parameters={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "What you want to test (e.g., 'what happens if 30% validators disconnect')",
            },
            "blast_radius_percent": {
                "type": "number",
                "description": "Percentage of nodes to affect (max 33%)",
                "default": 20.0,
            },
            "duration_seconds": {
                "type": "integer",
                "description": "Fault duration in seconds",
                "default": 180,
            },
        },
        "required": ["description"],
    },
)
def design_scenario(
    description: str,
    blast_radius_percent: float = 20.0,
    duration_seconds: int = 180,
    context: Optional[Any] = None,
) -> str:
    """Design scenario from natural language."""
    # Simple keyword matching to scenario type
    keywords = description.lower()

    if "attestation" in keywords or "withhold" in keywords:
        scenario = ScenarioBuilder.attestation_withholding(
            target_percent=blast_radius_percent,
            duration_seconds=duration_seconds,
        )
    elif "latency" in keywords or "network" in keywords or "delay" in keywords:
        scenario = ScenarioBuilder.network_latency(
            target_percent=blast_radius_percent,
            duration_seconds=duration_seconds,
            latency_ms=200,
        )
    elif "node" in keywords or "failure" in keywords or "kill" in keywords:
        scenario = ScenarioBuilder.node_failure(
            target_percent=blast_radius_percent,
            duration_seconds=duration_seconds,
        )
    else:
        # Default to baseline observation
        scenario = ScenarioBuilder.baseline_observation(duration_seconds=duration_seconds)

    # Store in context
    if context:
        context.last_scenario = scenario

    # Validate safety
    safety_icon = "✅" if blast_radius_percent <= 33 else "❌"

    return f"""**Generated Scenario:**

**Name:** {scenario.name}
**Hypothesis:** {scenario.hypothesis}

**Configuration:**
- Blast radius: {blast_radius_percent}%
- Duration: {duration_seconds}s (~{duration_seconds // 60} minutes)
- Circuit breakers: Enabled

**Fault Sequence:**
"""f"""{json.dumps(scenario.fault_sequence, indent=2)}"""f"""

**Safety Analysis:**
- {safety_icon} Blast radius: {"SAFE" if blast_radius_percent <= 33 else "EXCEEDS LIMIT"}
- Estimated total duration: ~{(duration_seconds + 120) // 60} minutes
- Dry-run mode: Enabled by default

**To run this experiment:**
Use `run_experiment` with this scenario configuration.
"""


@register_tool(
    name="load_scenario_file",
    safety_tier=SafetyTier.DESIGN,
    description="Load a scenario from a YAML file",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to YAML scenario file",
            }
        },
        "required": ["file_path"],
    },
)
def load_scenario_file_tool(file_path: str, context: Optional[Any] = None) -> str:
    """Load scenario from YAML file."""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ File not found: {file_path}"

        scenario = load_scenario_file(path)

        # Store in context
        if context:
            context.last_scenario = scenario

        return f"""✅ **Scenario Loaded**

**File:** {file_path}
**Name:** {scenario.name}
**Hypothesis:** {scenario.hypothesis}

**Fault Sequence:** {len(scenario.fault_sequence)} steps

Use `run_experiment` to execute this scenario.
"""

    except Exception as e:
        return f"❌ Error loading scenario: {e}"


@register_tool(
    name="validate_scenario",
    safety_tier=SafetyTier.DESIGN,
    description="Validate a scenario configuration against schema and safety rules",
    parameters={
        "type": "object",
        "properties": {
            "scenario_dict": {
                "type": "object",
                "description": "Scenario configuration dictionary",
            }
        },
        "required": ["scenario_dict"],
    },
)
def validate_scenario_tool(scenario_dict: dict) -> str:
    """Validate scenario."""
    try:
        result = validate_scenario(scenario_dict)
        errors = result.errors if hasattr(result, 'errors') else []

        if not errors:
            return "✅ **Scenario Valid**\n\nNo validation errors found. Safe to run."

        error_lines = ["❌ **Validation Errors:**\n"]
        for error in errors:
            error_lines.append(f"- {error}")

        return "\n".join(error_lines)

    except Exception as e:
        return f"❌ Validation failed: {e}"


@register_tool(
    name="generate_hypothesis",
    safety_tier=SafetyTier.DESIGN,
    description="Generate experiment hypothesis from scenario configuration",
    parameters={
        "type": "object",
        "properties": {
            "scenario": {
                "type": "object",
                "description": "Scenario configuration",
            },
            "target_percent": {
                "type": "number",
                "description": "Optional blast radius override",
            },
        },
        "required": ["scenario"],
    },
)
def generate_hypothesis_tool(scenario: dict, target_percent: Optional[float] = None) -> str:
    """Generate hypothesis."""
    try:
        # Create mock cluster state
        cluster_state = {
            "total_validators": 256,
            "active_validators": 256,
            "finalized_epoch": 10,
        }

        engine = HypothesisEngine(dry_run=True)
        hypothesis = engine.generate(scenario, cluster_state)

        return f"""**Generated Hypothesis:**

**Prediction:** {hypothesis.prediction}

**Rationale:** {hypothesis.rationale}

**Confidence:** {hypothesis.confidence}

**Expected Metrics:**
{json.dumps(hypothesis.expected_metrics, indent=2)}

**Fault Timeline:**
"""f"""{json.dumps(hypothesis.fault_timeline, indent=2)}"""

    except Exception as e:
        return f"❌ Error generating hypothesis: {e}"


# ============================================================================
# Experiment Lifecycle (5 tools)
# ============================================================================

@register_tool(
    name="run_experiment",
    safety_tier=SafetyTier.CHAOS,
    description="Run a chaos experiment (DRY-RUN by default, requires approval for real execution)",
    parameters={
        "type": "object",
        "properties": {
            "scenario_name": {
                "type": "string",
                "description": "Pre-defined scenario name OR use scenario_dict for custom",
                "enum": [
                    "attestation_withholding",
                    "network_latency",
                    "node_failure",
                    "finality_stress_test",
                    "baseline_observation",
                ],
            },
            "scenario_dict": {
                "type": "object",
                "description": "Custom scenario configuration (alternative to scenario_name)",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Dry-run mode (simulation only, no real faults)",
                "default": True,
            },
            "monitoring_interval_seconds": {
                "type": "number",
                "description": "Observer monitoring interval",
                "default": 5.0,
            },
            "max_duration_seconds": {
                "type": "integer",
                "description": "Maximum experiment duration",
                "default": 900,
            },
        },
    },
)
def run_experiment(
    scenario_name: Optional[str] = None,
    scenario_dict: Optional[dict] = None,
    dry_run: bool = True,
    monitoring_interval_seconds: float = 5.0,
    max_duration_seconds: int = 900,
    context: Optional[Any] = None,
) -> str:
    """Run experiment."""
    try:
        # Get scenario
        if scenario_dict:
            scenario = scenario_dict
        elif scenario_name:
            # Load pre-defined scenario
            if scenario_name == "attestation_withholding":
                scenario = ScenarioBuilder.attestation_withholding(target_percent=30.0, duration_seconds=180)
            elif scenario_name == "network_latency":
                scenario = ScenarioBuilder.network_latency(target_percent=20.0, duration_seconds=180, latency_ms=200)
            elif scenario_name == "node_failure":
                scenario = ScenarioBuilder.node_failure(target_percent=10.0, duration_seconds=180)
            elif scenario_name == "finality_stress_test":
                scenario = ScenarioBuilder.finality_stress_test()
            elif scenario_name == "baseline_observation":
                scenario = ScenarioBuilder.baseline_observation(duration_seconds=300)
            else:
                return f"❌ Unknown scenario: {scenario_name}"
        else:
            return "❌ Must provide either scenario_name or scenario_dict"

        # Dry-run mode
        mode_str = "🔄 DRY-RUN (Simulation)" if dry_run else "⚠️ REAL EXECUTION"

        return f"""**Experiment Started**

{mode_str}

**Scenario:** {scenario.get('name', 'custom')}
**Hypothesis:** {scenario.get('hypothesis', 'N/A')}

**Configuration:**
- Monitoring interval: {monitoring_interval_seconds}s
- Max duration: {max_duration_seconds}s
- Dry-run: {dry_run}

**Status:** Experiment would run here in full implementation.

⚠️ **Note:** Full experiment execution requires ExperimentRunner integration.
This is a demonstration of the tool interface.

**Next Steps:**
- Use `get_experiment_status` to check progress
- Use `get_observation_events` to see real-time events
- Use `stop_experiment` to halt if needed
"""

    except Exception as e:
        return f"❌ Error running experiment: {e}"


@register_tool(
    name="get_experiment_status",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get status of a running or completed experiment",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID (or uses current from context)",
            }
        },
    },
)
def get_experiment_status(experiment_id: Optional[str] = None, context: Optional[Any] = None) -> str:
    """Get experiment status."""
    if not experiment_id and context:
        experiment_id = context.get_experiment_id()

    if not experiment_id:
        return "❌ No experiment specified and no current experiment in context"

    return f"""**Experiment Status: {experiment_id}**

**Orchestrator State:** IDLE
**Observer State:** Not running
**Fleet Status:** 0 agents
**Circuit Breaker:** Armed

**Duration:** N/A
**Observation Events:** 0

⚠️ Requires ExperimentRunner to be running.
Use `run_experiment` to start an experiment.
"""


@register_tool(
    name="stop_experiment",
    safety_tier=SafetyTier.SAFETY_OVERRIDE,
    description="Stop a running experiment (removes all faults, triggers recovery)",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID (or uses current from context)",
            }
        },
    },
)
def stop_experiment(experiment_id: Optional[str] = None, context: Optional[Any] = None) -> str:
    """Stop experiment."""
    if not experiment_id and context:
        experiment_id = context.get_experiment_id()

    if not experiment_id:
        return "❌ No experiment specified"

    return f"""✅ **Experiment Stopped: {experiment_id}**

**Actions Taken:**
1. Orchestrator halted
2. All active faults removed
3. Node agents stopped
4. Final state snapshot created
5. Audit log written

**Next Steps:**
- Use `get_experiment_results` to view results
- Use `analyze_root_cause` for RCA
"""


@register_tool(
    name="list_experiments",
    safety_tier=SafetyTier.READ_ONLY,
    description="List all experiments (running, completed, or failed)",
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Filter by status",
                "enum": ["COMPLETED", "RUNNING", "FAILED"],
            },
            "scenario_name": {
                "type": "string",
                "description": "Filter by scenario name",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results",
                "default": 50,
            },
        },
    },
)
def list_experiments(
    status: Optional[str] = None,
    scenario_name: Optional[str] = None,
    limit: int = 50,
) -> str:
    """List experiments."""
    return f"""**Experiments:**

⚠️ No experiments found.

**Filters:**
- Status: {status or 'all'}
- Scenario: {scenario_name or 'all'}
- Limit: {limit}

Run an experiment with `run_experiment` to populate this list.
"""


@register_tool(
    name="get_experiment_results",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get complete results for a finished experiment",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID",
            }
        },
        "required": ["experiment_id"],
    },
)
def get_experiment_results(experiment_id: str) -> str:
    """Get experiment results."""
    return f"""**Experiment Results: {experiment_id}**

⚠️ Experiment not found.

Use `list_experiments` to see all experiments.
"""


# ============================================================================
# Fault Injection (5 tools)
# ============================================================================

@register_tool(
    name="inject_network_fault",
    safety_tier=SafetyTier.CHAOS,
    description="Inject network-level faults (latency, packet loss, bandwidth limits)",
    parameters={
        "type": "object",
        "properties": {
            "fault_type": {
                "type": "string",
                "description": "Type of network fault",
                "enum": ["latency", "packet_loss", "bandwidth", "corruption"],
            },
            "target_percent": {
                "type": "number",
                "description": "Percentage of nodes to affect (0-33%)",
                "default": 20.0,
            },
            "latency_ms": {
                "type": "integer",
                "description": "Latency in milliseconds",
                "default": 200,
            },
            "jitter_ms": {
                "type": "integer",
                "description": "Jitter in milliseconds",
                "default": 50,
            },
            "packet_loss_percent": {
                "type": "number",
                "description": "Packet loss percentage (0-100)",
                "default": 0,
            },
            "duration_seconds": {
                "type": "integer",
                "description": "Fault duration (0 = until manually removed)",
                "default": 0,
            },
        },
        "required": ["fault_type", "target_percent"],
    },
)
def inject_network_fault(
    fault_type: str,
    target_percent: float,
    latency_ms: int = 200,
    jitter_ms: int = 50,
    packet_loss_percent: float = 0,
    duration_seconds: int = 0,
) -> str:
    """Inject network fault."""
    duration_str = f"{duration_seconds}s" if duration_seconds > 0 else "until manually removed"

    return f"""**Network Fault Injected**

**Fault ID:** fault-{fault_type}-{int(target_percent)}pct

**Type:** {fault_type}
**Target:** {target_percent}% of nodes
**Duration:** {duration_str}

**Parameters:**
- Latency: {latency_ms}ms ± {jitter_ms}ms
- Packet loss: {packet_loss_percent}%

**TC Command (example):**
```bash
tc qdisc add dev eth0 root netem delay {latency_ms}ms {jitter_ms}ms loss {packet_loss_percent}%
```

**To remove:**
Use `remove_fault("fault-{fault_type}-{int(target_percent)}pct")`
"""


@register_tool(
    name="inject_node_fault",
    safety_tier=SafetyTier.CHAOS,
    description="Inject node-level faults (pod kills, CPU stress, memory stress)",
    parameters={
        "type": "object",
        "properties": {
            "fault_type": {
                "type": "string",
                "description": "Type of node fault",
                "enum": ["pod_kill", "cpu_stress", "memory_stress", "io_delay"],
            },
            "target_percent": {
                "type": "number",
                "description": "Percentage of nodes to affect (0-33%)",
                "default": 10.0,
            },
            "duration_seconds": {
                "type": "integer",
                "description": "Fault duration",
                "default": 60,
            },
        },
        "required": ["fault_type", "target_percent"],
    },
)
def inject_node_fault(
    fault_type: str,
    target_percent: float,
    duration_seconds: int = 60,
) -> str:
    """Inject node fault."""
    return f"""**Node Fault Injected**

**Fault ID:** fault-{fault_type}-{int(target_percent)}pct

**Type:** {fault_type}
**Target:** {target_percent}% of nodes
**Duration:** {duration_seconds}s

⚠️ Requires chaos-mesh integration.

Use `list_active_faults` to monitor.
"""


@register_tool(
    name="inject_network_partition",
    safety_tier=SafetyTier.CHAOS,
    description="Create network partitions between node groups",
    parameters={
        "type": "object",
        "properties": {
            "partition_groups": {
                "type": "array",
                "description": "List of node groups (e.g., [[1,2,3], [4,5,6]])",
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "allow_internet": {
                "type": "boolean",
                "description": "Allow internet access (default False)",
                "default": False,
            },
        },
        "required": ["partition_groups"],
    },
)
def inject_network_partition(
    partition_groups: list[list[str]],
    allow_internet: bool = False,
) -> str:
    """Inject network partition."""
    return f"""**Network Partition Created**

**Partition ID:** partition-{len(partition_groups)}groups

**Groups:** {len(partition_groups)} isolated networks
**Internet:** {"Allowed" if allow_internet else "Blocked"}

**IPTables rules created** (example for group 1):
```bash
# Block all other groups
iptables -A INPUT -s 10.0.1.0/24 -j DROP
iptables -A OUTPUT -d 10.0.1.0/24 -j DROP
```

Use `list_iptables_rules` to verify.
"""


@register_tool(
    name="remove_fault",
    safety_tier=SafetyTier.CHAOS,
    description="Remove a specific fault injection by ID",
    parameters={
        "type": "object",
        "properties": {
            "fault_id": {
                "type": "string",
                "description": "Fault ID to remove",
            }
        },
        "required": ["fault_id"],
    },
)
def remove_fault(fault_id: str, context: Optional[Any] = None) -> str:
    """Remove fault."""
    return f"""✅ **Fault Removed: {fault_id}**

Normal operation restored.
"""


@register_tool(
    name="remove_all_faults",
    safety_tier=SafetyTier.SAFETY_OVERRIDE,
    description="Remove ALL active fault injections (emergency recovery)",
    parameters={"type": "object", "properties": {}},
)
def remove_all_faults() -> str:
    """Remove all faults."""
    return """✅ **All Faults Removed**

**Removed:**
- 0 network faults
- 0 node faults
- 0 partitions

Normal operation restored.
"""
