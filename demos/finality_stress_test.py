#!/usr/bin/env python3
"""Demo: Finality Stress Test with Combined Faults.

Demonstrates multi-fault chaos engineering that combines:
  - Network latency injection (200ms on 20% of nodes)
  - Attestation withholding (30% of validators)

This test simulates compound failure scenarios similar to the
May 2023 Ethereum finality loss incident, where multiple factors
contributed to consensus degradation.

Run with:
    python demos/finality_stress_test.py

This demo runs entirely in dry-run mode (no real infrastructure needed).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add source to path for direct execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chaoswopr.agents.experiment_runner import ExperimentRunner, ExperimentRunnerConfig
from chaoswopr.agents.llm_client import MockLLMClient
from chaoswopr.agents.messaging.protocol import AgentType
from chaoswopr.agents.node_coordinator import FleetConfig
from chaoswopr.agents.orchestrator import OrchestratorState
from chaoswopr.agents.scenario_loader import ScenarioBuilder


def run_stress_test() -> bool:
    """Run the finality stress test and return success status."""
    print("=" * 70)
    print("chaoswopr - Finality Stress Test Demo")
    print("=" * 70)
    print()
    print("This test combines network latency + attestation withholding")
    print("to stress the consensus mechanism under compound failure.")
    print()

    # Build scenario
    scenario = ScenarioBuilder.finality_stress_test(
        adversarial_ratio=0.3,
        node_count=10,
        duration_seconds=600,
    )

    print(f"Scenario: {scenario.name}")
    print(f"Hypothesis: {scenario.hypothesis}")
    print(f"Tags: {', '.join(scenario.tags)}")
    print()

    # Print fault timeline
    print("Fault Sequence:")
    for i, step in enumerate(scenario.fault_sequence):
        action = step.get("action", "unknown")
        time_str = step.get("time", "?")
        desc = step.get("description", "")
        print(f"  [{i}] t={time_str}: {action}")
        if desc:
            print(f"       {desc}")
    print()

    # Configure runner
    config = ExperimentRunnerConfig(
        fleet_config=FleetConfig(
            num_agents=10,
            adversarial_ratio=0.3,
        ),
        dry_run=True,
    )
    runner = ExperimentRunner(config)

    # Run experiment
    print("Running 5-phase experiment workflow...")
    print("-" * 40)
    result = runner.run_experiment(scenario.to_dict())
    print("-" * 40)
    print()

    # Display results
    print("Results:")
    print(f"  Experiment ID:     {result.experiment_id}")
    print(f"  Success:           {result.success}")
    print(f"  Duration:          {result.duration_seconds:.2f}s")
    print(f"  Halted by safety:  {result.halted}")
    print()

    if result.hypothesis:
        print("Hypothesis:")
        print(f"  Prediction: {result.hypothesis.get('prediction', 'N/A')}")
        print(f"  Confidence: {result.hypothesis.get('confidence', 'N/A')}")
        timeline = result.hypothesis.get("fault_timeline", [])
        print(f"  Timeline:   {len(timeline)} steps")
        print()

    if result.plan:
        actions = result.plan.get("actions", [])
        print(f"Experiment Plan: {len(actions)} actions")
        for action in actions[:5]:
            print(f"  - {action.get('action_type', '?')} on {action.get('target_nodes', '?')} at t={action.get('start_time_seconds', '?')}s")
        print()

    print(f"Monitoring: {len(result.metrics_snapshots)} metric snapshots")
    print(f"Observer:   {len(result.observation_events)} events")
    print()

    # Fleet analysis
    fleet = result.fleet_status
    if fleet:
        print("Fleet Status:")
        print(f"  Total:       {fleet.get('total_agents', 0)} agents")
        print(f"  Honest:      {fleet.get('honest_count', 0)}")
        print(f"  Adversarial: {fleet.get('adversarial_count', 0)}")
        print()

    # Message bus analysis
    status = runner.get_status()
    bus = status.get("bus_stats", {})
    print("Communication:")
    print(f"  Messages published:  {bus.get('messages_published', 0)}")
    print(f"  Messages delivered:  {bus.get('messages_delivered', 0)}")
    print()

    # Verify orchestrator state
    orch_state = runner.orchestrator.state
    print(f"Orchestrator state: {orch_state.value}")
    assert orch_state == OrchestratorState.IDLE, "Orchestrator did not return to IDLE"
    print()

    return result.success


def run_comparison() -> None:
    """Run a comparison between single-fault and multi-fault scenarios."""
    print()
    print("=" * 70)
    print("Comparison: Single-Fault vs Multi-Fault")
    print("=" * 70)
    print()

    runner = ExperimentRunner(
        ExperimentRunnerConfig(
            fleet_config=FleetConfig(num_agents=10, adversarial_ratio=0.3),
            dry_run=True,
        )
    )

    # Single fault: just attestation withholding
    scenario_single = ScenarioBuilder.attestation_withholding(
        target_percent=30.0,
        node_count=10,
    )
    result_single = runner.run_experiment(scenario_single.to_dict())

    # Multi fault: combined latency + withholding
    scenario_multi = ScenarioBuilder.finality_stress_test(
        adversarial_ratio=0.3,
        node_count=10,
    )
    result_multi = runner.run_experiment(scenario_multi.to_dict())

    print(f"{'Metric':<30} {'Single Fault':<20} {'Multi Fault':<20}")
    print("-" * 70)
    print(f"{'Success':<30} {str(result_single.success):<20} {str(result_multi.success):<20}")
    print(f"{'Duration (s)':<30} {result_single.duration_seconds:<20.2f} {result_multi.duration_seconds:<20.2f}")
    print(f"{'Halted':<30} {str(result_single.halted):<20} {str(result_multi.halted):<20}")
    print(f"{'Observation events':<30} {len(result_single.observation_events):<20} {len(result_multi.observation_events):<20}")
    print(f"{'Metrics snapshots':<30} {len(result_single.metrics_snapshots):<20} {len(result_multi.metrics_snapshots):<20}")
    print()


def main() -> int:
    """Run all stress test demos."""
    success = run_stress_test()

    if success:
        run_comparison()

    print("=" * 70)
    if success:
        print("ALL DEMOS PASSED")
    else:
        print("DEMO FAILED")
    print("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
