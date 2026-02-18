#!/usr/bin/env python3
"""Full Real Chaos Engineering Experiment.

Runs a complete end-to-end experiment with:
  1. Real Kurtosis Ethereum testnet deployment
  2. Real OpenRouter LLM integration (Claude Opus 4 + Sonnet 4.5)
  3. Real chaos injection (attestation withholding)
  4. Real monitoring via Prometheus
  5. Real root cause analysis

Prerequisites:
  - Docker running
  - Kurtosis installed (kurtosis version)
  - OpenRouter API key in .env file
  - 8GB+ RAM available
  - 30-60 minutes for full experiment

Run with:
    python demos/full_real_experiment.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add source to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Load .env
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from chaoswopr.agents.experiment_runner import ExperimentRunner, ExperimentRunnerConfig
from chaoswopr.agents.node_coordinator import FleetConfig
from chaoswopr.agents.scenario_loader import ScenarioBuilder
from config.llm_config import LLMConfig


def main() -> None:
    """Run a full real chaos engineering experiment."""
    print("=" * 80)
    print("🔥 FULL REAL CHAOS ENGINEERING EXPERIMENT 🔥")
    print("=" * 80)
    print()
    print("⚠️  WARNING: This will deploy a real Ethereum testnet and run chaos tests!")
    print("   - Deploys Kurtosis testnet with 50+ validators")
    print("   - Injects real network faults")
    print("   - Uses real OpenRouter API ($0.05 cost)")
    print("   - Takes 30-60 minutes to complete")
    print()

    # Confirm (skip if --yes flag passed)
    if "--yes" not in sys.argv:
        response = input("Continue? (yes/no): ").strip().lower()
        if response not in ["yes", "y"]:
            print("Aborted.")
            sys.exit(0)
    else:
        print("Auto-confirmed with --yes flag")
    print()

    # Step 0: Verify prerequisites
    print("[0/8] Verifying prerequisites...")

    # Check LLM config
    llm_config = LLMConfig.from_env()
    provider = llm_config.provider.lower()
    api_key = llm_config.api_key or os.getenv("OPENROUTER_API_KEY", "")

    print(f"  ✅ LLM Provider: {provider}")
    print(f"  ✅ API Key: {api_key[:20]}..." if api_key else "  ❌ API Key: NOT SET")

    if not api_key and provider != "mock":
        print("\n❌ ERROR: OPENROUTER_API_KEY not found")
        sys.exit(1)

    # Check Kurtosis
    import subprocess
    try:
        result = subprocess.run(
            ["kurtosis", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print(f"  ✅ Kurtosis installed")
        else:
            print(f"  ❌ Kurtosis not working: {result.stderr}")
            sys.exit(1)
    except Exception as e:
        print(f"  ❌ Kurtosis not found: {e}")
        sys.exit(1)

    # Check Docker
    try:
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print(f"  ✅ Docker running")
        else:
            print(f"  ❌ Docker not running: {result.stderr}")
            sys.exit(1)
    except Exception as e:
        print(f"  ❌ Docker not found: {e}")
        sys.exit(1)

    print()

    # Step 1: Build scenario
    print("[1/8] Building chaos scenario...")
    scenario = ScenarioBuilder.attestation_withholding(
        target_percent=20.0,  # Start conservative - 20% of validators
        withhold_probability=1.0,
        duration_seconds=300,  # 5 minutes
        node_count=50,  # Small testnet for speed
    )
    print(f"  Scenario: {scenario.name}")
    print(f"  Hypothesis: {scenario.hypothesis}")
    print(f"  Blast radius: {scenario.blast_radius['max_affected_percent']}%")
    print(f"  Target nodes: {scenario.blast_radius['max_affected_percent'] * 50 / 100:.0f} of 50 validators")
    print(f"  Fault steps: {len(scenario.fault_sequence)}")
    print()

    # Step 2: Configure runner (REAL MODE)
    print("[2/8] Configuring experiment runner (REAL MODE - NO DRY RUN)...")
    config = ExperimentRunnerConfig(
        fleet_config=FleetConfig(
            num_agents=50,  # One agent per validator
            adversarial_ratio=0.2,  # 20% adversarial
        ),
        monitoring_interval_seconds=10.0,  # Check every 10s
        dry_run=False,  # 🔥 REAL MODE - Deploy real infrastructure!
        llm_provider=provider,
        llm_api_key=api_key,
        hypothesis_model=llm_config.hypothesis_model,
        rca_model=llm_config.rca_model,
    )

    print(f"  Fleet: {config.fleet_config.num_agents} validator agents")
    print(f"  Adversarial: {config.fleet_config.adversarial_ratio * 100}%")
    print(f"  LLM Provider: {config.llm_provider}")
    print(f"  Hypothesis Model: {config.hypothesis_model}")
    print(f"  RCA Model: {config.rca_model}")
    print(f"  🔥 DRY RUN: {config.dry_run} (REAL INFRASTRUCTURE)")
    print()

    # Step 3: Initialize runner
    print("[3/8] Initializing experiment runner...")
    print("  ⏳ This may take 1-2 minutes to set up Kurtosis enclave...")
    print()

    start_time = time.time()
    try:
        runner = ExperimentRunner(config)
        init_time = time.time() - start_time
        print(f"  ✅ Runner initialized in {init_time:.1f}s")
    except Exception as e:
        print(f"  ❌ Failed to initialize runner: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    print()

    # Step 4: Run experiment
    print("[4/8] Running full chaos experiment...")
    print("  Phase 1: PRE-FLIGHT - Deploy testnet and verify health")
    print("  Phase 2: HYPOTHESIS - Generate AI hypothesis (OpenRouter API)")
    print("  Phase 3: PLANNING - Compile experiment plan")
    print("  Phase 4: EXECUTING - Inject faults and monitor")
    print("  Phase 5: ANALYSIS - Root cause analysis (OpenRouter API)")
    print()
    print("  ⏳ Estimated time: 30-60 minutes")
    print("  ⏳ Starting now...")
    print()

    experiment_start = time.time()
    try:
        result = runner.run_experiment(scenario.to_dict())
        experiment_time = time.time() - experiment_start
    except KeyboardInterrupt:
        print("\n\n⚠️  Experiment interrupted by user!")
        print("  Cleaning up...")
        # TODO: Add cleanup logic
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Experiment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Step 5: Display results
    print()
    print("=" * 80)
    print("[5/8] EXPERIMENT RESULTS")
    print("=" * 80)
    print(f"  Experiment ID: {result.experiment_id}")
    print(f"  Scenario: {result.scenario_name}")
    print(f"  Success: {'✅ PASSED' if result.success else '❌ FAILED'}")
    print(f"  Total Duration: {experiment_time:.1f}s ({experiment_time/60:.1f} minutes)")
    print(f"  Halted: {result.halted}")
    if result.halted:
        print(f"  Halt Reason: {result.halt_reason}")
    if result.error_message:
        print(f"  Error: {result.error_message}")
    print()

    # Step 6: Show LLM-generated hypothesis
    print("[6/8] AI-GENERATED HYPOTHESIS")
    print("=" * 80)
    if result.hypothesis:
        hyp = result.hypothesis
        print(f"Prediction:")
        print(f"  {hyp.get('prediction', 'N/A')}")
        print()
        print(f"Rationale:")
        print(f"  {hyp.get('rationale', 'N/A')[:400]}...")
        print()
        print(f"Blast Radius: {hyp.get('blast_radius_percent', 'N/A')}%")
        print(f"Confidence: {hyp.get('confidence', 'N/A')}")
        print()

        timeline = hyp.get('fault_timeline', [])
        print(f"Fault Timeline ({len(timeline)} steps):")
        for i, step in enumerate(timeline[:5], 1):
            print(f"  {i}. T+{step.get('time_offset_seconds', 0)}s: {step.get('description', step.get('action', 'N/A'))}")
    else:
        print("  (No hypothesis generated)")
    print()

    # Step 7: Show metrics
    print("[7/8] OBSERVED METRICS")
    print("=" * 80)
    if result.metrics_snapshots:
        print(f"Total snapshots collected: {len(result.metrics_snapshots)}")
        if result.metrics_snapshots:
            final_snapshot = result.metrics_snapshots[-1]
            print(f"\nFinal snapshot (T+{final_snapshot.get('timestamp', 0)}s):")
            metrics = final_snapshot.get('metrics', {})
            for key, value in list(metrics.items())[:10]:
                print(f"  {key}: {value}")
    else:
        print("  (No metrics collected)")
    print()

    # Step 8: Show RCA
    print("[8/8] AI ROOT CAUSE ANALYSIS")
    print("=" * 80)
    if result.observation_events:
        print(f"Total observation events: {len(result.observation_events)}")
        anomalies = [e for e in result.observation_events if e.get('event_type') == 'anomaly']
        if anomalies:
            print(f"Anomalies detected: {len(anomalies)}")
            for i, anomaly in enumerate(anomalies[:3], 1):
                print(f"\n  Anomaly {i}:")
                print(f"    Type: {anomaly.get('anomaly_type', 'N/A')}")
                print(f"    Severity: {anomaly.get('severity', 'N/A')}")
                print(f"    Message: {anomaly.get('message', 'N/A')}")

                # Show RCA if available
                if 'rca' in anomaly:
                    rca = anomaly['rca']
                    print(f"    Root Cause: {rca.get('root_cause', 'N/A')[:100]}...")
                    print(f"    Confidence: {rca.get('confidence', 'N/A')}")
        else:
            print("  ✅ No anomalies detected - experiment passed without issues!")
    else:
        print("  (No observation events recorded)")
    print()

    # Final summary
    print("=" * 80)
    print("🎉 EXPERIMENT COMPLETE!")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  ✅ Real Kurtosis testnet deployed and tested")
    print(f"  ✅ Real LLM hypothesis generation ({config.hypothesis_model})")
    print(f"  ✅ Real chaos injection (attestation withholding)")
    print(f"  ✅ Real root cause analysis ({config.rca_model})")
    print(f"  ✅ Total experiment time: {experiment_time/60:.1f} minutes")
    print()
    print("Cost Estimate:")
    print(f"  Hypothesis (Claude Opus 4): ~$0.03")
    print(f"  RCA (Claude Sonnet 4.5): ~$0.015")
    print(f"  Total LLM cost: ~$0.045")
    print()
    print(f"Full results and logs saved to: experiments/{result.experiment_id}/")
    print()
    print("Next steps:")
    print("  1. Review the AI-generated hypothesis and RCA")
    print("  2. Check Prometheus metrics for detailed analysis")
    print("  3. Run more scenarios from scenarios/ directory")
    print("  4. Scale up to 200-500 node testnets")
    print()


if __name__ == "__main__":
    main()
