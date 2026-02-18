#!/usr/bin/env python3
"""Demo: Basic Attestation Withholding Experiment.

Demonstrates the complete multi-agent chaos engineering pipeline:
  1. Orchestrator creates and manages a fleet of 10 node agents
  2. 70% honest / 30% adversarial split is established
  3. Hypothesis is generated for attestation withholding
  4. Experiment plan is compiled and dispatched
  5. Monitoring cycles collect metrics during fault injection
  6. Analysis phase generates experiment report

Run with:
    python demos/basic_withholding_demo.py

This demo runs entirely in dry-run mode (no real infrastructure needed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add source to path for direct execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chaoswopr.agents.experiment_runner import ExperimentRunner, ExperimentRunnerConfig
from chaoswopr.agents.llm_client import MockLLMClient
from chaoswopr.agents.node_coordinator import FleetConfig
from chaoswopr.agents.scenario_loader import ScenarioBuilder


def main() -> None:
    """Run the basic attestation withholding demo."""
    print("=" * 70)
    print("chaoswopr - Basic Attestation Withholding Demo")
    print("=" * 70)
    print()

    # Step 1: Build scenario
    print("[1/6] Building scenario...")
    scenario = ScenarioBuilder.attestation_withholding(
        target_percent=30.0,
        withhold_probability=1.0,
        duration_seconds=600,
        node_count=10,
    )
    print(f"  Scenario: {scenario.name}")
    print(f"  Hypothesis: {scenario.hypothesis}")
    print(f"  Blast radius: {scenario.blast_radius['max_affected_percent']}%")
    print(f"  Fault steps: {len(scenario.fault_sequence)}")
    print()

    # Step 2: Configure runner
    print("[2/6] Configuring experiment runner...")
    config = ExperimentRunnerConfig(
        fleet_config=FleetConfig(
            num_agents=10,
            adversarial_ratio=0.3,
        ),
        monitoring_interval_seconds=5.0,
        dry_run=True,
    )
    runner = ExperimentRunner(config)
    print(f"  Fleet: {config.fleet_config.num_agents} agents")
    print(f"  Adversarial ratio: {config.fleet_config.adversarial_ratio}")
    print(f"  Dry run: {config.dry_run}")
    print()

    # Step 3: Run experiment
    print("[3/6] Running experiment (5-phase workflow)...")
    print("  PRE-FLIGHT -> HYPOTHESIS -> PLANNING -> EXECUTING/MONITORING -> ANALYSIS")
    print()
    result = runner.run_experiment(scenario.to_dict())

    # Step 4: Display results
    print("[4/6] Experiment Results:")
    print(f"  Experiment ID: {result.experiment_id}")
    print(f"  Success: {result.success}")
    print(f"  Duration: {result.duration_seconds:.2f}s")
    print(f"  Halted: {result.halted}")
    if result.halt_reason:
        print(f"  Halt reason: {result.halt_reason}")
    print()

    # Step 5: Display hypothesis
    print("[5/6] Generated Hypothesis:")
    if result.hypothesis:
        print(f"  Prediction: {result.hypothesis.get('prediction', 'N/A')}")
        print(f"  Confidence: {result.hypothesis.get('confidence', 'N/A')}")
        print(f"  Blast radius: {result.hypothesis.get('blast_radius_percent', 'N/A')}%")
        timeline = result.hypothesis.get("fault_timeline", [])
        print(f"  Fault timeline steps: {len(timeline)}")
        for i, step in enumerate(timeline):
            print(f"    [{i}] t={step.get('time_offset_seconds', '?')}s: {step.get('action_type', '?')}")
    print()

    # Step 6: Display plan and metrics
    print("[6/6] Experiment Plan & Metrics:")
    if result.plan:
        actions = result.plan.get("actions", [])
        print(f"  Plan actions: {len(actions)}")
        for i, action in enumerate(actions[:5]):
            print(f"    [{i}] {action.get('action_type', '?')} at t={action.get('start_time_seconds', '?')}s")
    print(f"  Observation events: {len(result.observation_events)}")
    print(f"  Metrics snapshots: {len(result.metrics_snapshots)}")
    print()

    # Fleet status
    fleet = result.fleet_status
    if fleet:
        print("  Fleet Status:")
        print(f"    Total agents: {fleet.get('total_agents', 'N/A')}")
        print(f"    Honest: {fleet.get('honest_count', 'N/A')}")
        print(f"    Adversarial: {fleet.get('adversarial_count', 'N/A')}")
    print()

    # Message bus stats
    status = runner.get_status()
    bus_stats = status.get("bus_stats", {})
    print("  Message Bus Stats:")
    print(f"    Messages published: {bus_stats.get('messages_published', 0)}")
    print(f"    Messages delivered: {bus_stats.get('messages_delivered', 0)}")
    print(f"    Total subscribers: {bus_stats.get('total_subscribers', 0)}")
    print()

    # Final status
    print("=" * 70)
    if result.success:
        print("DEMO PASSED: Experiment completed successfully")
    else:
        print(f"DEMO FAILED: {result.error_message}")
    print("=" * 70)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
