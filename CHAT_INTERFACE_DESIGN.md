# Chaos Engineering Chat Interface - Design Document

## Overview

A chat-based interface to make chaos engineering accessible to non-technical users while maintaining safety and control.

## Use Cases

### 1. Scenario Discovery & Design
**User**: "I want to test what happens if validators can't communicate"
**Assistant**:
- Explains network partition scenarios
- Generates YAML scenario file
- Shows expected impact
- User reviews and approves

### 2. Results Analysis
**User**: "Why did experiment abc123 fail?"
**Assistant**:
- Queries experiment results
- Analyzes metrics
- Explains in plain English: "The network lost finality because participation dropped to 61%, below the 66% threshold"

### 3. Guided Exploration
**User**: "What's the worst that could happen with MEV-boost?"
**Assistant**:
- Lists known MEV-boost failure modes
- Suggests testable scenarios
- Helps design experiments

### 4. Demo & Reporting
**User**: "Run the attestation withholding demo"
**Assistant**:
- Loads pre-approved demo scenario
- Deploys testnet
- Shows real-time progress
- Generates executive summary

---

## Tool Categories

### 🟢 Tier 1: Read-Only Tools (No Approval Needed)

```python
@tool(safety_level="read-only")
def explain_scenario(scenario_name: str) -> str:
    """Explain what a chaos scenario does in plain English.

    Example:
        explain_scenario("attestation_withholding")
        → "This scenario simulates validators failing to submit
           attestations, which can lead to finality delays..."
    """

@tool(safety_level="read-only")
def analyze_experiment(experiment_id: str) -> dict:
    """Analyze a past experiment and explain what happened.

    Returns:
        - Summary in plain English
        - Key metrics
        - What went wrong/right
        - Recommendations
    """

@tool(safety_level="read-only")
def query_metrics(
    metric_name: str,
    time_range: str = "last_5m"
) -> dict:
    """Query Prometheus metrics with natural language time ranges.

    Example:
        query_metrics("participation_rate", "during_experiment_abc123")
    """

@tool(safety_level="read-only")
def list_experiments(
    status: str = "all",  # all, success, failed, running
    limit: int = 10
) -> list[dict]:
    """List past experiments with summaries."""

@tool(safety_level="read-only")
def get_recommendations(context: str) -> list[str]:
    """Get scenario recommendations based on user goals.

    Example:
        get_recommendations("test finality under network stress")
        → ["attestation_withholding", "network_partition", ...]
    """
```

### 🟡 Tier 2: Design Tools (Generates Artifacts)

```python
@tool(safety_level="design")
def design_scenario(
    description: str,
    max_blast_radius_percent: float = 20.0
) -> dict:
    """Generate a scenario YAML from natural language description.

    Args:
        description: "Test what happens when 20% of validators
                      suddenly disconnect"

    Returns:
        - Generated YAML content
        - Estimated impact
        - Suggested duration
        - Safety analysis

    Note: Does NOT execute, just creates the artifact.
    """

@tool(safety_level="design")
def create_hypothesis(
    goal: str,
    network_size: int = 256
) -> dict:
    """Use LLM to generate an AI hypothesis for a goal.

    Example:
        create_hypothesis(
            "Prove the network can handle MEV-boost failure",
            network_size=128
        )
    """

@tool(safety_level="design")
def estimate_impact(scenario_yaml: str) -> dict:
    """Analyze a scenario and estimate impact before running.

    Returns:
        - Blast radius: "Will affect 51/256 nodes (20%)"
        - Duration: "~12 minutes"
        - Cost: "~$0.05 in LLM calls"
        - Risks: ["May cause finality delay", "No data loss expected"]
    """
```

### 🔴 Tier 3: Execute Tools (Requires Approval)

```python
@tool(safety_level="execute", requires_approval=True)
def deploy_testnet(
    num_validators: int,
    el_client: str = "geth",
    cl_client: str = "lighthouse",
    wait_for_finality: bool = True
) -> dict:
    """Deploy an Ethereum testnet via Kurtosis.

    Limits enforced:
        - Max validators: 500
        - Max deployment time: 10 minutes
        - Auto-cleanup after 2 hours

    Before execution, shows:
        - Resource usage: "2 Geth nodes, 2 Lighthouse nodes"
        - Deployment time: "~4 minutes"
        - Asks user: "Deploy testnet? [Yes/No]"
    """

@tool(safety_level="execute", requires_approval=True)
def run_experiment(
    scenario_name: str,
    testnet_url: str = None,  # If None, deploys new
    auto_cleanup: bool = True
) -> dict:
    """Run a complete chaos engineering experiment.

    Workflow:
        1. Show experiment plan (6 actions, 540s duration)
        2. Show blast radius (51/256 nodes affected)
        3. Ask approval: "Run experiment? [Yes/No]"
        4. If Yes: Execute with real-time updates
        5. If No: Save as draft experiment

    Returns:
        - Experiment ID
        - Real-time status updates
        - Link to results dashboard
    """

@tool(safety_level="execute", requires_approval=True)
def inject_fault(
    fault_type: str,  # "attestation_withholding", "network_partition", etc.
    target_percent: float,
    duration_seconds: int,
    testnet_id: str
) -> dict:
    """Inject a specific fault into a running testnet.

    Safety limits:
        - Max target_percent: 33%
        - Max duration: 30 minutes
        - Circuit breaker: Auto-removes if finality >10min

    Before execution:
        - Shows affected nodes: "Will target nodes 0-50 (20%)"
        - Shows rollback plan: "Auto-removes fault after 180s"
        - Asks: "Inject fault? [Yes/No]"
    """
```

---

## Safety Mechanisms

### 1. Progressive Disclosure

```
User: "Test network partition"