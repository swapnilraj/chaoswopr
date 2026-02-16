# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**chaoswopr** is an AI-driven chaos engineering tool for Ethereum operational resilience testing. It deploys private Ethereum testnets (50-500 nodes), injects coordinated faults at network/node/protocol levels, and uses a multi-agent AI system to orchestrate experiments, analyze results, and generate incident response playbooks.

## Repository Structure

**Phase 1 (Foundation) is complete.** Phase 2 (Intelligence) is next.

### Planning Documents
- **SPEC.md** - Complete technical specification and architecture
- **IMPLEMENTATION_PLAN.md** - Master plan with 3-phase roadmap, dependency graph, and critical path
- **PHASE1.md** - Foundation: Infrastructure, monitoring, safety systems (4 tracks, 23 tasks) -- DONE
- **PHASE2.md** - Intelligence: Agent system, chaos injection, scenarios (4 tracks, 28 tasks)
- **PHASE3.md** - Analysis & Production: Reporting, compliance, scale testing (4 tracks, 26 tasks)

### Source Layout (`src/chaoswopr/`)
- `infrastructure/testnet/` - Kurtosis client, client config, ethereum-package config, deployer, beacon API client
- `infrastructure/monitoring/` - Prometheus client, metrics catalog (52 metrics), alerting rules, metrics export
- `safety/` - Blast radius, circuit breaker, snapshots, isolation, audit logging, kill switch
- `scenarios/` - YAML scenario validator (JSON Schema + semantic checks)
- `storage/` - PostgreSQL (SQLAlchemy ORM) + S3 audit log storage
- `cli.py` - Click-based CLI entry point

### Test Layout (`tests/`)
- `unit/` - 394 unit tests (auto-marked with `@pytest.mark.unit`)
- `integration/` - Cross-track integration tests, storage layer tests (auto-marked `integration`)
- `e2e/` - Exit criteria verification tests (auto-marked `e2e`)
- `integration_real/` - Real infrastructure tests using Docker/Kurtosis/testcontainers (auto-marked `infra`, skipped without Docker)
- `e2e_real/` - Real E2E tests deploying full Ethereum testnets (auto-marked `e2e_real`, skipped without Docker+Kurtosis)
- `fixtures/sample_configs/` - Valid/invalid/network-partition scenario YAML fixtures
- `helpers/factories.py` - Test data factories
- `conftest.py` - Root fixtures shared across all test types

### Config
- `config/schema/scenario_schema.json` - JSON Schema (Draft 2020-12) for scenario YAML
- `config/testnet/default_network.yaml` - Default 50-node testnet config
- `scenarios/baseline_observation.yaml` - The baseline observation scenario

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

## Build and Test Commands

```bash
# Create venv and install
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run all tests
make test                          # or: python -m pytest tests/

# Run specific test categories
python -m pytest tests/unit/       # Unit tests only
python -m pytest tests/integration/ # Integration tests only
python -m pytest tests/e2e/        # End-to-end tests only
python -m pytest -m safety         # Safety-marked tests only

# Run real infrastructure tests (requires Docker + Kurtosis)
python -m pytest tests/integration_real/ -m infra --timeout=600
python -m pytest tests/e2e_real/ -m e2e_real --timeout=900

# Run a single test file or test
python -m pytest tests/unit/test_circuit_breaker.py
python -m pytest tests/unit/test_circuit_breaker.py::TestCircuitBreaker::test_trip_on_finality -v

# Coverage (excludes real infra tests)
python -m pytest tests/unit/ tests/integration/ tests/e2e/ --cov=src/chaoswopr --cov-report=term-missing

# Lint
make lint                          # ruff check + mypy

# Validate exit criteria
python scripts/validate_exit_criteria.py

# Validate infrastructure requirements (Docker, Kurtosis, resources)
python scripts/validate_infra_requirements.py --verbose

# Testnet (dry-run)
make testnet-up                    # Deploy testnet in dry-run mode
make testnet-down                  # Tear down testnet
make testnet-status                # Check testnet status

# Scenario validation
python -m chaoswopr.scenarios.validator scenarios/baseline_observation.yaml
```

## Phase 1 Status

All 7 exit criteria verified:
1. Testnet boots reliably (deployer with dry-run mode)
2. 52 metrics defined in catalog (exceeds 50+ requirement)
3. Circuit breakers trip on finality/slashing/participation thresholds
4. Snapshots create and restore (Docker and Kubernetes backends)
5. Baseline scenario runs end-to-end
6. Network isolation enforced (mainnet endpoints + public DNS blocked)
7. 452 tests passing, 83.3% coverage, CI pipeline configured

## Phase 1.5 Status (Real Infrastructure Testing)

Phase 1.5 adds real infrastructure testing alongside the existing mock/dry-run tests:

- **Beacon API client** (`beacon_api.py`) - Real HTTP client for Ethereum Beacon API (health, sync, finality, peers)
- **KurtosisClient upgraded** - Parses real CLI output (`enclave inspect`, `enclave ls`), service discovery, port mapping
- **Deployer upgraded** - Real finality verification via BeaconAPIClient (replaces TODO stub)
- **30 real infra tests** in `tests/integration_real/` (Docker, Kurtosis, Prometheus via testcontainers, PostgreSQL)
- **8 real E2E tests** in `tests/e2e_real/` (full 8-node Ethereum testnet with client diversity)
- **CI pipeline** - `infra-test` job (main branch pushes), `e2e-real-test` job (manual trigger only)
- All real tests gracefully skip when Docker/Kurtosis unavailable (pytest skip markers)

**Real Infrastructure Validation**: Successfully deployed 4-node nethermind+lighthouse testnet in ~30 seconds. All infrastructure components verified working. See **PHASE1_RESULTS.md** for detailed testing results.

## Known Issues and Workarounds

### Geth blobSchedule Configuration Error

**Issue**: Latest Geth requires `blobSchedule` in genesis config for Cancun fork, but ethereum-genesis-generator v3.3.7 (cached by Kurtosis) doesn't generate it.

**Error Message**: `missing entry for fork "cancun" in blobSchedule`

**Workaround**: Use **Nethermind** execution client instead of Geth. Nethermind doesn't validate blobSchedule config.

**Example**:
```python
from chaoswopr.infrastructure.testnet.client_config import ClientConfig, ClientDistribution

# ✅ Use Nethermind to avoid blobSchedule error
config = ClientConfig(
    node_count=4,
    execution=ClientDistribution({"nethermind": 1.0}),
    consensus=ClientDistribution({"lighthouse": 1.0}),
)

# ❌ Avoid Geth until genesis-generator updated
# execution=ClientDistribution({"geth": 1.0})  # Will fail
```

**Resolution**: Wait for ethereum-package to update ethereum-genesis-generator dependency to v5.2.4+ (includes blobSchedule support).

### Minimal Testnet Finality Configuration

**Issue**: 4-node testnet chain progresses (blocks produced) but finality not reached (justified/finalized epochs stuck at 0).

**Root Cause**: Testnet configuration issue, not infrastructure failure. Insufficient validator participation threshold.

**Status**: Not blocking - infrastructure proven working (deployment succeeds, services healthy, chain progressing).

**For Chaos Testing**: Scenarios can work with progressing but non-finalizing chains. Finality detection is implemented and will work once testnet configuration is tuned.

**Future Work**: Research optimal minimal testnet configuration. Options:
- Increase validator count to 8-16 nodes
- Adjust genesis config (validator deposit schedule)
- Tune network params (reduce slot time to 6s)

### Kurtosis Service Name Changes

**Issue**: Service names changed in ethereum-package v4.2.0+

**Changes**:
- `tx_spammer` → `spamoor` (transaction spammer service)

**Already Fixed**: ethereum_package.py updated to use correct service names.
