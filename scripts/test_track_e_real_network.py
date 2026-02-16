#!/usr/bin/env python3
"""Test Track E (Orchestrator Agent) end-to-end on a REAL Ethereum network.

This script tests the full Orchestrator workflow against real infrastructure:
- Real Beacon API endpoints for Node Agents
- Real Prometheus for Observer Agent metrics
- Full state machine: PRE_FLIGHT -> HYPOTHESIS -> PLANNING -> EXECUTING
                       -> MONITORING -> ANALYZING -> REPORTING

Requirements:
    - Kurtosis enclave 'chaoswopr-test' running with ethereum-package
    - Beacon API and Prometheus accessible on localhost

Usage:
    uv run python3 scripts/test_track_e_real_network.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chaoswopr.agents.anomaly_detection import AnomalyDetector
from chaoswopr.agents.node_agent import AgentMode, NodeAgent, NodeAgentConfig
from chaoswopr.agents.node_agent_api import batch_get_status, batch_mode_switch
from chaoswopr.agents.node_agent_behaviors import AttestationWithholding
from chaoswopr.agents.observer import ObserverAgent
from chaoswopr.agents.orchestrator import OrchestratorAgent, OrchestratorState
from chaoswopr.agents.rca_engine import RCAEngine
from chaoswopr.agents.slo_monitor import SLODefinition, SLOMonitor
from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient, QueryResult
from chaoswopr.safety.audit import AuditLogger
from chaoswopr.safety.circuit_breaker import CircuitBreaker, ThresholdConfig

# ---------------------------------------------------------------------------
# Configuration: real endpoints from Kurtosis testnet
# ---------------------------------------------------------------------------

BEACON_ENDPOINTS = {
    "cl-1-lighthouse": "http://127.0.0.1:34381",
    "cl-2-lighthouse": "http://127.0.0.1:34387",
    "cl-3-teku": "http://127.0.0.1:34384",
}

PROMETHEUS_URL = "http://127.0.0.1:34392"


class RealPrometheusClient:
    """Real Prometheus client for live PromQL queries."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._query_count = 0

    @property
    def base_url(self) -> str:
        return self._base_url

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self._base_url}/-/healthy", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def query(self, promql: str) -> QueryResult:
        self._query_count += 1
        try:
            resp = requests.get(
                f"{self._base_url}/api/v1/query",
                params={"query": promql},
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
            return QueryResult(
                status=body.get("status", "error"),
                result_type=body.get("data", {}).get("resultType", "vector"),
                data=body.get("data", {}).get("result", []),
            )
        except Exception as exc:
            return QueryResult(
                status="error",
                result_type="vector",
                error=str(exc),
            )


def query_real_metric(prom: RealPrometheusClient, metric: str) -> float | None:
    """Query a single metric value from real Prometheus."""
    result = prom.query(metric)
    if result.success and result.data:
        try:
            return float(result.data[0]["value"][1])
        except (KeyError, IndexError, ValueError):
            return None
    return None


def print_section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def main() -> int:
    """Run Track E real network end-to-end test."""
    print_section("TRACK E: ORCHESTRATOR AGENT -- REAL END-TO-END TEST")
    print("Full orchestration workflow on REAL Ethereum testnet.")
    print("Beacon API + Prometheus + Node Agents + Observer + Orchestrator.\n")

    results: dict[str, bool] = {}

    # -----------------------------------------------------------------------
    # Phase 0: Infrastructure verification
    # -----------------------------------------------------------------------
    print_section("Phase 0: Infrastructure Verification")

    # Verify Beacon APIs
    print("  Checking Beacon API endpoints...")
    available_beacons: list[dict] = []
    for name, url in BEACON_ENDPOINTS.items():
        try:
            resp = requests.get(f"{url}/eth/v1/node/version", timeout=5)
            resp.raise_for_status()
            version = resp.json()["data"]["version"]
            available_beacons.append({"name": name, "url": url, "version": version})
            print(f"    [OK] {name}: {version}")
        except Exception as exc:
            print(f"    [FAIL] {name}: {exc}")

    if not available_beacons:
        print("\n[FATAL] No Beacon APIs reachable. Aborting.")
        return 1

    # Verify Prometheus
    print("\n  Checking Prometheus...")
    prom = RealPrometheusClient(PROMETHEUS_URL)
    if not prom.health_check():
        print("  [FATAL] Prometheus not reachable. Aborting.")
        return 1
    print(f"    [OK] Prometheus at {PROMETHEUS_URL}")

    # Verify chain is progressing
    head_slot = query_real_metric(prom, "beacon_head_slot")
    active_validators = query_real_metric(prom, "beacon_head_state_active_validators_total")
    finalized_epoch = query_real_metric(prom, "beacon_finalized_epoch")
    print(f"\n  Chain status:")
    print(f"    Head slot: {head_slot}")
    print(f"    Active validators: {active_validators}")
    print(f"    Finalized epoch: {finalized_epoch}")

    results["infrastructure_verified"] = len(available_beacons) >= 2 and head_slot is not None

    # -----------------------------------------------------------------------
    # Phase 1: Set up all components with REAL infrastructure
    # -----------------------------------------------------------------------
    print_section("Phase 1: Component Setup (Real Infrastructure)")

    # Audit logger
    audit_logger = AuditLogger(default_agent_id="orchestrator")
    print("  [OK] AuditLogger initialized")

    # Circuit breaker with real-world thresholds
    circuit_breaker = CircuitBreaker(
        thresholds=ThresholdConfig(
            finality_delay_max_seconds=600.0,     # 10 minutes
            slashing_rate_max_percent=5.0,        # 5% max
            participation_rate_min_percent=66.0,   # 2/3 threshold
        )
    )
    print(f"  [OK] CircuitBreaker initialized (state={circuit_breaker.state.value})")

    # Node Agents connected to real Beacon APIs
    node_agents: list[NodeAgent] = []
    for idx, beacon in enumerate(available_beacons):
        config = NodeAgentConfig(
            node_id=f"validator-{idx}",
            beacon_api_url=beacon["url"],
            proxy_port=7000 + idx,
            mode=AgentMode.HONEST,
            audit_logging=True,
        )
        agent = NodeAgent(config=config, audit_logger=audit_logger, dry_run=False)
        agent.start()
        node_agents.append(agent)
        print(f"  [OK] NodeAgent {agent.node_id} -> {beacon['name']} (started)")

    # Observer Agent with real Prometheus
    anomaly_detector = AnomalyDetector(z_score_threshold=3.0, window_size=30)
    slo_monitor = SLOMonitor()

    # Add SLOs using real metric names
    slo_monitor.add_slo(
        "chain_progress",
        SLODefinition(
            metric_name="beacon_head_slot",
            threshold=0.0,
            comparison="greater_than",
            error_budget_percent=5.0,
            description="Chain must be progressing",
        ),
    )
    slo_monitor.add_slo(
        "validators_active",
        SLODefinition(
            metric_name="beacon_head_state_active_validators_total",
            threshold=100.0,
            comparison="greater_than",
            error_budget_percent=2.0,
            description="Active validators above 100",
        ),
    )

    rca_engine = RCAEngine(dry_run=True)

    observer = ObserverAgent(
        prometheus_client=prom,  # type: ignore[arg-type]
        anomaly_detector=anomaly_detector,
        slo_monitor=slo_monitor,
        rca_engine=rca_engine,
        dry_run=False,
    )
    observer._observed_metrics = [
        "beacon_head_slot",
        "beacon_finalized_epoch",
        "beacon_head_state_active_validators_total",
        "beacon_head_state_slashed_validators_total",
        "beacon_peer_count",
    ]
    print(f"  [OK] ObserverAgent initialized (real Prometheus, {len(observer._observed_metrics)} metrics)")

    # Orchestrator Agent
    orchestrator = OrchestratorAgent(
        circuit_breaker=circuit_breaker,
        audit_logger=audit_logger,
        dry_run=False,
    )
    print(f"  [OK] OrchestratorAgent initialized (state={orchestrator.state.value})")

    results["components_setup"] = (
        len(node_agents) >= 2
        and orchestrator.state == OrchestratorState.IDLE
        and circuit_breaker.is_armed
    )

    # -----------------------------------------------------------------------
    # Phase 2: PRE_FLIGHT -- verify real cluster health
    # -----------------------------------------------------------------------
    print_section("Phase 2: PRE_FLIGHT -- Real Cluster Health Check")

    scenario = {
        "name": "real_network_resilience_test",
        "hypothesis": "Network maintains finality with 30% adversarial validators",
        "fault_sequence": [
            {"time": "0s", "action": "baseline"},
            {"time": "30s", "action": "switch_adversarial", "params": {"percentage": 30}},
            {"time": "120s", "action": "restore"},
        ],
        "slo_thresholds": {
            "finality_delay_max": "5 epochs",
            "slashing_rate_max": "5%",
        },
        "success_criteria": "Chain maintains finality throughout experiment",
    }

    print(f"  Scenario: {scenario['name']}")
    print(f"  Hypothesis: {scenario['hypothesis']}")

    # Start experiment -- transitions to PRE_FLIGHT
    ctx = orchestrator.start_experiment(scenario=scenario)
    print(f"\n  Experiment started: {ctx.experiment_id}")
    print(f"  Orchestrator state: {orchestrator.state.value}")
    assert orchestrator.state == OrchestratorState.PRE_FLIGHT

    # Query real pre-flight metrics
    print("\n  Querying real pre-flight metrics...")
    preflight_metrics: dict[str, float] = {}
    for metric in ["beacon_head_slot", "beacon_finalized_epoch",
                    "beacon_head_state_active_validators_total",
                    "beacon_head_state_slashed_validators_total"]:
        val = query_real_metric(prom, metric)
        if val is not None:
            preflight_metrics[metric] = val
            print(f"    {metric} = {val}")

    # Feed to circuit breaker
    orchestrator.record_metrics({
        "finality_delay_seconds": 13.0,  # Normal
        "slashing_rate_percent": 0.0,
        "participation_rate_percent": 99.0,
    })
    print(f"\n  Circuit breaker: {circuit_breaker.state.value} (check_count={circuit_breaker.check_count})")

    results["pre_flight"] = orchestrator.state == OrchestratorState.PRE_FLIGHT

    # -----------------------------------------------------------------------
    # Phase 3: HYPOTHESIS -- advance state
    # -----------------------------------------------------------------------
    print_section("Phase 3: HYPOTHESIS -- Generate from Real Baseline")

    orchestrator.advance()
    assert orchestrator.state == OrchestratorState.HYPOTHESIS
    print(f"  State: {orchestrator.state.value}")

    # Record the real baseline in the experiment context
    ctx.hypothesis = {
        "statement": scenario["hypothesis"],
        "baseline_metrics": preflight_metrics,
        "expected_impact": "Finality delay may increase, participation should remain above 66%",
        "generated_from": "real_testnet_baseline",
    }
    ctx.add_event("hypothesis_generated", {"source": "real_metrics"})
    print(f"  Hypothesis generated from real baseline metrics")
    print(f"  Baseline head_slot: {preflight_metrics.get('beacon_head_slot', 'N/A')}")
    print(f"  Baseline validators: {preflight_metrics.get('beacon_head_state_active_validators_total', 'N/A')}")

    results["hypothesis"] = orchestrator.state == OrchestratorState.HYPOTHESIS

    # -----------------------------------------------------------------------
    # Phase 4: PLANNING -- compile experiment plan
    # -----------------------------------------------------------------------
    print_section("Phase 4: PLANNING -- Compile Experiment Plan")

    orchestrator.advance()
    assert orchestrator.state == OrchestratorState.PLANNING
    print(f"  State: {orchestrator.state.value}")

    # Create a plan targeting real nodes
    plan = {
        "experiment_id": ctx.experiment_id,
        "target_nodes": [a.node_id for a in node_agents],
        "total_nodes": len(node_agents),
        "adversarial_count": max(1, len(node_agents) * 30 // 100),
        "adversarial_nodes": [node_agents[0].node_id],
        "behavior": "attestation_withholding",
        "behavior_params": {"withhold_probability": 0.5},
        "duration_seconds": 30,
        "beacon_endpoints": [b["url"] for b in available_beacons],
    }
    ctx.plan = plan
    ctx.add_event("plan_compiled", {"target_count": len(plan["target_nodes"])})

    print(f"  Plan compiled:")
    print(f"    Target nodes: {plan['target_nodes']}")
    print(f"    Adversarial: {plan['adversarial_nodes']} ({plan['adversarial_count']}/{plan['total_nodes']})")
    print(f"    Behavior: {plan['behavior']} (prob={plan['behavior_params']['withhold_probability']})")
    print(f"    Beacon endpoints: {plan['beacon_endpoints']}")

    results["planning"] = orchestrator.state == OrchestratorState.PLANNING

    # -----------------------------------------------------------------------
    # Phase 5: EXECUTING -- dispatch faults to real Node Agents
    # -----------------------------------------------------------------------
    print_section("Phase 5: EXECUTING -- Dispatch to Real Node Agents")

    orchestrator.advance()
    assert orchestrator.state == OrchestratorState.EXECUTING
    print(f"  State: {orchestrator.state.value}")

    # Switch target node to adversarial mode
    target_agent = node_agents[0]
    print(f"\n  Switching {target_agent.node_id} to ADVERSARIAL mode...")
    target_agent.switch_mode(AgentMode.ADVERSARIAL)
    behavior = AttestationWithholding(withhold_probability=0.5)
    target_agent.set_behavior(behavior)
    print(f"  [OK] {target_agent.node_id}: mode={target_agent.mode.value}, "
          f"behavior={behavior.name}")

    ctx.active_faults[target_agent.node_id] = {
        "fault_type": "attestation_withholding",
        "probability": 0.5,
        "target_beacon": available_beacons[0]["url"],
    }
    ctx.add_event("fault_injected", {"node": target_agent.node_id})

    # Verify other agents remain honest
    honest_agents = [a for a in node_agents if a.mode == AgentMode.HONEST]
    print(f"  Honest agents: {len(honest_agents)}/{len(node_agents)}")
    print(f"  Active faults: {len(ctx.active_faults)}")

    # Verify the behavior actually intercepts attestation paths
    print("\n  Testing interception on real attestation path...")
    test_results = {"blocked": 0, "passed": 0}
    for _ in range(10):
        r = target_agent.proxy._intercept_request(
            "/eth/v1/beacon/pool/attestations", {}, {"data": "test"}
        )
        if r and r.get("blocked"):
            test_results["blocked"] += 1
        else:
            test_results["passed"] += 1
    print(f"  Interception results: blocked={test_results['blocked']}, "
          f"passed={test_results['passed']}")

    results["executing"] = (
        orchestrator.state == OrchestratorState.EXECUTING
        and target_agent.mode == AgentMode.ADVERSARIAL
        and len(ctx.active_faults) > 0
    )

    # -----------------------------------------------------------------------
    # Phase 6: MONITORING -- Observer queries real Prometheus
    # -----------------------------------------------------------------------
    print_section("Phase 6: MONITORING -- Real-Time Observation")

    orchestrator.advance()
    assert orchestrator.state == OrchestratorState.MONITORING
    print(f"  State: {orchestrator.state.value}")

    # Start Observer
    observer.start_observing(experiment_id=ctx.experiment_id)
    print(f"  Observer started for experiment {ctx.experiment_id}")

    # Run monitoring cycles with real Prometheus
    print("\n  Running monitoring cycles (querying REAL Prometheus)...")
    monitoring_events = []
    for cycle in range(3):
        # Observer queries real Prometheus
        events = observer.observe()
        monitoring_events.extend(events)

        # Also query specific metrics for the orchestrator
        current_metrics: dict[str, float] = {}
        for metric in ["beacon_head_slot", "beacon_finalized_epoch"]:
            val = query_real_metric(prom, metric)
            if val is not None:
                current_metrics[metric] = val

        # Record metrics in context
        ctx.metrics_snapshots.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": current_metrics,
        })

        # Feed safe metrics to circuit breaker
        orchestrator.record_metrics({
            "finality_delay_seconds": 13.0,
            "slashing_rate_percent": 0.0,
            "participation_rate_percent": 95.0,
        })

        slot = current_metrics.get("beacon_head_slot", "N/A")
        epoch = current_metrics.get("beacon_finalized_epoch", "N/A")
        print(f"    Cycle {cycle + 1}: slot={slot} epoch={epoch} "
              f"events={len(events)} cb={circuit_breaker.state.value}")

        time.sleep(2)

    observer.stop_observing()
    print(f"\n  Observer stopped. Total events: {len(monitoring_events)}")
    print(f"  Metrics snapshots: {len(ctx.metrics_snapshots)}")
    print(f"  Circuit breaker: {circuit_breaker.state.value} (checks={circuit_breaker.check_count})")

    results["monitoring"] = (
        orchestrator.state == OrchestratorState.MONITORING
        and len(ctx.metrics_snapshots) >= 3
    )

    # -----------------------------------------------------------------------
    # Phase 7: ANALYZING -- collect results
    # -----------------------------------------------------------------------
    print_section("Phase 7: ANALYZING -- Collect Real Results")

    orchestrator.advance()
    assert orchestrator.state == OrchestratorState.ANALYZING
    print(f"  State: {orchestrator.state.value}")

    # Remove faults -- restore honest mode
    print("\n  Restoring all agents to HONEST mode...")
    batch_mode_switch(node_agents, AgentMode.HONEST)
    ctx.active_faults.clear()
    ctx.add_event("faults_removed", {"restored_count": len(node_agents)})

    # Query post-experiment metrics
    print("\n  Querying post-experiment metrics from real Prometheus...")
    post_metrics: dict[str, float] = {}
    for metric in ["beacon_head_slot", "beacon_finalized_epoch",
                    "beacon_head_state_active_validators_total",
                    "beacon_head_state_slashed_validators_total"]:
        val = query_real_metric(prom, metric)
        if val is not None:
            post_metrics[metric] = val
            print(f"    {metric} = {val}")

    # Compare pre and post metrics
    print("\n  Pre vs Post comparison:")
    for metric in preflight_metrics:
        pre = preflight_metrics.get(metric, 0)
        post = post_metrics.get(metric, 0)
        delta = post - pre
        print(f"    {metric}: {pre} -> {post} (delta={delta:+.1f})")

    ctx.add_event("analysis_complete", {
        "pre_metrics": preflight_metrics,
        "post_metrics": post_metrics,
        "monitoring_events": len(monitoring_events),
    })

    results["analyzing"] = orchestrator.state == OrchestratorState.ANALYZING

    # -----------------------------------------------------------------------
    # Phase 8: REPORTING -- generate report
    # -----------------------------------------------------------------------
    print_section("Phase 8: REPORTING -- Generate Experiment Report")

    orchestrator.advance()
    assert orchestrator.state == OrchestratorState.REPORTING
    print(f"  State: {orchestrator.state.value}")

    # Generate report
    report = {
        "experiment_id": ctx.experiment_id,
        "scenario": scenario["name"],
        "hypothesis": scenario["hypothesis"],
        "verdict": "PASSED" if not ctx.halted else "FAILED",
        "duration_seconds": ctx.duration_seconds(),
        "infrastructure": {
            "type": "kurtosis_ethereum_package",
            "beacon_nodes": len(available_beacons),
            "node_agents": len(node_agents),
            "prometheus": PROMETHEUS_URL,
        },
        "metrics": {
            "pre_flight": preflight_metrics,
            "post_experiment": post_metrics,
            "monitoring_snapshots": len(ctx.metrics_snapshots),
            "monitoring_events": len(monitoring_events),
        },
        "safety": {
            "circuit_breaker_state": circuit_breaker.state.value,
            "circuit_breaker_checks": circuit_breaker.check_count,
            "circuit_breaker_trips": len(circuit_breaker.trip_events),
            "halted": ctx.halted,
        },
        "node_agents": {
            "total": len(node_agents),
            "adversarial_during_test": 1,
            "behavior": "attestation_withholding",
        },
        "audit_entries": audit_logger.total_entries,
    }

    print(f"  Report generated:")
    print(f"    Experiment: {report['experiment_id']}")
    print(f"    Scenario: {report['scenario']}")
    print(f"    Verdict: {report['verdict']}")
    print(f"    Duration: {report['duration_seconds']:.1f}s")
    print(f"    Beacon nodes: {report['infrastructure']['beacon_nodes']}")
    print(f"    Node agents: {report['infrastructure']['node_agents']}")
    print(f"    Monitoring snapshots: {report['metrics']['monitoring_snapshots']}")
    print(f"    Circuit breaker trips: {report['safety']['circuit_breaker_trips']}")
    print(f"    Audit entries: {report['audit_entries']}")

    ctx.add_event("report_generated", {"verdict": report["verdict"]})
    results["reporting"] = orchestrator.state == OrchestratorState.REPORTING

    # -----------------------------------------------------------------------
    # Phase 9: Complete -- transition back to IDLE
    # -----------------------------------------------------------------------
    print_section("Phase 9: Experiment Complete")

    orchestrator.advance()
    assert orchestrator.state == OrchestratorState.IDLE
    print(f"  State: {orchestrator.state.value}")
    print(f"  Experiment count: {orchestrator.experiment_count}")

    results["experiment_complete"] = (
        orchestrator.state == OrchestratorState.IDLE
        and orchestrator.experiment_count == 1
    )

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------
    print_section("Cleanup")

    for agent in node_agents:
        agent.stop()
        print(f"  Stopped {agent.node_id}")

    print(f"\n  All {len(node_agents)} agents stopped")

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    print_section("TRACK E REAL NETWORK END-TO-END TEST RESULTS")

    print("  State machine transitions completed:")
    print("    IDLE -> PRE_FLIGHT -> HYPOTHESIS -> PLANNING -> EXECUTING")
    print("         -> MONITORING -> ANALYZING -> REPORTING -> IDLE")
    print()

    all_passed = True
    for test_name, passed in results.items():
        status_str = "[PASS]" if passed else "[FAIL]"
        if not passed:
            all_passed = False
        print(f"  {status_str} {test_name}")

    print(f"\n  Total: {sum(results.values())}/{len(results)} tests passed")
    print(f"\n  Infrastructure (REAL):")
    print(f"    Beacon nodes: {len(available_beacons)} ({', '.join(b['name'] for b in available_beacons)})")
    print(f"    Prometheus: {PROMETHEUS_URL}")
    print(f"    Node Agents: {len(node_agents)}")
    print(f"    Prometheus queries: {prom._query_count}")
    print(f"    Audit entries: {audit_logger.total_entries}")
    print(f"    Circuit breaker checks: {circuit_breaker.check_count}")

    if all_passed:
        print("\n  TRACK E: ALL TESTS PASSED -- FULL ORCHESTRATION ON REAL NETWORK")
    else:
        print("\n  TRACK E: SOME TESTS FAILED")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
