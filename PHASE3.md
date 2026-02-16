# Phase 3: Analysis and Production

**Duration estimate:** 4-6 weeks
**Team size:** 3-4 engineers
**Risk level:** Medium -- most core technology is built; this phase is about polish, scale, and compliance-grade output

---

## Overview

Phase 3 transforms EthereumChaos from a working prototype into a production-grade chaos engineering platform that produces compliance-ready outputs for financial institutions and regulators. The focus shifts from "does it work?" to "is it reliable, scalable, and does it produce trustworthy documentation?"

This phase covers four areas: the analysis and output module (statistical reports, playbooks, compliance documents), the full scenario library (all six pre-programmed scenarios plus the framework for custom scenarios), production hardening (500-node scale, performance optimization, operational tooling), and end-to-end integration testing.

---

## Goals

1. Build the complete analysis and output module: statistical analysis, playbook generation, compliance reports, and visual dashboards.
2. Implement all six pre-programmed scenarios from the spec and validate them end-to-end.
3. Harden the system for 500-node scale with acceptable performance.
4. Produce compliance-ready documentation (resilience certification, disaster recovery playbooks, governance records).
5. Build the visual dashboard with experiment replay capabilities.
6. Complete end-to-end integration testing across all components.

---

## Parallel Tracks

### Track I: Analysis and Output Module

| Task | Description | Effort |
|------|-------------|--------|
| I1. Statistical analysis engine | Implement the post-experiment statistical analysis pipeline: Mann-Whitney U tests comparing chaos vs. baseline metrics, 95% confidence intervals on recovery times, effect size calculations, distribution comparisons. Use scipy/statsmodels. | L |
| I2. Metric comparison framework | Build the framework for structured metric comparison: align time-series data from chaos and baseline runs, compute deltas at each phase (pre-fault, during-fault, recovery), generate summary tables. | M |
| I3. Playbook generation engine | Implement the Observer Agent's playbook generation capability: given experiment results and root cause analysis, generate structured incident response playbooks. Format: "If [condition] -> Check [diagnostic step] -> Apply [remediation]." Output as Markdown and PDF. | L |
| I4. Compliance report generator | Build the compliance report generator for Basel/FI requirements: resilience certification documents, stress test summaries, governance records. Output as PDF and JSON. Include digital signatures for tamper evidence. | L |
| I5. Historical comparison engine | Implement comparison against historical incidents: given experiment results, compare key metrics (finality delay, recovery time, participation drop) against historical data (May 2023 finality loss, etc.). Generate a structured comparison table. | M |
| I6. Report template system | Build a template system for reports: configurable headers, branding, sections. Support multiple output formats (PDF, HTML, JSON, Markdown). Allow financial institutions to customize report templates. | M |

**Key technical decisions:**
- **scipy + statsmodels for statistics.** Well-established, auditable libraries. Regulators need to trust the statistical methods; using standard tools helps.
- **PDF generation via WeasyPrint or ReportLab.** WeasyPrint for HTML-to-PDF conversion (better for complex layouts); ReportLab as fallback for simpler documents.
- **Digital signatures on compliance reports.** Use GPG signatures on PDF outputs. The signature key is managed by the organization, not by EthereumChaos.
- **JSON output alongside PDF.** Machine-readable reports enable automated compliance pipelines.

### Track J: Scenario Library

| Task | Description | Effort |
|------|-------------|--------|
| J1. may_2023_finality_loss.yaml | Implement the Prysm bug recreation scenario: inject P2P latency on Prysm nodes, trigger attestation pool overflow, observe finality degradation. Validate against historical data (25-minute finality delay). | L |
| J2. mass_validator_exit.yaml | Implement the Shapella stress scenario: trigger mass validator exits (5-30% of validator set), observe the network's ability to maintain finality with a shrinking validator set. Test the exit queue mechanics. | L |
| J3. mev_builder_censorship.yaml | Implement coordinated MEV censorship: adversarial builders censor specific transaction types, measure censorship resistance and inclusion delays. Test PBS (Proposer-Builder Separation) resilience. | L |
| J4. ddos_relay_attack.yaml | Implement P2P flood attack: overwhelm gossipsub with invalid messages, measure impact on legitimate message propagation and consensus. Test rate limiting effectiveness. | M |
| J5. economic_panic.yaml | Implement the economic panic scenario: simulate 50% ETH price crash by triggering coordinated validator exits and increased transaction volume (panic selling). Measure network stability under economic stress. | L |
| J6. network_partition.yaml | Implement the Byzantine generals scenario: split the network into 2-3 partitions of varying sizes, observe consensus behavior in each partition, test recovery when partitions heal. | L |
| J7. Custom scenario framework | Build the framework for users to define custom scenarios: scenario builder CLI/API, parameter validation, dry-run mode (validates the scenario without executing), scenario composition (chain multiple scenarios). | M |
| J8. Scenario regression test suite | Build an automated test suite that runs all six scenarios nightly in CI. Each scenario has expected metric ranges; the test suite flags regressions (e.g., "finality delay increased by 20% compared to last run"). | L |

**Key technical decisions:**
- **Scenarios are versioned.** Each scenario YAML includes a version field. Changes to scenarios create new versions; old versions are preserved for reproducibility.
- **Scenario parameters are overridable.** Each scenario has default parameters, but users can override them at runtime (e.g., "run mass_validator_exit with 20% exits instead of the default 10%").
- **Dry-run mode.** Before executing a scenario, validate the experiment plan against the current cluster state. Catch issues like "this scenario requires 200 Prysm nodes but only 50 are deployed."

### Track K: Production Hardening

| Task | Description | Effort |
|------|-------------|--------|
| K1. 500-node scale testing | Scale the testnet to 500 nodes. Profile and optimize: Kurtosis enclave startup time, Prometheus scrape performance, Orchestrator planning latency, Node Agent command dispatch throughput. | XL |
| K2. Performance benchmarking suite | Build automated performance benchmarks: testnet boot time, time-to-finality, Prometheus query latency at various node counts, experiment execution overhead. Run on every release. | L |
| K3. Resource optimization | Optimize resource usage: reduce per-node memory footprint, tune Prometheus retention and scrape intervals for large clusters, optimize audit log write batching. Target: 500 nodes on a 32-node K8s cluster. | L |
| K4. Operational tooling | Build operational tools: cluster health dashboard (separate from experiment dashboards), deployment status page, experiment queue and scheduler, multi-tenant experiment isolation. | L |
| K5. Error handling and recovery | Harden error handling across all components: retry logic with exponential backoff, graceful degradation (Observer continues if Orchestrator crashes), partial experiment recovery (resume from last checkpoint). | L |
| K6. Configuration management | Consolidate all configuration into a single, well-documented config system: environment-specific configs (dev/staging/prod), secrets management (vault integration), config validation at startup. | M |
| K7. Documentation and runbooks | Write operational documentation: deployment guide, troubleshooting runbook, architecture diagrams, API reference, scenario authoring guide. | L |

**Key technical decisions:**
- **500-node target is a hard requirement.** The spec says 50-500 nodes. Phase 1 validates 50-200; Phase 3 must reach 500. If 500 nodes on a single K8s cluster is infeasible, document the multi-cluster approach.
- **Experiment scheduler.** In production, multiple experiments may be queued. Build a simple FIFO scheduler with priority support. Only one experiment runs at a time (to avoid interference).
- **Vault for secrets.** Validator keys, API tokens, and signing keys are managed via HashiCorp Vault (or equivalent). No secrets in config files or environment variables in production.

### Track L: Visual Dashboard and Replay

| Task | Description | Effort |
|------|-------------|--------|
| L1. Experiment timeline view | Build the Grafana panel (or custom UI) showing the experiment timeline: fault injection events as markers, SLO threshold lines, phase labels (baseline, chaos, recovery). | M |
| L2. Consensus visualization | Build a visualization of consensus behavior during experiments: validator attestation heatmap (rows = validators, columns = slots, color = attested/missed/delayed), fork choice tree during equivocation attacks. | L |
| L3. Experiment replay | Implement experiment replay: given an experiment ID, replay the Grafana dashboards with recorded metric data, synchronized with the experiment timeline. Allow scrubbing forward/backward. | L |
| L4. Screen recording integration | Integrate automated screen recording of Grafana dashboards during experiments for the "stress test video" compliance requirement. Use headless browser + screen capture. | M |
| L5. Comparison view | Build a side-by-side comparison view: overlay metrics from two experiments (e.g., baseline vs. chaos, or two runs of the same scenario with different parameters). | M |

**Key technical decisions:**
- **Grafana-first approach.** Build as much as possible using Grafana panels and plugins rather than a custom UI. This leverages Grafana's time-series visualization capabilities and reduces maintenance.
- **Replay via Prometheus recording rules.** Record all experiment metrics to a separate Prometheus instance (or labeled time series) at experiment start. Replay queries against this recorded data.
- **Headless browser for recording.** Use Playwright or Puppeteer to capture Grafana dashboards during experiments. Store recordings as MP4 in S3.

---

## Exit Criteria

Phase 3 is complete when ALL of the following are satisfied:

1. **All six scenarios pass:** Each of the six pre-programmed scenarios runs end-to-end, produces valid statistical analysis, generates a playbook, and creates a compliance report.
2. **Statistical analysis is validated:** Mann-Whitney U test results are validated against manual calculations for at least 2 scenarios. Confidence intervals are correctly computed.
3. **Compliance reports pass review:** Generated compliance reports (resilience certification, DR playbook, governance record) are reviewed by a domain expert and confirmed to meet the documented requirements.
4. **500-node scale achieved:** A 500-node testnet boots, reaches finality, and runs at least one scenario without infrastructure failures. Performance benchmarks are documented.
5. **Experiment replay works:** An experiment can be replayed from recorded data, with the timeline view correctly showing all fault injection events and metric responses.
6. **Regression suite is green:** All six scenarios pass in the nightly CI regression suite for 5 consecutive runs.
7. **Operational documentation is complete:** Deployment guide, troubleshooting runbook, and scenario authoring guide are written and reviewed.
8. **Custom scenario validated:** At least one custom scenario (not in the pre-programmed six) is authored using the custom scenario framework and executes successfully.

---

## Dependencies

### Dependencies on Phase 1

| Phase 1 Deliverable | Required By | Detail |
|---------------------|-------------|--------|
| Full monitoring stack (Track B) | Track I, Track L | Analysis and dashboards read from Prometheus/Grafana. |
| PostgreSQL storage (Track D4) | Track I | Statistical analysis reads experiment data from PostgreSQL. |
| S3 storage (Track D4) | Track I4, Track L4 | Compliance reports and screen recordings stored in S3. |
| Scenario YAML schema (Track D1) | Track J | All scenarios conform to the Phase 1 schema. |

### Dependencies on Phase 2

| Phase 2 Deliverable | Required By | Detail |
|---------------------|-------------|--------|
| Orchestrator Agent (Track E) | Track I, Track J | Analysis runs post-experiment; scenarios are executed by the Orchestrator. |
| Observer Agent (Track G) | Track I3 | Playbook generation is an Observer capability. |
| Node Agents (Track F) | Track J | Scenarios require Node Agent adversarial behaviors. |
| Chaos Injection Module (Track H) | Track J | Scenarios inject faults via the chaos module. |
| All Phase 2 components | Track K | Production hardening requires all components to exist. |

### Internal Phase 3 Dependencies

| Dependency | Detail |
|------------|--------|
| Track I (Analysis) is mostly independent | Can begin as soon as Phase 2 produces experiment data. I3 and I4 can start with sample data. |
| Track J (Scenarios) depends on Phase 2 completion | Scenarios need the full agent system and chaos injection module. |
| Track K (Hardening) depends on Phase 2 completion | Cannot harden what does not exist yet. |
| Track L (Dashboard/Replay) depends on Track B (Phase 1) and Track I | Dashboards visualize analysis results. |

**Recommended sequencing:**
1. Start Track I (Analysis) immediately at Phase 3 start, using experiment data from Phase 2 testing.
2. Start Track L (Dashboard/Replay) in parallel with Track I.
3. Start Track J (Scenarios) once Phase 2 is feature-complete (all agents and chaos module working).
4. Start Track K (Hardening) in parallel with Track J, focusing on scale testing first.

---

## Estimated Complexity and Effort

| Track | Effort | Parallelizable | Notes |
|-------|--------|----------------|-------|
| Track I: Analysis & Output | ~3 weeks | Yes (independent) | I4 (compliance reports) requires domain expertise in Basel/FI requirements. |
| Track J: Scenario Library | ~3 weeks | Yes (scenarios are independent of each other) | Each scenario is ~2-3 days. J1 and J6 are the most complex. |
| Track K: Production Hardening | ~3 weeks | Partially (K1 blocks K2/K3) | K1 (500-node scale) is the highest-effort task and may surface surprises. |
| Track L: Dashboard & Replay | ~2 weeks | Yes (independent) | L3 (replay) is the most technically interesting; L4 (recording) is the most brittle. |

**Critical path:** Track J (Scenario Library) is on the critical path because it validates the entire system end-to-end. Track K (500-node scale testing) is the most likely to surface blocking issues.

With 3-4 engineers, expect 4-6 weeks total calendar time. Tracks I and L can start during the last weeks of Phase 2 if Phase 2 is on schedule.

---

## Risk Areas

### High Risk

**R14: 500-node scale feasibility (K1)**
Running 500 Ethereum nodes on a single Kubernetes cluster requires significant resources (CPU, memory, network). Kurtosis and the ethereum-package may not have been tested at this scale. **Mitigation:** Profile resource usage at 100, 200, and 300 nodes first. Define minimum hardware requirements. If a single cluster cannot support 500 nodes, design a multi-cluster deployment and document the additional complexity. Set a fallback target of 300 nodes if 500 proves infeasible within the time budget.

**R15: Compliance report accuracy (I4)**
Generated compliance reports must be accurate and trustworthy. Incorrect statistical claims or misleading summaries could have regulatory consequences for users. **Mitigation:** All statistical methods are documented and auditable. Reports include raw data references so results can be independently verified. Have a domain expert review the report template and at least 3 generated reports before release.

### Medium Risk

**R16: Scenario fidelity to historical events (J1-J6)**
The pre-programmed scenarios aim to recreate historical incidents, but the testnet environment differs from mainnet. Metrics may not match historical data closely. **Mitigation:** Define "fidelity ranges" rather than exact targets. Document known differences between the testnet and mainnet conditions. The goal is directionally correct behavior, not exact reproduction.

**R17: Grafana replay performance (L3)**
Replaying experiments with 500 nodes worth of metrics may be slow in Grafana. **Mitigation:** Use downsampled data for replay (1-minute resolution instead of raw). Provide a "high-fidelity" mode for smaller experiments. Pre-compute summary metrics for the replay timeline.

**R18: Screen recording reliability (L4)**
Headless browser screen recording is inherently fragile: browser rendering differences, timing issues, dashboard load time. **Mitigation:** Add retry logic and quality checks (verify recording is not blank, verify duration matches experiment). Accept that this is a "best effort" feature and document manual recording as a fallback.

### Low Risk

**R19: Report template maintenance**
Financial institutions may require frequent report template updates as regulations evolve. **Mitigation:** The template system (I6) is designed for easy customization. Provide clear documentation for template authors.

**R20: Scenario regression flakiness (J8)**
Nightly scenario runs may be flaky due to non-determinism in consensus timing. **Mitigation:** Use wide metric ranges for pass/fail thresholds in the regression suite. Require 3 consecutive failures before flagging a regression (as opposed to a single failure).
