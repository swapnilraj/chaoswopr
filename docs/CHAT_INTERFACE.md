# ChaosWopr Chat Interface - Complete Guide

## Overview

The ChaosWopr Chat Interface provides natural language access to **ALL** chaos engineering operations through an AI-powered conversational interface. It exposes 64 tools across 6 categories with built-in safety controls and approval workflows.

## Quick Start

### 1. Install Dependencies

```bash
pip install streamlit python-dotenv requests
```

### 2. Configure API Key

Create `.env` file in project root:

```env
OPENROUTER_API_KEY=your_api_key_here
```

### 3. Run Chat Interface

```bash
streamlit run src/chaoswopr/chat/streamlit_app.py
```

The interface will open at `http://localhost:8501`

## Tool Coverage (64 Tools)

### 🏗️ Infrastructure (12 tools)

**Testnet Lifecycle:**
- `deploy_testnet` - Deploy Ethereum testnet with validators
- `destroy_testnet` - Destroy testnet enclave
- `list_testnets` - List all enclaves
- `get_testnet_info` - Get enclave details
- `scale_testnet` - Scale validator count

**Monitoring & Metrics:**
- `query_prometheus` - Execute PromQL queries
- `get_metric_value` - Get specific metric value
- `list_available_metrics` - Browse 52-metric catalog
- `check_beacon_health` - Check beacon node status
- `wait_for_finality` - Wait for network finality
- `get_service_urls` - Get service endpoints
- `configure_client_diversity` - Set client distributions

### 🔍 Observability (15 tools)

**Network & Node Inspection:**
- `list_beacon_nodes` - List all beacon nodes
- `list_execution_nodes` - List all execution nodes
- `get_node_details` - Get detailed node info
- `list_validators` - List validators (requires Beacon API v2)
- `get_validator_details` - Get validator info
- `get_network_topology` - View peer connectivity graph

**Fault & Configuration Visibility:**
- `list_active_faults` - See current fault injections
- `get_fault_details` - Get fault configuration
- `list_tc_rules` - View traffic control rules
- `list_iptables_rules` - View partition rules
- `get_current_configuration` - View experiment config

**Alerting & Monitoring:**
- `list_active_alerts` - See firing alerts
- `get_prometheus_config` - View Prometheus settings
- `get_resource_usage` - View CPU/memory/disk/network
- `get_grafana_dashboards` - List dashboards

### 🎯 Experiment (16 tools)

**Scenario Management:**
- `list_available_scenarios` - Browse pre-defined scenarios
- `explain_scenario` - Get detailed scenario explanation
- `design_scenario` - Create custom scenario from natural language
- `load_scenario_file` - Load YAML scenario
- `validate_scenario` - Validate scenario configuration
- `generate_hypothesis` - Generate experiment hypothesis

**Experiment Lifecycle:**
- `run_experiment` - Execute chaos experiment (DRY-RUN by default)
- `get_experiment_status` - Check experiment state
- `stop_experiment` - Halt running experiment
- `list_experiments` - Browse experiment history
- `get_experiment_results` - Get complete results

**Fault Injection:**
- `inject_network_fault` - Inject latency/packet loss/bandwidth limits
- `inject_node_fault` - Inject pod kills/CPU stress/memory stress
- `inject_network_partition` - Create network partitions
- `remove_fault` - Remove specific fault
- `remove_all_faults` - Emergency recovery (removes all faults)

### 📊 Analysis (10 tools)

**Metrics & Monitoring:**
- `get_experiment_metrics` - Get time-series metrics
- `compare_experiments` - Statistical comparison

**Anomaly Detection:**
- `get_anomalies` - Get detected anomalies (Z-score, CUSUM, correlation)
- `get_slo_breaches` - Get SLO violations

**Root Cause Analysis:**
- `analyze_root_cause` - Perform RCA with LLM
- `get_observation_events` - Get observer event timeline

**Historical Analysis:**
- `get_scenario_success_rate` - Get success rate statistics
- `get_hypothesis_accuracy` - Compare predicted vs actual
- `search_experiments` - Search by keywords/date/blast radius
- `export_experiment_report` - Export PDF/JSON/Markdown report

### 🛡️ Safety (5 tools)

**Circuit Breakers:**
- `get_circuit_breaker_status` - View circuit breaker state
- `configure_circuit_breaker` - Update thresholds

**Snapshots:**
- `create_snapshot` - Create testnet state snapshot
- `restore_snapshot` - Restore from snapshot (WARNING: overwrites state)
- `list_snapshots` - Browse available snapshots

### 🤖 Agents (6 tools)

**Node Agent Fleet:**
- `get_fleet_status` - View agent fleet (honest/adversarial split)
- `configure_node_behavior` - Set adversarial behavior
- `switch_agent_mode` - Switch between honest/adversarial

**Orchestrator & Observer:**
- `get_orchestrator_state` - View state machine phase
- `get_observer_insights` - Get latest anomalies/SLOs
- `view_audit_log` - View ERC-8004 compliant audit log

## Safety Tiers

All tools are categorized into 5 safety tiers with automatic approval workflows:

### 🟢 Tier 1: Read-Only (No Approval)
All `get_*`, `list_*`, `check_*`, `view_*` tools. Safe to execute without confirmation.

**Examples:**
- `list_available_scenarios`
- `get_testnet_info`
- `check_beacon_health`

### 🟡 Tier 2: Design (No Approval)
Hypothesis generation, scenario design, validation. No infrastructure impact.

**Examples:**
- `design_scenario`
- `generate_hypothesis`
- `validate_scenario`

### 🟠 Tier 3: Infrastructure (Approval Required)
Testnet deployment, scaling, destruction. Shows approval dialog with resource estimates.

**Examples:**
- `deploy_testnet` → Shows validator count, estimated time, resources
- `destroy_testnet` → Shows warning about data loss
- `scale_testnet` → Shows impact preview

**Approval UI:**
```
🚀 Infrastructure Operation - Approval Required

Operation: Deploy Ethereum Testnet

Configuration:
- Validators: 256 (2 nodes × 128 validators)
- Estimated time: 5-8 minutes
- Impact: ~4GB RAM, ~8 CPU cores

[✅ Approve] [❌ Cancel]
```

### 🔴 Tier 4: Chaos (Approval + Confirmation)
Running experiments, injecting faults. Shows safety review with blast radius validation.

**Examples:**
- `run_experiment(dry_run=False)` → Requires checkbox confirmation
- `inject_network_fault` → Shows affected nodes, duration
- `inject_node_fault` → Shows safety checks

**Approval UI:**
```
⚠️ Chaos Operation - Confirmation Required

Scenario: Attestation Withholding (30% validators)
Blast Radius: 15 nodes (30% of 50) ✅ Under 33% limit
Duration: 10 minutes

Safety Checks:
✅ Circuit breaker armed
✅ Snapshot created: snapshot-xyz789
✅ Blast radius validated
⚠️ This is a REAL experiment (not dry-run)

☑ I understand this is a REAL operation

[✅ Execute] [❌ Cancel]
```

### ⛔ Tier 5: Safety Override (Approval + Warning)
Kill switch, snapshot restore, remove all faults. Requires typed "CONFIRM".

**Examples:**
- `restore_snapshot` → Overwrites current state
- `remove_all_faults` → Emergency recovery
- `stop_experiment` → Forceful halt

**Approval UI:**
```
🛑 SAFETY OVERRIDE - Confirmation Required

Operation: Restore Snapshot

This will:
1. Stop all running experiments
2. Remove all active faults
3. Restore testnet state to snapshot
4. Overwrite current state

⚠️ Current state will be lost. This cannot be undone.

Type CONFIRM to proceed:
[_________________]

[🛑 Execute Override] [❌ Cancel]
```

## Example Conversations

### Conversation 1: First-Time User Exploration

```
User: "What can I do with this?"
Assistant: [Explains capabilities, suggests starting with scenario exploration]

User: "What scenarios are available?"
Assistant: [Calls list_available_scenarios]
   → Shows 5 pre-defined scenarios with descriptions

User: "Tell me more about attestation withholding"
Assistant: [Calls explain_scenario("attestation_withholding")]
   → Detailed explanation with real-world examples (Prysm bug May 2023)
   → Expected outcomes based on percentage

User: "Can I test this on a small network?"
Assistant: [Suggests deploying testnet first]
   → "Would you like to deploy a testnet with 128 validators?"
```

### Conversation 2: Deploy and Run Experiment

```
User: "Deploy a testnet with 256 validators"
Assistant: [Calls deploy_testnet(256, wait_for_finality=True)]
   → Shows Infrastructure Approval UI (Tier 3)
   → User approves
   → Deployment starts (5-8 minutes)
   → Returns enclave name, Prometheus URL, service list
   → Context updated: current_enclave_name set

User: "Run the attestation withholding scenario at 30%"
Assistant: [Calls design_scenario]
   → Shows scenario preview with safety analysis
   → [Calls run_experiment(dry_run=False)]
   → Shows Chaos Approval UI (Tier 4)
   → User confirms checkbox and approves
   → Experiment starts (dry-run mode can be toggled)
   → Context updated: current_experiment_id set
   → Streams observation events

User: "What's happening?"
Assistant: [Calls get_experiment_status]
   → Shows orchestrator phase, observer state, circuit breaker status
```

### Conversation 3: Investigate Failure

```
User: "Why did experiment abc123 fail?"
Assistant: [Calls get_experiment_results("abc123")]
   → Shows halt_reason: "Circuit breaker trip"
   → [Calls get_circuit_breaker_status()]
   → Shows trip event details
   → [Calls analyze_root_cause("abc123")]
   → Shows RCA hypotheses with evidence
   → Synthesizes: "Circuit breaker tripped due to finality delay >600s.
                   Root cause: 50% packet loss exceeded consensus gossip threshold.
                   Evidence: Finality delayed 12 epochs, attestation inclusion rate 45%"

User: "How do I fix this?"
Assistant: [Provides recommendations from RCA]
   → Reduce packet loss to <20%
   → Increase gossip timeout parameters
   → Monitor attestation inclusion distance
```

### Conversation 4: Advanced Inspection

```
User: "Show me the current network topology"
Assistant: [Calls list_beacon_nodes()]
   → Shows all beacon nodes with status
   → [Calls get_network_topology()]
   → Displays peer connectivity graph
   → "Would you like to inject a network partition?"

User: "Yes, partition 30% of nodes"
Assistant: [Calls inject_network_partition()]
   → Shows Chaos Approval UI with partition preview
   → User approves
   → Shows affected nodes, iptables rules
   → [Calls list_iptables_rules()]
   → Shows active rules on each node
```

## Conversation Context Tracking

The chat maintains conversation context to enable natural references:

**Context Fields:**
- `current_enclave_name` - Active testnet
- `current_experiment_id` - Running experiment
- `last_scenario` - Recently designed scenario
- `recent_experiment_ids` - Last 10 experiments
- `recent_fault_ids` - Last 10 fault injections
- `recent_snapshot_ids` - Last 10 snapshots

**Natural References:**
```
User: "Deploy a testnet"
→ Context: current_enclave_name = "chaoswopr-chat-1234567890"

User: "Check the testnet"
→ Resolves to get_testnet_info(enclave_name="chaoswopr-chat-1234567890")

User: "Run an experiment"
→ Context: current_experiment_id = "abc123..."

User: "Why did it fail?"
→ Resolves to get_experiment_results(experiment_id="abc123...")
```

**Clear Context:**
Use the sidebar "Clear Context" button to reset for a new experiment.

## Architecture

### File Structure

```
src/chaoswopr/chat/
├── streamlit_app.py              # Main Streamlit UI
├── conversation_context.py       # Session state management
├── approval_workflows.py         # Tier 3-5 approval UIs
├── tools/
│   ├── __init__.py               # Export TOOLS_REGISTRY
│   ├── base.py                   # Tool registry, execution framework
│   ├── infrastructure.py         # 12 infrastructure tools
│   ├── observability.py          # 15 observability tools
│   ├── experiment.py             # 16 experiment tools
│   ├── analysis.py               # 10 analysis tools
│   ├── safety.py                 # 5 safety tools
│   └── agents.py                 # 6 agent tools
```

### Tool Registration Pattern

Tools use decorator-based registration:

```python
@register_tool(
    name="deploy_testnet",
    safety_tier=SafetyTier.INFRASTRUCTURE,
    description="Deploy an Ethereum testnet",
    parameters={
        "type": "object",
        "properties": {
            "num_validators": {"type": "integer", "default": 256}
        },
        "required": ["num_validators"]
    }
)
def deploy_testnet(num_validators: int, context: Optional[Any] = None) -> str:
    # Implementation
    pass
```

This automatically:
- Registers tool in TOOLS_REGISTRY
- Generates OpenAI-compatible schema for LLM
- Enforces safety tier on execution
- Validates parameters against schema

### Execution Flow

```
User message
    ↓
LLM (Claude Opus 4)
    ↓
Tool selection + arguments
    ↓
validate_tool_params()
    ↓
Check safety tier
    ↓
[Tier 3-5] → Request approval UI
    ↓
[Approved] → execute_tool()
    ↓
Update context
    ↓
Format result (markdown)
    ↓
Display in chat
```

### Safety Enforcement

**Blast Radius Validation:**
```python
validate_tool_params("inject_network_fault", {"target_percent": 40})
→ (False, "target_percent must be 0-33%, got 40%")
```

**Approval Required:**
```python
execute_tool("deploy_testnet", {...}, approval_granted=False)
→ "⚠️ This operation requires approval (Safety Tier INFRASTRUCTURE)"
```

**Audit Logging:**
All tool executions are logged (success and failures) for compliance.

## Testing

### Manual Testing Checklist

- [ ] All 64 tools listed in sidebar
- [ ] Tool execution works for each category
- [ ] Approval workflows display correctly
- [ ] Context preserved across conversation turns
- [ ] Blast radius violations are blocked
- [ ] Error messages are user-friendly
- [ ] Markdown rendering works correctly

### Example Test Conversation

```python
# Test read-only tools (no approval)
User: "List available scenarios"
→ Should execute immediately

# Test infrastructure tools (approval required)
User: "Deploy a testnet with 256 validators"
→ Should show approval UI
→ After approval, should execute

# Test chaos tools (approval + confirmation)
User: "Run attestation withholding experiment at 30%"
→ Should show safety review
→ Should require checkbox confirmation
→ After approval, should execute

# Test context tracking
User: "Deploy a testnet"
User: "Check the testnet"
→ Should resolve enclave name from context

# Test blast radius enforcement
User: "Inject network fault on 50% of nodes"
→ Should fail validation (exceeds 33% limit)
```

## Troubleshooting

### "OPENROUTER_API_KEY not configured"

**Solution:**
1. Create `.env` file in project root
2. Add: `OPENROUTER_API_KEY=your_key_here`
3. Restart Streamlit app

### "No tools registered"

**Solution:**
- Check imports in `tools/__init__.py`
- Verify all tool modules are present
- Check Python version (requires 3.11+)

### "Approval UI not showing"

**Solution:**
- Check safety tier assignment in tool definition
- Verify `request_approval()` is called for Tier 3+ tools
- Check Streamlit session state

### "Context not preserved"

**Solution:**
- Verify `chaoswopr_context` in session state
- Check `context.set_enclave()` / `set_experiment()` calls
- Use "Clear Context" button to reset

## Future Enhancements

### Planned Features

1. **Multi-Modal Output:**
   - Inline Grafana dashboard embeds
   - Real-time metric charts
   - Network topology visualizations

2. **Advanced Workflows:**
   - Multi-step experiment planning wizard
   - Scenario comparison (side-by-side results)
   - Automated playbook generation

3. **Team Collaboration:**
   - Shared experiment history
   - Annotation and comments
   - Role-based access control (RBAC)

4. **Enhanced LLM Integration:**
   - Structured reasoning for hypothesis generation
   - Multi-agent debate for RCA
   - Automated scenario synthesis from incident reports

## Contributing

To add a new tool:

1. **Choose category:** infrastructure, observability, experiment, analysis, safety, or agents
2. **Add to appropriate file:** `tools/{category}.py`
3. **Use registration decorator:**
   ```python
   @register_tool(
       name="your_tool_name",
       safety_tier=SafetyTier.READ_ONLY,  # or appropriate tier
       description="What your tool does",
       parameters={...}  # OpenAI-compatible schema
   )
   def your_tool_name(...) -> str:
       # Return markdown-formatted result
       pass
   ```
4. **Tool automatically available** in chat interface
5. **Add to documentation:** Update this README

## License

See main ChaosWopr LICENSE file.

## Support

For issues or questions:
- Check troubleshooting section above
- Review example conversations
- Consult CLAUDE.md for project context