# EthereumChaos Implementation Plan

**Project:** AI-Driven Chaos Engineering for Ethereum Operational Resilience
**Total estimated duration:** 14-20 weeks (3 phases)
**Team size:** 3-4 engineers

---

## Executive Summary

EthereumChaos is a platform that uses AI agents to orchestrate chaos engineering experiments against private Ethereum testnets, producing compliance-ready resilience documentation for financial institutions and regulators. The implementation is structured in three phases that progressively build capabilities: infrastructure, intelligence, and production-grade analysis.

---

## Phase Overview

| Phase | Name | Duration | Focus | Risk |
|-------|------|----------|-------|------|
| [Phase 1](./PHASE1.md) | Foundation | 4-6 weeks | Infrastructure, monitoring, safety systems | Medium |
| [Phase 2](./PHASE2.md) | Intelligence | 6-8 weeks | AI agents, chaos injection, experiment execution | High |
| [Phase 3](./PHASE3.md) | Analysis and Production | 4-6 weeks | Reports, scenarios, scale, compliance output | Medium |

---

## Phase 1: Foundation

**Goal:** A reproducible, instrumented Ethereum testnet with monitoring, safety systems, and the scenario schema.

**Parallel tracks:**

| Track | Description | Effort |
|-------|-------------|--------|
| A: Testnet Infrastructure | Kurtosis + ethpandaops/ethereum-package deployment (50-200 nodes, multi-client, mainnet fork) | ~3 weeks |
| B: Monitoring Stack | Prometheus/Grafana with 50+ metrics, dashboards, alerting rules | ~2 weeks |
| C: Safety and Control | Circuit breakers, snapshot/rollback, kill switch, audit logs, testnet isolation | ~3 weeks |
| D: Scenario Schema | YAML schema definition, validation tooling, baseline scenario | ~1 week |

**Key exit criteria:**
- Testnet boots reliably with 50+ multi-client nodes reaching finality
- All metrics visible in Grafana with less than 30s lag
- Circuit breakers detect and respond to alert conditions
- Baseline (no-fault) scenario runs end-to-end

**Full details:** [PHASE1.md](./PHASE1.md)

---

## Phase 2: Intelligence

**Goal:** A multi-agent system that generates hypotheses, executes chaos experiments, and observes their effects autonomously.

**Parallel tracks:**

| Track | Description | Effort |
|-------|-------------|--------|
| E: Orchestrator Agent | Hypothesis generation, experiment planning, fault dispatch, adaptive learning (LangGraph) | ~4 weeks |
| F: Node Agents | Per-validator control, honest/adversarial modes, P2P manipulation, coordinated attacks (CrewAI) | ~4 weeks |
| G: Observer Agent | Real-time anomaly detection, SLO monitoring, root cause analysis, RAG over Ethereum docs | ~3 weeks |
| H: Chaos Injection Module | tc/netem, chaos-mesh, protocol-level faults, network partitions, safety wrappers | ~3 weeks |

**Key exit criteria:**
- Orchestrator runs a full experiment (hypothesis to report) without human intervention
- At least 5 adversarial Node Agent behaviors demonstrably affect consensus
- Observer detects anomalies within 60 seconds and generates root cause hypotheses
- Circuit breakers halt runaway experiments automatically
- May 2023 finality loss scenario runs end-to-end

**Full details:** [PHASE2.md](./PHASE2.md)

---

## Phase 3: Analysis and Production

**Goal:** A production-grade platform producing compliance-ready documentation at 500-node scale.

**Parallel tracks:**

| Track | Description | Effort |
|-------|-------------|--------|
| I: Analysis and Output | Statistical analysis (Mann-Whitney U), playbook generation, compliance reports (PDF/JSON) | ~3 weeks |
| J: Scenario Library | All 6 pre-programmed scenarios, custom scenario framework, regression test suite | ~3 weeks |
| K: Production Hardening | 500-node scale, performance benchmarks, operational tooling, error recovery | ~3 weeks |
| L: Dashboard and Replay | Experiment timeline, consensus visualization, replay, screen recording | ~2 weeks |

**Key exit criteria:**
- All 6 scenarios pass end-to-end with valid statistical analysis and compliance reports
- 500-node testnet boots, finalizes, and runs at least one scenario
- Experiment replay works from recorded data
- Nightly regression suite passes 5 consecutive runs
- Operational documentation complete

**Full details:** [PHASE3.md](./PHASE3.md)

---

## Timeline and Dependencies

```
Week  1  2  3  4  5  6  7  8  9  10  11  12  13  14  15  16  17  18  19  20
      |--------Phase 1--------|
      [Track A: Testnet Infra  ]
      [Track B: Monitoring     ]
      [Track C: Safety System  ]
      [Track D: Scenario Schema]
                               |------------Phase 2------------|
                               [Track E: Orchestrator Agent    ]
                               [Track F: Node Agents           ]
                               [Track G: Observer Agent        ]
                               [Track H: Chaos Injection       ]
                                                               |-------Phase 3-------|
                                                               [Track I: Analysis    ]
                                                               [Track J: Scenarios   ]
                                                               [Track K: Hardening   ]
                                                               [Track L: Dashboards  ]
```

**Phase boundaries are soft.** If Phase 1 tracks finish early, Phase 2 tracks can start ahead of schedule. Tracks G (Observer) and H (Chaos Injection) in Phase 2 are independent enough to begin development during the tail end of Phase 1. Similarly, Track I (Analysis) and Track L (Dashboards) can begin during the final weeks of Phase 2.

### Inter-Phase Dependency Map

```
Phase 1                    Phase 2                     Phase 3
--------                   --------                    --------
Track A (Testnet) -------> Track E (Orchestrator)
                  -------> Track F (Node Agents)
                  -------> Track G (Observer)
                  -------> Track H (Chaos Injection)

Track B (Monitoring) ----> Track E (Orchestrator)
                    ----> Track G (Observer) --------> Track I (Analysis)
                                                  --> Track L (Dashboards)

Track C (Safety) --------> Track E (Orchestrator)
                 --------> Track H (Chaos Injection)

Track D (Schema) --------> Track E (Orchestrator)
                 -------------------------------- --> Track J (Scenarios)

                           Track E (Orchestrator) ---> Track I (Analysis)
                                                  --> Track J (Scenarios)
                           Track F (Node Agents) ----> Track J (Scenarios)
                           Track G (Observer) -------> Track I (Analysis)
                           Track H (Chaos Inj.) -----> Track J (Scenarios)

                           All Phase 2 --------------> Track K (Hardening)
```

---

## Critical Path

The critical path through the project is:

1. **Track A2** (ethpandaops integration) -- everything depends on a working testnet
2. **Track F4** (P2P message manipulation) -- the highest-risk task and core differentiator
3. **Track E3** (hypothesis generation) -- the AI capability that makes the platform intelligent
4. **Track J1-J6** (scenario library) -- end-to-end validation of the entire system
5. **Track K1** (500-node scale) -- production readiness gate

If any of these tasks is significantly delayed, the project timeline extends.

---

## Risk Summary

Risks are numbered continuously across phases for easy reference.

| ID | Risk | Phase | Severity | Mitigation |
|----|------|-------|----------|------------|
| R1 | ethpandaops config complexity | 1 | High | Start simple, iterate. Engage community. |
| R2 | Snapshot/rollback reliability | 1 | High | Test on target storage class early. |
| R3 | Prometheus cardinality explosion | 1 | Medium | Recording rules, short retention. |
| R4 | Network isolation enforcement | 1 | Medium | Integration tests in CI. |
| R5 | Client version incompatibility | 1 | Low | Pin versions. |
| R6 | Audit log storage costs | 1 | Low | Batch writes, lifecycle policies. |
| R7 | P2P message manipulation | 2 | High | Prototype week 1. Fallback to client forks. |
| R8 | LLM hypothesis reliability | 2 | High | Structured output, safety wrappers, human review. |
| R9 | Agent coordination failures | 2 | High | Centralized coordination via Orchestrator. |
| R10 | vLLM resource contention | 2 | Medium | Smaller models for real-time; API for planning. |
| R11 | chaos-mesh K8s compatibility | 2 | Medium | Test on target provider week 1. |
| R12 | Observer false positives | 2 | Low | Tune thresholds with baseline data. |
| R13 | Audit log volume | 2 | Low | Structured logging, batched writes. |
| R14 | 500-node scale feasibility | 3 | High | Profile incrementally. Fallback to 300 nodes. |
| R15 | Compliance report accuracy | 3 | High | Auditable methods, domain expert review. |
| R16 | Scenario fidelity to history | 3 | Medium | Fidelity ranges, not exact targets. |
| R17 | Grafana replay performance | 3 | Medium | Downsampled replay data. |
| R18 | Screen recording reliability | 3 | Medium | Retry logic, manual fallback. |
| R19 | Report template maintenance | 3 | Low | Customizable template system. |
| R20 | Scenario regression flakiness | 3 | Low | Wide thresholds, 3-strike rule. |

---

## Technical Stack Summary

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Testnet deployment | Kurtosis + ethpandaops/ethereum-package | Industry standard for Ethereum testnet orchestration |
| Container orchestration | Docker (dev) / Kubernetes (prod) | Kurtosis abstracts the backend |
| EL clients | Nethermind, Geth | Multi-client diversity per spec |
| CL clients | Prysm, Lighthouse | Multi-client diversity per spec |
| Agent orchestration | LangGraph | Explicit state machine for safety-critical orchestration |
| Node agent coordination | CrewAI | Multi-agent communication for adversarial coordination |
| LLM inference | vLLM (local) + API fallback | Low latency for real-time; cost-effective at scale |
| Monitoring | Prometheus + Grafana | Industry standard; Kurtosis-native integration |
| Chaos injection | tc/netem + chaos-mesh | Network and node-level faults with K8s integration |
| Time-series storage | PostgreSQL (via remote-write) | Simplicity; reuse existing database |
| Vector store (RAG) | pgvector | Reuse PostgreSQL; avoid additional operational burden |
| Audit logs | S3 (append-only, object lock) | Tamper-evident, cost-effective |
| Secrets | HashiCorp Vault | Production-grade secrets management |
| Statistical analysis | scipy + statsmodels | Auditable, well-established libraries |
| PDF generation | WeasyPrint | HTML-to-PDF for complex report layouts |
| Screen recording | Playwright/Puppeteer | Headless browser capture of Grafana dashboards |
| CI/CD | GitHub Actions | Standard; integrates with existing workflow |

---

## Team Structure Recommendation

| Role | Count | Responsibilities |
|------|-------|-----------------|
| Infrastructure Engineer | 1 | Tracks A, B, K (testnet, monitoring, scale) |
| Backend Engineer (Agents) | 1-2 | Tracks E, F, G (Orchestrator, Node Agents, Observer) |
| Backend Engineer (Platform) | 1 | Tracks C, D, H, I (safety, scenarios, chaos, analysis) |
| All engineers | -- | Track J (scenarios -- each engineer owns 2), Track L (dashboards -- shared) |

The agent-focused engineers should have experience with LLM application development (prompt engineering, structured output, RAG). The infrastructure engineer should have deep Kubernetes and Prometheus experience. The platform engineer bridges both worlds.

---

## Decision Log

Key architectural decisions made during planning:

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| LangGraph for Orchestrator | Explicit state machine semantics for safety-critical flow | CrewAI (less deterministic), AutoGen (heavier) |
| Sidecar pattern for Node Agents | Avoids modifying client source code | Client forks (more maintenance), eBPF (too complex) |
| PostgreSQL over Thanos for storage | Operational simplicity in early phases | Thanos (better for scale), ClickHouse (better for analytics) |
| pgvector over dedicated vector DB | Reduces infrastructure components | Pinecone (managed), Milvus (more features) |
| chaos-mesh over LitmusChaos | Better K8s-native API, more mature | LitmusChaos (broader scope), custom (more control) |
| YAML for scenarios | Comments, K8s ecosystem convention | TOML (stricter), JSON (no comments), HCL (niche) |
| Circuit breaker as standalone service | Functions even if agents crash | Embedded in agents (simpler but less resilient) |

---

## How to Use This Plan

1. **Read this document** for the high-level overview, timeline, and risk landscape.
2. **Read the phase document** ([PHASE1.md](./PHASE1.md), [PHASE2.md](./PHASE2.md), [PHASE3.md](./PHASE3.md)) for the phase you are currently working on.
3. **Use the track tables** within each phase document to identify individual tasks and their effort estimates.
4. **Check exit criteria** before declaring a phase complete.
5. **Monitor risks** from the risk summary table above and the detailed risk sections in each phase document.
