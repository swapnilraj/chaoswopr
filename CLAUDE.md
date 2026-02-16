# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**chaoswopr** is an AI-driven chaos engineering tool for Ethereum operational resilience testing. It deploys private Ethereum testnets (50-500 nodes), injects coordinated faults at network/node/protocol levels, and uses a multi-agent AI system to orchestrate experiments, analyze results, and generate incident response playbooks.

## Repository Structure

This project is currently in the **planning phase**. Key documents:

- **SPEC.md** - Complete technical specification and architecture
- **IMPLEMENTATION_PLAN.md** - Master plan with 3-phase roadmap, dependency graph, and critical path
- **PHASE1.md** - Foundation: Infrastructure, monitoring, safety systems (4 tracks, 23 tasks)
- **PHASE2.md** - Intelligence: Agent system, chaos injection, scenarios (4 tracks, 28 tasks)
- **PHASE3.md** - Analysis & Production: Reporting, compliance, scale testing (4 tracks, 26 tasks)

## Architecture (from SPEC.md)

### Core Components

1. **Infrastructure Layer** - Kurtosis wrapper around ethpandaops/ethereum-package for programmatic testnet deployment with multi-client support (Nethermind, Geth, Prysm, Lighthouse)

2. **Agent System** (three types):
   - **Orchestrator Agent**: Master controller using handrolled agent system - generates hypotheses, plans experiments, coordinates multi-fault injection, makes real-time SLO decisions
   - **Node Agents** (50-500 instances): AI agents controlling validator keys - 70% honest, 30% adversarial (withhold attestations, equivocate, censor txns, coordinate exits). Scaled via vLLM.
   - **Observer Agent**: Specialized LLM with RAG over Ethereum docs - real-time anomaly detection, SLO breach tracking, root cause analysis

3. **Chaos Injection Module** - Three levels:
   - Network: tc/netem (packet drops, latency, partitions)
   - Node: chaos-mesh (pod kills, CPU/mem/IO exhaustion)
   - Protocol: attestation withholding, equivocation, censorship, MEV manipulation

4. **Safety System** - Built into Phase 1, not bolted on later:
   - Blast radius limits (max 33% nodes)
   - Circuit breakers (finality >10min, slashing >5%)
   - K8s volume snapshots for rollback
   - ERC-8004-style audit logging

5. **Scenario Library** - YAML-defined experiments recreating real incidents:
   - may_2023_finality_loss.yaml (Prysm bug)
   - mass_validator_exit.yaml, mev_builder_censorship.yaml, etc.

6. **Analysis Module** - Statistical analysis (Mann-Whitney U tests), playbook generation, compliance reports (Basel/FI-ready PDFs), Grafana dashboards

### Execution Workflow (5-step)

PRE-FLIGHT → HYPOTHESIS → CHAOS → RECOVERY → ANALYSIS

Each phase has specific handoff points between agents.

## Key Technical Decisions

**Already decided in IMPLEMENTATION_PLAN.md:**

- **Primary language**: Python (best LLM ecosystem: LangGraph, vLLM, chaos tooling)
- **LLM orchestration**: LangGraph for Orchestrator, vLLM for Node Agent scaling
- **Infrastructure**: Kurtosis + ethpandaops/ethereum-package
- **Monitoring**: Prometheus + Grafana with custom beaconcha.in-style APIs
- **Chaos tools**: chaos-mesh (K8s), tc/netem (network), custom protocol injectors
- **Storage**: PostgreSQL for time-series, S3 for audit logs

**To be decided during Phase 1 Track A:**

- Kubernetes target (managed EKS/GKE vs. local kind/minikube - support both)
- Storage backend refinement (PostgreSQL vs. TimescaleDB/VictoriaMetrics)

## Implementation Sequence

**Dependencies are strict** - Phase 1 must complete before Phase 2 begins:

1. **Phase 1: Foundation** (Tracks A-D parallel) - Deploy working testnet with monitoring and safety before any chaos
2. **Phase 2: Intelligence** (Tracks E-H parallel) - Build all three agents and chaos injection module
3. **Phase 3: Analysis & Production** (Tracks I-L parallel) - Scale to 500 nodes, generate compliance artifacts

See **IMPLEMENTATION_PLAN.md** for the complete dependency graph and critical path (A2 → F4 → E3 → J1-J6 → K1).

## Safety-First Development

- Never skip safety system development (Phase 1 Track C)
- Circuit breakers must be testable before any chaos injection
- Blast radius calculations must be validated in unit tests
- Testnet isolation is mandatory - no mainnet contact
- All agent decisions must be audit-logged

## Scenario Schema

Scenarios are YAML files with this structure:
```yaml
hypothesis: "Network can finalize with X% validators offline"
fault_sequence:
  - time: 0s
    action: baseline
  - time: 60s
    action: inject_network_latency
    params: {nodes: 20%, latency: 200ms}
slo_thresholds:
  finality_delay_max: 5 epochs
  slashing_rate_max: 5%
success_criteria: "Finality maintained OR recovered in <5min"
```

Schema validation is built in Phase 1 Track D.

## Key Constraints

1. **Blast radius**: Never affect >33% of nodes simultaneously
2. **Circuit breakers**: Auto-halt on finality >10min or slashing >5%
3. **Phased rollout**: Faults start at 5% → 10% → 20% before full scale
4. **Client diversity**: Testnet must mirror mainnet ratios (40% Nethermind, 30% Geth, etc.)
5. **Real mainnet state**: Fork from live blocks for authentic conditions

## Critical Risks (from IMPLEMENTATION_PLAN.md)

- **Node Agent scaling bottleneck** at 500 instances (vLLM memory/GPU) - profile early in Phase 2
- **Orchestrator LLM hallucination** in hypothesis generation - constrain with validated templates
- **Circuit breaker race conditions** under extreme chaos - extensive testing in Phase 1

## Output Artifacts

The system generates:
- **Resilience certifications** ("Survived 15/15 scenarios")
- **Incident response playbooks** (auto-generated, operator-actionable)
- **Compliance reports** (PDF + JSON with audit trail)
- **Visual dashboards** (Grafana with experiment replay)

All outputs must be regulator-ready for Basel/FI compliance.

## When Working on This Project

1. **Always read SPEC.md first** for architectural context
2. **Consult IMPLEMENTATION_PLAN.md** for dependency ordering - don't build out of sequence
3. **Check phase documents** (PHASE1/2/3.md) for detailed task breakdowns
4. **Safety first** - never bypass circuit breakers or blast radius limits
5. **Real-world grounding** - reference the 6 pre-defined scenarios when building features
6. **Agent coordination** - the three-agent system has strict handoff protocols (PRE-FLIGHT → HYPOTHESIS → CHAOS → RECOVERY → ANALYSIS)

## No Code Yet

This repository currently contains only planning documents. Implementation will begin with Phase 1 Track A (project scaffolding) and Track B (Kurtosis infrastructure layer).
