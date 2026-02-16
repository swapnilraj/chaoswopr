# Node Agents - Track F

## Overview

Node Agents are AI-controlled sidecar proxies that intercept Beacon API calls between validator clients and beacon nodes. They support both honest (70% of nodes) and adversarial (30% of nodes) operating modes, enabling protocol-level fault injection for chaos engineering experiments.

## Architecture

### Sidecar Pattern

Each Node Agent runs alongside a validator client, intercepting all Beacon API requests:

```
Validator Client → Node Agent Proxy → Beacon Node
                      ↓
                 Intercept & Modify
```

### Key Components

1. **NodeAgent** (`node_agent.py`)
   - Main agent class managing lifecycle
   - Mode switching (honest ↔ adversarial)
   - Proxy configuration
   - Audit logging integration

2. **BeaconAPIProxy** (`node_agent.py`)
   - HTTP proxy intercepting Beacon API calls
   - Request/response modification
   - Pluggable interceptor system

3. **Behaviors** (`node_agent_behaviors.py`)
   - HonestBehavior: Pass-through with audit logging
   - AttestationWithholding: Drop attestations
   - AttestationDelay: Delay attestation submission
   - BlockEquivocation: Propose conflicting blocks
   - TransactionCensoring: Filter transactions by address
   - CoordinatedExit: Trigger validator exits at specific slots

4. **REST API** (`node_agent_api.py`)
   - Orchestrator control interface
   - Batch command support
   - Status queries

## Usage

### Basic Agent Lifecycle

```python
from chaoswopr.agents import NodeAgent, NodeAgentConfig, AgentMode

# Create configuration
config = NodeAgentConfig(
    node_id="validator-1",
    beacon_api_url="http://localhost:5052",
    mode=AgentMode.HONEST,
    proxy_port=5053,
)

# Initialize agent
agent = NodeAgent(config=config)

# Start proxy
agent.start()

# Agent is now intercepting requests in honest mode
```

### Switching to Adversarial Mode

```python
from chaoswopr.agents.node_agent_behaviors import AttestationWithholding

# Switch mode
agent.switch_mode(AgentMode.ADVERSARIAL)

# Set adversarial behavior
behavior = AttestationWithholding(withhold_probability=0.5)
agent.set_behavior(behavior)

# Agent now withholds 50% of attestations
```

### REST API Control

```python
from chaoswopr.agents.node_agent_api import create_app
from fastapi import FastAPI
import uvicorn

# Create FastAPI app for the agent
app = create_app(agent)

# Run API server
uvicorn.run(app, host="0.0.0.0", port=8000)
```

Then control via HTTP:

```bash
# Get status
curl http://localhost:8000/status

# Switch mode
curl -X POST http://localhost:8000/switch_mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "adversarial"}'

# Set behavior
curl -X POST http://localhost:8000/set_behavior \
  -H "Content-Type: application/json" \
  -d '{
    "behavior_type": "attestation_withholding",
    "parameters": {"withhold_probability": 0.8}
  }'
```

### Batch Operations

```python
from chaoswopr.agents.node_agent_api import batch_mode_switch, batch_set_behavior

# Control multiple agents
agents = [agent1, agent2, agent3]

# Switch all to adversarial
results = batch_mode_switch(agents, AgentMode.ADVERSARIAL)

# Set same behavior on all
results = batch_set_behavior(
    agents,
    "attestation_delay",
    {"delay_seconds": 2.0}
)
```

## Behaviors Reference

### HonestBehavior (Default for 70% of nodes)

Pass-through proxy with audit logging. All requests are logged and forwarded unchanged to the beacon node.

```python
from chaoswopr.agents.node_agent_behaviors import HonestBehavior

behavior = HonestBehavior(
    audit_logger=audit_logger,
    node_id="validator-1"
)
```

### AttestationWithholding

Simulates validators withholding attestations, reducing network participation.

```python
from chaoswopr.agents.node_agent_behaviors import AttestationWithholding

# Withhold all attestations
behavior = AttestationWithholding(withhold_probability=1.0)

# Withhold 30% of attestations
behavior = AttestationWithholding(withhold_probability=0.3)
```

**Tests**: Network resilience to low participation rates

### AttestationDelay

Introduces artificial delay before submitting attestations.

```python
from chaoswopr.agents.node_agent_behaviors import AttestationDelay

# Delay by 2 seconds
behavior = AttestationDelay(delay_seconds=2.0)
```

**Tests**: Network handling of late attestations

### BlockEquivocation

Proposes conflicting blocks for the same slot (slashable offense).

```python
from chaoswopr.agents.node_agent_behaviors import BlockEquivocation

# Always equivocate
behavior = BlockEquivocation(equivocate_probability=1.0)
```

**Tests**: Slashing detection and network fork choice

### TransactionCensoring

Filters out transactions from specific addresses when proposing blocks.

```python
from chaoswopr.agents.node_agent_behaviors import TransactionCensoring

# Censor specific addresses
behavior = TransactionCensoring(
    target_addresses=["0x1234...", "0x5678..."],
    censor_probability=1.0
)
```

**Tests**: MEV manipulation and censorship resistance

### CoordinatedExit

Triggers validator exit at a specific slot.

```python
from chaoswopr.agents.node_agent_behaviors import CoordinatedExit

# Exit at slot 1000
behavior = CoordinatedExit(trigger_slot=1000)
```

**Tests**: Mass validator exit scenarios

## Integration with Orchestrator

The Orchestrator Agent uses the REST API to coordinate experiments:

1. **Pre-flight**: Start all agents in honest mode
2. **Hypothesis**: Switch 30% to adversarial, set behaviors
3. **Chaos**: Monitor as faults are injected via agent behaviors
4. **Recovery**: Switch all back to honest mode
5. **Analysis**: Query agent status and audit logs

## Audit Logging

All agent actions are logged via the `AuditLogger`:

```python
from chaoswopr.safety.audit import AuditLogger

audit_logger = AuditLogger(default_agent_id="validator-1")

config = NodeAgentConfig(
    node_id="validator-1",
    beacon_api_url="http://localhost:5052",
    audit_logging=True,
)

agent = NodeAgent(config=config, audit_logger=audit_logger)
```

Logged events:
- `node_agent_start`: Agent started
- `node_agent_stop`: Agent stopped
- `node_agent_mode_switch`: Mode changed
- `node_agent_request`: Request intercepted (honest mode)

## Testing

Run Node Agent tests:

```bash
# Unit tests
pytest tests/unit/test_node_agent.py -v
pytest tests/unit/test_node_agent_behaviors.py -v
pytest tests/unit/test_node_agent_api.py -v

# All agent tests
pytest tests/unit/test_node_agent*.py -v
```

## Implementation Status

**Track F: Node Agents - COMPLETE**

- [x] Task F1: NodeAgent base class with sidecar pattern
- [x] Task F2: Honest mode implementation (passthrough + audit logging)
- [x] Task F3: Adversarial behavior library (5 behaviors)
- [x] Task F4: Orchestrator command interface (REST API + batch commands)

**Test Coverage**: 43+ unit tests passing

## Next Steps

- **Integration with Track H (Chaos Injection)**: Node agents will coordinate with the chaos injection module for multi-level faults
- **Orchestrator Agent (Phase 2 Track E)**: Will use the Node Agent API to coordinate experiments
- **Scaling with vLLM (Phase 2)**: Scale to 500 node agents for production testing

## Files

```
src/chaoswopr/agents/
├── __init__.py              # Package exports
├── node_agent.py            # NodeAgent and BeaconAPIProxy
├── node_agent_behaviors.py  # Behavior library
├── node_agent_api.py        # REST API for orchestrator control
└── README.md                # This file

tests/unit/
├── test_node_agent.py       # NodeAgent tests
├── test_node_agent_behaviors.py  # Behavior tests
└── test_node_agent_api.py   # API tests
```
