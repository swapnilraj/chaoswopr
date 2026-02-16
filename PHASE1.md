# Phase 1: Foundation

**Duration estimate:** 4-6 weeks
**Team size:** 2-3 engineers
**Risk level:** Medium -- mostly integration work with established tools, but Kurtosis configuration at scale introduces unknowns

---

## Overview

Phase 1 establishes the bedrock infrastructure that every subsequent phase depends on. The goal is a reproducible, instrumented Ethereum testnet that can be spun up and torn down reliably, with monitoring that captures the 50+ metrics the spec requires, and a safety system that prevents runaway experiments from the moment chaos injection begins in Phase 2.

Nothing in Phase 1 involves AI agents or chaos injection. This phase succeeds when an engineer can run a single command to launch a multi-client Ethereum testnet, observe its health on a Grafana dashboard, and tear it down cleanly.

---

## Goals

1. Deploy a private Ethereum testnet (50-500 nodes) via Kurtosis and ethpandaops/ethereum-package with multi-client support.
2. Stand up a Prometheus/Grafana monitoring stack collecting all required metrics.
3. Build the safety and control system scaffolding (circuit breakers, blast radius limits, snapshot/rollback).
4. Define the scenario YAML schema and validate it with at least one hand-authored scenario.
5. Establish the PostgreSQL and S3 storage layer for metrics time-series and audit logs.
6. Create the CI/CD pipeline for reproducible testnet deployments.

---

## Parallel Tracks

### Track A: Testnet Infrastructure (Kurtosis + ethpandaops)

| Task | Description | Effort |
|------|-------------|--------|
| A1. Kurtosis environment setup | Install Kurtosis CLI, configure Docker/K8s backends, validate basic enclave lifecycle (create, inspect, destroy). | S |
| A2. ethpandaops/ethereum-package integration | Write the initial Kurtosis package configuration: 50-node testnet with Nethermind (40%), Geth (30%), Prysm/Lighthouse split for consensus. Validate all clients start and reach finality. | L |
| A3. Client diversity configuration | Parameterize client ratios so they can be changed per-experiment. Test configurations from 50 to 200 nodes (500-node scale testing deferred to Phase 3 hardening). | M |
| A4. Mainnet state fork support | Configure the ethereum-package to fork mainnet state at a specific block number. Validate that forked state loads correctly and the network progresses from it. | L |
| A5. MEV-boost infrastructure | Enable MEV-boost relays and builders in the testnet configuration. Validate that MEV auctions function (block proposals route through the relay). | M |
| A6. Transaction spammer setup | Configure the built-in transaction spammer to generate realistic load. Parameterize TPS targets (100-10,000 TPS). | S |
| A7. Reproducible deployment script | Wrap the full deployment in a single CLI command / Makefile target. Include seed-based determinism where possible. | M |

**Key technical decisions:**
- Use Docker backend for local development, Kubernetes for CI and scale testing. The Kurtosis abstraction means the package config is the same for both.
- Pin ethpandaops/ethereum-package to a specific release tag to avoid upstream breakage.
- Client diversity ratios are specified in a separate YAML config file that the Kurtosis package reads, keeping experiment parameters decoupled from infrastructure code.

### Track B: Monitoring Stack

| Task | Description | Effort |
|------|-------------|--------|
| B1. Prometheus deployment | Deploy Prometheus within the Kurtosis enclave (or sidecar). Configure scrape targets for all EL and CL nodes automatically via service discovery. | M |
| B2. Core metrics catalog | Define and validate collection of the 50+ metrics: finality time, attestation participation rate, mempool depth, peer counts, CPU/memory per node, disk I/O, network bandwidth. Document each metric's source (Beacon API, node_exporter, client-specific endpoints). | L |
| B3. Grafana dashboard -- cluster health | Build the "Cluster Health" dashboard: node status grid, finality timeline, participation rate gauge, resource utilization heatmap. | M |
| B4. Grafana dashboard -- experiment view | Build the "Experiment" dashboard: timeline with fault injection markers, before/during/after comparison panels, SLO threshold lines. This is a skeleton in Phase 1; Phase 2 populates the fault markers. | M |
| B5. Alerting rules for circuit breakers | Define Prometheus alerting rules that will feed the safety system: finality_delay > 10 min, slashing_count > 5%, participation_rate < 66%. In Phase 1 these fire alerts; in Phase 2 they trigger automated circuit breakers. | S |
| B6. Metrics export to PostgreSQL | Set up Prometheus remote-write to PostgreSQL (via the pg_prometheus adapter or Thanos/Cortex). Validate that historical query works for post-experiment analysis. | M |

**Key technical decisions:**
- Prometheus runs inside the Kurtosis enclave so it can use Kurtosis service discovery. Grafana runs outside (host-accessible) with Prometheus as a datasource.
- Use the standard Beacon API `/eth/v1/beacon/states/head/validators` and `/eth/v1/node/syncing` endpoints rather than client-specific metrics where possible, to keep the monitoring stack client-agnostic.
- PostgreSQL for long-term storage rather than Thanos/Cortex to keep operational complexity low in early phases.

### Track C: Safety and Control System

| Task | Description | Effort |
|------|-------------|--------|
| C1. Blast radius configuration schema | Define the configuration format for blast radius limits: max percentage of nodes affected, phased rollout percentages (5% -> 10% -> 20%), per-client-type limits. | S |
| C2. Circuit breaker framework | Implement the circuit breaker service: polls Prometheus alert endpoints, maintains state (armed/tripped/reset), exposes a gRPC/REST API for Phase 2 agents to query. | L |
| C3. Snapshot/rollback mechanism | Implement Kubernetes VolumeSnapshot integration: snapshot all PVCs every 30 seconds during an experiment window, restore on demand. For Docker backend, implement equivalent via Docker volume snapshots or rsync-based checkpoints. | L |
| C4. Testnet isolation validation | Write integration tests proving the testnet cannot make external network calls (no mainnet RPC, no public DNS). Enforce via Kurtosis network policies or iptables rules. | M |
| C5. Audit log infrastructure | Define the audit log schema (timestamp, agent_id, action_type, target, parameters, outcome). Set up S3 bucket with append-only policy. Write the logging client library that all components will use. | M |
| C6. Kill switch CLI | Build a manual kill switch command that immediately halts all fault injection, restores snapshots, and generates a dump of the current state. This is the human override for when automation fails. | M |

**Key technical decisions:**
- Circuit breakers are a standalone service (not embedded in agents) so they function even if the agent system crashes.
- Audit logs use append-only S3 with object lock to prevent tampering, aligning with the ERC-8004-style verifiability requirement.
- The kill switch is a CLI tool (not a web UI) to minimize attack surface and maximize reliability.

### Track D: Scenario Schema and Storage

| Task | Description | Effort |
|------|-------------|--------|
| D1. Scenario YAML schema definition | Define the YAML schema for scenarios: hypothesis, fault_sequence (timeline of actions), slo_thresholds, success_criteria, blast_radius_config. Use JSON Schema for validation. | M |
| D2. Schema validation tooling | Build a CLI validator that checks scenario YAML against the schema, including semantic validation (e.g., blast_radius percentages sum correctly, referenced fault types exist). | S |
| D3. First scenario: baseline observation | Write a "no-fault baseline" scenario that runs the full pre-flight, observation, and analysis workflow with zero fault injection. This validates the scenario execution pipeline end-to-end. | M |
| D4. Storage layer setup | Provision PostgreSQL database with schemas for: experiment_runs, metric_snapshots, scenario_definitions. Provision S3 bucket for audit_logs and experiment_artifacts. | M |

**Key technical decisions:**
- YAML over TOML or JSON for scenario definitions because it supports comments (critical for documenting hypothesis rationale) and is the standard in the Kubernetes/Kurtosis ecosystem.
- JSON Schema for validation so that IDEs can provide autocomplete and inline validation.
- The baseline scenario doubles as a smoke test for every deployment.

---

## Exit Criteria

Phase 1 is complete when ALL of the following are satisfied:

1. **Testnet boots reliably:** Running `make testnet-up` (or equivalent) launches a 50+ node multi-client Ethereum testnet that reaches finality within 3 epochs, succeeding 95%+ of the time.
2. **Metrics flowing:** All 50+ defined metrics are visible in Grafana dashboards with less than 30 seconds of lag.
3. **Safety system armed:** Circuit breakers detect simulated alert conditions (manually triggered Prometheus alerts) and transition to the tripped state. Kill switch tears down the experiment cleanly.
4. **Snapshots work:** A snapshot can be taken and a rollback restores the testnet to the snapshotted state with all validators resuming duties.
5. **Baseline scenario passes:** The no-fault baseline scenario runs end-to-end: pre-flight health check, 10-minute observation window, metrics recorded to PostgreSQL, audit log written to S3.
6. **Isolation verified:** Integration tests confirm no external network access from the testnet enclave.
7. **CI pipeline green:** The entire above sequence runs in CI (GitHub Actions or equivalent) on every PR to the infrastructure code.

---

## Dependencies

| Dependency | Type | Detail |
|------------|------|--------|
| ethpandaops/ethereum-package | External | Upstream must support the client versions and configuration options we need. Pin to a specific release. |
| Kurtosis | External | Must support both Docker and K8s backends at the versions we target. |
| Kubernetes cluster | Infrastructure | Needed for scale testing (200+ nodes) and for VolumeSnapshot support. A managed K8s cluster (EKS/GKE) is recommended. |
| Docker | Infrastructure | Local development backend. Docker Desktop or colima on macOS. |
| PostgreSQL | Infrastructure | Managed instance (RDS/CloudSQL) for CI; local Docker container for development. |
| S3-compatible storage | Infrastructure | AWS S3 or MinIO for local development. |

**Phase 1 has no dependencies on Phase 2 or Phase 3.** It is the foundational layer that everything else builds upon.

---

## Estimated Complexity and Effort

| Track | Effort | Parallelizable | Notes |
|-------|--------|----------------|-------|
| Track A: Testnet Infrastructure | ~3 weeks | Yes (independent of B, C, D) | A2 and A4 are the largest tasks; mainnet fork is the biggest unknown. |
| Track B: Monitoring Stack | ~2 weeks | Yes (independent of C, D; needs A for scrape targets) | B2 (metrics catalog) is the most labor-intensive task. |
| Track C: Safety System | ~3 weeks | Yes (independent of A, B, D) | C2 and C3 are the largest; snapshot/rollback on Docker is tricky. |
| Track D: Scenario Schema | ~1 week | Yes (fully independent) | Smallest track; can start and finish first. |

**Critical path:** Track A (testnet infrastructure) must reach A2 completion before Track B can validate scrape targets. Track C and D are fully independent.

With 2-3 engineers, expect 4-6 weeks total calendar time running tracks in parallel.

---

## Risk Areas

### High Risk

**R1: ethpandaops/ethereum-package configuration complexity**
The ethereum-package is powerful but has a large configuration surface. Getting multi-client testnets to reliably reach finality, especially with mainnet fork state, may require significant iteration. **Mitigation:** Start with the simplest possible configuration (single client, no fork) and incrementally add complexity. Engage with the ethpandaops community early.

**R2: Snapshot/rollback reliability**
Kubernetes VolumeSnapshots are not instantaneous and behavior varies across storage providers. Restoring 50+ node states consistently is non-trivial. **Mitigation:** Test with the specific K8s storage class early. Accept that Docker-backend snapshots may use a different (slower) mechanism and document the tradeoff.

### Medium Risk

**R3: Metrics cardinality explosion**
50+ metrics across 50-500 nodes can produce very high cardinality in Prometheus. **Mitigation:** Use recording rules aggressively. Set retention to 24 hours in Prometheus (long-term in PostgreSQL). Monitor Prometheus memory usage.

**R4: Kurtosis enclave networking isolation**
Ensuring zero external access while allowing internal service discovery requires careful network policy configuration. **Mitigation:** Write explicit integration tests (Track C4) and run them in CI.

### Low Risk

**R5: Client version incompatibility**
Different Ethereum client versions may have protocol incompatibilities. **Mitigation:** Pin all client versions in the Kurtosis config and update them as a deliberate, tested change.

**R6: Storage costs for audit logs**
S3 with object lock can become expensive at high write rates. **Mitigation:** Batch audit log writes. Use lifecycle policies to transition old logs to cheaper storage tiers.
