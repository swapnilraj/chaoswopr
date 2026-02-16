# Phase 2: Intelligence

**Duration estimate:** 6-8 weeks
**Team size:** 3-4 engineers
**Risk level:** High -- this phase introduces AI agents, adversarial behaviors, and real-time coordination, all of which have significant complexity

---

## Overview

Phase 2 builds the brain of EthereumChaos: the multi-agent system that generates hypotheses, executes chaos experiments, and observes their effects. This is where the project transitions from "instrumented testnet" to "intelligent chaos engineering platform."

Three agent types are implemented: the Orchestrator Agent (master controller), Node Agents (per-validator behavior controllers), and the Observer Agent (real-time analyst). These agents communicate through well-defined APIs and are coordinated via the safety system built in Phase 1.

Phase 2 also integrates the chaos injection module (tc/netem, chaos-mesh, custom protocol-level faults) and wires it into the agent control loop.

---

## Goals

1. Implement the Orchestrator Agent with hypothesis generation, experiment planning, and fault orchestration capabilities.
2. Implement Node Agents that can control validator behavior (honest and adversarial modes).
3. Implement the Observer Agent with real-time anomaly detection and SLO monitoring.
4. Build the chaos injection module at all three levels: network, node, and protocol.
5. Wire the circuit breaker system (Phase 1) into the agent control loop for automated safety enforcement.
6. Execute the first complete chaos experiment end-to-end (hypothesis through analysis).

---

## Parallel Tracks

### Track E: Orchestrator Agent

| Task | Description | Effort |
|------|-------------|--------|
| E1. Agent framework selection and setup | Set up LangGraph as the orchestration framework. Define the agent state graph: IDLE -> PLANNING -> EXECUTING -> MONITORING -> ANALYZING -> REPORTING. Build the state transition logic. | L |
| E2. Prometheus query tool | Build the tool that allows the Orchestrator to query Prometheus: parameterized PromQL queries, result parsing, statistical summary generation. The agent uses this for pre-flight health checks and real-time monitoring. | M |
| E3. Hypothesis generation engine | Implement the LLM-driven hypothesis generator. Input: scenario YAML + current cluster state + history of past experiments. Output: structured hypothesis (prediction, blast radius, fault timeline, expected metrics). | XL |
| E4. Experiment plan compiler | Build the component that transforms a hypothesis into an executable experiment plan: ordered list of fault injection actions with timestamps, monitoring checkpoints, escalation/de-escalation triggers, rollback conditions. | L |
| E5. Fault injection dispatcher | Implement the dispatcher that translates experiment plan actions into concrete fault injection API calls (tc/netem, chaos-mesh, Node Agent commands). Handles timing, retries, and rollback on failure. | L |
| E6. Circuit breaker integration | Wire the Orchestrator into the circuit breaker service (Phase 1 C2): poll circuit breaker state before each action, halt experiment immediately on trip, trigger rollback sequence. | M |
| E7. Experiment state persistence | Persist experiment state (plan, current step, metrics snapshots, decisions) to PostgreSQL so that experiments can be resumed after Orchestrator restart and audited after completion. | M |
| E8. Adaptive hypothesis learning | Implement the feedback loop: after each experiment, store results and update the hypothesis generation prompt with historical context. "Last run showed X at 30%; try 35% to find the boundary." | L |

**Key technical decisions:**
- **LangGraph over CrewAI for orchestration.** LangGraph provides explicit state machine semantics which are critical for a safety-sensitive system where we need deterministic state transitions. CrewAI is better suited for the Node Agent coordination layer (Track F).
- **Simple handrolled agent system.** Per the spec, the Orchestrator uses a simple handrolled agent pattern rather than a full framework. LangGraph provides the state graph; the LLM calls are direct API calls with structured output parsing.
- **Structured output for hypotheses.** The LLM generates hypotheses as JSON conforming to a strict schema, not free-form text. This ensures the experiment plan compiler can process them deterministically.
- **vLLM for local inference.** To avoid rate limits and latency during real-time monitoring, run a local vLLM instance for the Orchestrator's LLM calls. Fall back to API-based models for development.

### Track F: Node Agents

| Task | Description | Effort |
|------|-------------|--------|
| F1. Node Agent architecture | Design the per-validator agent system: each agent wraps a validator client instance, intercepts Beacon API calls, and can modify validator behavior. Define the agent interface: honest_mode(), adversarial_mode(behavior_config), status(). | L |
| F2. Honest mode implementation | Implement the baseline honest behavior (70% of nodes): agent passes through all validator duties unmodified. Add instrumentation to log all actions to the audit system. | M |
| F3. Adversarial behavior library | Implement the adversarial behaviors (30% of nodes): attestation withholding, attestation delay, block equivocation, transaction censoring, coordinated exit. Each behavior is parameterized (e.g., delay_ms, withhold_probability). | XL |
| F4. P2P message manipulation | Implement the P2P layer interception: intercept gossipsub messages, delay/drop/reorder them according to the active behavior configuration. This requires hooking into the libp2p layer of the consensus client. | XL |
| F5. Orchestrator command interface | Build the API through which the Orchestrator sends commands to Node Agents: switch_mode(agent_id, mode, config), get_status(agent_id), batch commands for coordinated attacks. | M |
| F6. Coordination protocol for adversarial nodes | Implement the coordination layer for the 30% adversarial nodes: synchronized attestation withholding, coordinated block proposals for equivocation, MEV auction manipulation. Uses CrewAI for multi-agent coordination. | L |
| F7. Validator key management | Implement secure validator key handling: generate keys at testnet deploy, distribute to Node Agents, ensure no key is used by multiple agents (prevents accidental slashing). | M |

**Key technical decisions:**
- **Sidecar pattern for Node Agents.** Each Node Agent runs as a sidecar container alongside the validator client, intercepting Beacon API traffic via a local proxy. This avoids modifying validator client source code.
- **CrewAI for Node Agent coordination.** The 30% adversarial nodes need to coordinate behaviors (e.g., simultaneously withhold attestations). CrewAI provides the multi-agent communication primitives for this.
- **P2P manipulation via libp2p proxy.** Rather than modifying consensus client code, run a libp2p proxy that the consensus client connects through. The proxy can delay, drop, or reorder messages. This is the highest-risk task in this track.

### Track G: Observer Agent

| Task | Description | Effort |
|------|-------------|--------|
| G1. Observer Agent framework | Set up the Observer Agent: specialized LLM instance with access to Grafana API, Prometheus queries, and log aggregation. Define the observation loop: poll metrics -> detect anomalies -> classify severity -> report. | L |
| G2. RAG pipeline over Ethereum documentation | Build the RAG (Retrieval-Augmented Generation) pipeline: index Ethereum consensus spec, client documentation, known CVEs, historical incident reports. Use vector store (pgvector in PostgreSQL) for retrieval. | L |
| G3. Anomaly detection module | Implement statistical anomaly detection on streaming metrics: Z-score based detection for metric deviations, changepoint detection for regime shifts (e.g., finality time suddenly doubles), correlation detection (CPU spike coincides with participation drop). | L |
| G4. SLO monitoring and breach detection | Implement real-time SLO monitoring: compare current metrics against scenario-defined thresholds, calculate error budgets, detect breaches, generate structured alerts. | M |
| G5. Root cause analysis engine | Build the root cause analysis capability: when an anomaly is detected, the Observer queries correlated metrics, checks logs, consults the RAG pipeline for known issues, and generates a structured root cause hypothesis. | XL |
| G6. Real-time reporting stream | Implement the live reporting interface: WebSocket stream of Observer findings during an experiment, structured as timestamped events (anomaly_detected, slo_breach, root_cause_hypothesis, recovery_observed). | M |
| G7. Log aggregation integration | Set up centralized log aggregation (Loki or equivalent) for all consensus and execution client logs. Build the Observer's log query tool for root cause analysis. | M |

**Key technical decisions:**
- **Separate LLM instance for Observer.** The Observer needs low-latency inference for real-time analysis. It gets its own vLLM instance (or dedicated API allocation) to avoid contention with the Orchestrator.
- **pgvector for RAG.** Reuse the existing PostgreSQL instance with pgvector extension rather than introducing a separate vector database. Reduces operational complexity.
- **Statistical anomaly detection before LLM analysis.** The anomaly detection module uses traditional statistics (Z-scores, CUSUM) as a fast first pass. The LLM is only invoked for root cause analysis on confirmed anomalies. This keeps the system responsive even at high metric volumes.

### Track H: Chaos Injection Module

| Task | Description | Effort |
|------|-------------|--------|
| H1. Network-level fault injection (tc/netem) | Build the tc/netem wrapper: apply packet drops (0-50%), latency injection (10-5000ms), bandwidth throttling, and network partitions to specific containers/pods. Expose as an API the Orchestrator can call. | L |
| H2. Node-level fault injection (chaos-mesh) | Integrate chaos-mesh for Kubernetes environments: pod kills, CPU stress, memory stress, disk I/O throttling. Target specific client types (e.g., "all Nethermind nodes"). Expose as an API. | L |
| H3. Protocol-level fault injection | Build the custom Ethereum protocol fault injectors: these are the Node Agent adversarial behaviors (Track F3/F4) exposed as injectable faults. The Orchestrator treats them the same as network/node faults in experiment plans. | M |
| H4. Fault injection safety wrapper | Wrap all fault injection APIs with safety checks: verify blast radius limits, check circuit breaker state, enforce phased rollout (5% -> 10% -> 20%), log every action to audit system. | M |
| H5. Network partition simulator | Build the network partition tool: split the validator set into configurable "islands" that cannot communicate with each other. Support clean partition (instant) and degraded partition (high loss/latency between islands). | L |
| H6. Fault removal and cleanup | Implement reliable fault removal: undo all tc/netem rules, remove chaos-mesh experiments, reset Node Agents to honest mode. Must work even if the Orchestrator crashes mid-experiment (cleanup daemon). | M |

**Key technical decisions:**
- **chaos-mesh over LitmusChaos.** chaos-mesh has better Kubernetes-native integration and a more mature API. LitmusChaos has a broader scope but more operational overhead.
- **Cleanup daemon.** A separate daemon process monitors active faults and removes them if the Orchestrator heartbeat stops. This prevents "stuck faults" from corrupting the testnet.
- **Phased rollout enforcement.** The safety wrapper enforces that fault injection follows the configured rollout schedule. Even if the Orchestrator requests 33% immediately, the wrapper ramps up through the configured steps with mandatory observation windows between steps.

---

## Exit Criteria

Phase 2 is complete when ALL of the following are satisfied:

1. **Orchestrator runs a full experiment:** Given a scenario YAML, the Orchestrator generates a hypothesis, compiles an experiment plan, dispatches faults, monitors the experiment, and produces a structured result -- all without human intervention.
2. **Node Agents control validators:** At least 5 adversarial behaviors are implemented and demonstrably affect consensus metrics (e.g., attestation withholding measurably reduces participation rate).
3. **Observer detects anomalies in real-time:** The Observer correctly identifies metric anomalies caused by fault injection within 60 seconds and generates a plausible root cause hypothesis.
4. **Circuit breakers halt experiments:** A test where faults are escalated past the safety threshold triggers the circuit breaker, which halts the experiment and initiates rollback automatically.
5. **Network partitions work:** The partition simulator can split validators into 2+ islands and consensus behavior degrades as expected (finality delay increases proportional to the minority partition size).
6. **Audit trail complete:** Every agent decision and fault injection action is recorded in the audit log with enough detail to reconstruct the experiment from logs alone.
7. **May 2023 finality loss scenario runs:** The pre-programmed Prysm bug recreation scenario executes end-to-end and produces metrics comparable to the historical incident.

---

## Dependencies

### Dependencies on Phase 1

| Phase 1 Deliverable | Required By | Detail |
|---------------------|-------------|--------|
| Testnet infrastructure (Track A) | All of Phase 2 | Agents need a running testnet to operate on. |
| Monitoring stack (Track B) | Tracks E, G | Orchestrator and Observer query Prometheus/Grafana. |
| Circuit breaker service (Track C2) | Track E6, Track H4 | Agents must integrate with the existing circuit breaker. |
| Audit log infrastructure (Track C5) | All tracks | All agents write to the audit log. |
| Scenario YAML schema (Track D1) | Track E3, E4 | Orchestrator reads scenario files. |
| PostgreSQL/S3 storage (Track D4) | Tracks E7, G2 | Experiment state and RAG vectors stored in PostgreSQL. |

### Internal Phase 2 Dependencies

| Dependency | Detail |
|------------|--------|
| Track E (Orchestrator) depends on Track H (Chaos Injection) | The Orchestrator dispatches faults via the chaos injection APIs. E5 requires H1-H3 to exist. |
| Track E (Orchestrator) depends on Track F (Node Agents) | Protocol-level faults are executed by Node Agents. E5 requires F5 (command interface). |
| Track G (Observer) is independent | Can be developed and tested with synthetic metrics before integration. |
| Track H (Chaos Injection) is mostly independent | Can be developed and tested against the Phase 1 testnet without agents. |

**Recommended sequencing:**
1. Start Tracks G and H immediately (independent).
2. Start Track F (Node Agents) immediately (only needs Phase 1 testnet).
3. Start Track E (Orchestrator) early but expect integration work in the final 2 weeks when H and F are ready.

---

## Estimated Complexity and Effort

| Track | Effort | Parallelizable | Notes |
|-------|--------|----------------|-------|
| Track E: Orchestrator Agent | ~4 weeks | Partially (E1-E4 independent; E5-E8 need H and F) | E3 (hypothesis generation) is the hardest task; requires significant prompt engineering and testing. |
| Track F: Node Agents | ~4 weeks | Yes (independent until integration) | F4 (P2P manipulation) is the highest-risk task in the entire project. |
| Track G: Observer Agent | ~3 weeks | Yes (fully independent until integration) | G5 (root cause analysis) is open-ended; timebox it. |
| Track H: Chaos Injection | ~3 weeks | Yes (independent until integration) | Mostly integration work with existing tools (tc/netem, chaos-mesh). |

**Critical path:** Track F (Node Agents), specifically F4 (P2P message manipulation), is on the critical path because it enables protocol-level chaos which is the core differentiator. If F4 is delayed, the entire project's unique value proposition is delayed.

With 3-4 engineers, expect 6-8 weeks total calendar time. The final 2 weeks are integration and end-to-end testing.

---

## Risk Areas

### High Risk

**R7: P2P message manipulation (F4)**
Intercepting and modifying libp2p gossipsub messages without modifying consensus client source code is technically challenging. The libp2p proxy approach may introduce unacceptable latency or may not be able to intercept all message types. **Mitigation:** Prototype this task in week 1 of Phase 2. If the proxy approach fails, fall back to maintaining forks of 1-2 consensus clients with instrumentation hooks. This is more maintenance burden but technically simpler.

**R8: LLM reliability for hypothesis generation (E3)**
The Orchestrator's hypothesis generation depends on LLM output quality. Hallucinated hypotheses could lead to meaningless experiments or unsafe fault configurations. **Mitigation:** Structured output with JSON schema validation. All hypotheses are validated against the blast radius configuration before execution. The safety wrapper (H4) provides a second layer of defense. Include a human-review mode for the first N experiments.

**R9: Agent coordination failures (F6)**
Coordinating 30% adversarial Node Agents to execute synchronized attacks (e.g., simultaneous attestation withholding) is a distributed systems problem. Clock skew, message delays, and partial failures can cause uncoordinated behavior. **Mitigation:** Use the Orchestrator as the coordination point (centralized command) rather than peer-to-peer coordination among Node Agents. Accept that coordination will be "approximately synchronized" within a 1-2 second window.

### Medium Risk

**R10: vLLM resource contention**
Running local LLM instances (vLLM) for the Orchestrator and Observer alongside a 50-500 node Ethereum testnet requires significant compute resources. **Mitigation:** Use smaller models (7B-13B parameter) for real-time tasks. Use API-based larger models for hypothesis generation (not latency-sensitive). Profile resource usage early and define minimum hardware requirements.

**R11: chaos-mesh compatibility**
chaos-mesh may not support all required fault types on all Kubernetes configurations (e.g., some managed K8s providers restrict kernel-level operations needed for tc/netem). **Mitigation:** Test on the target K8s provider in week 1. Maintain a fallback to direct tc/netem commands via kubectl exec for providers that restrict chaos-mesh.

### Low Risk

**R12: Observer false positives**
The anomaly detection module may generate false positives during normal network variance. **Mitigation:** Tune detection thresholds using the Phase 1 baseline scenario data. Require anomalies to persist for >30 seconds before alerting.

**R13: Audit log volume**
With 50-500 Node Agents logging every action, audit log volume could become significant. **Mitigation:** Use structured logging with configurable verbosity levels. Batch writes to S3. Estimate storage costs early.
