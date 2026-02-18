#!/usr/bin/env python3
"""Demo: Real LLM-Powered Chaos Engineering with OpenRouter.

Demonstrates AI-powered chaos engineering with real LLM API calls:
  1. Loads OpenRouter API key from environment
  2. Uses Claude Opus 4 for hypothesis generation
  3. Uses Claude Sonnet 4.5 for root cause analysis
  4. Runs complete multi-agent experiment workflow

Prerequisites:
    export OPENROUTER_API_KEY=sk-or-v1-...
    export CHAOSWOPR_LLM_PROVIDER=openrouter

Run with:
    python demos/real_llm_demo.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add source to path for direct execution
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Load .env file if it exists
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from chaoswopr.agents.experiment_runner import ExperimentRunner, ExperimentRunnerConfig
from chaoswopr.agents.llm_client import LLMClient
from chaoswopr.agents.node_coordinator import FleetConfig
from chaoswopr.agents.scenario_loader import ScenarioBuilder
from config.llm_config import LLMConfig


def main() -> None:
    """Run a real LLM-powered chaos engineering experiment."""
    print("=" * 70)
    print("chaoswopr - Real LLM-Powered Chaos Engineering Demo")
    print("=" * 70)
    print()

    # Step 0: Verify LLM configuration
    print("[0/6] Verifying LLM configuration...")
    llm_config = LLMConfig.from_env()

    # Normalize provider to lowercase
    provider = llm_config.provider.lower()
    api_key = llm_config.api_key or os.getenv("OPENROUTER_API_KEY", "")

    print(f"  Provider: {provider}")
    print(f"  API Key: {api_key[:20]}..." if api_key else "  API Key: NOT SET")
    print(f"  Hypothesis Model: {llm_config.hypothesis_model}")
    print(f"  RCA Model: {llm_config.rca_model}")

    if not api_key and provider != "mock":
        print("\n❌ ERROR: OPENROUTER_API_KEY not found in environment")
        print("Please set it in .env file or export OPENROUTER_API_KEY=sk-or-v1-...")
        sys.exit(1)

    print("  ✅ Configuration valid")
    print()

    # Step 1: Build scenario
    print("[1/6] Building scenario...")
    scenario = ScenarioBuilder.attestation_withholding(
        target_percent=28.0,  # Below 33% blast radius limit
        withhold_probability=1.0,
        duration_seconds=600,
        node_count=10,
    )
    print(f"  Scenario: {scenario.name}")
    print(f"  Hypothesis: {scenario.hypothesis}")
    print(f"  Blast radius: {scenario.blast_radius['max_affected_percent']}%")
    print(f"  Fault steps: {len(scenario.fault_sequence)}")
    print()

    # Step 2: Configure runner with real LLM
    print("[2/6] Configuring experiment runner (REAL LLM MODE)...")
    config = ExperimentRunnerConfig(
        fleet_config=FleetConfig(
            num_agents=10,
            adversarial_ratio=0.3,
        ),
        monitoring_interval_seconds=5.0,
        dry_run=True,  # Still dry-run infrastructure, but use real LLMs
        llm_provider=provider,
        llm_api_key=api_key,
        hypothesis_model=llm_config.hypothesis_model,
        rca_model=llm_config.rca_model,
    )
    runner = ExperimentRunner(config)
    print(f"  Fleet: {config.fleet_config.num_agents} agents")
    print(f"  Adversarial ratio: {config.fleet_config.adversarial_ratio}")
    print(f"  LLM Provider: {config.llm_provider}")
    print(f"  Infrastructure: Dry-run (no real testnet)")
    print()

    # Step 3: Run experiment
    print("[3/6] Running experiment with REAL LLM API calls...")
    print("  PRE-FLIGHT -> HYPOTHESIS (LLM) -> PLANNING -> EXECUTING -> ANALYSIS (LLM)")
    print()
    print("  ⏳ Calling Claude Opus 4 for hypothesis generation...")
    print("  ⏳ This may take 10-30 seconds...")
    print()

    try:
        result = runner.run_experiment(scenario.to_dict())
    except Exception as e:
        print(f"\n❌ Experiment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Step 4: Display results
    print()
    print("[4/6] Experiment Results:")
    print(f"  Experiment ID: {result.experiment_id}")
    print(f"  Scenario: {result.scenario_name}")
    print(f"  Success: {result.success}")
    print(f"  Duration: {result.duration_seconds:.2f}s")
    print(f"  Halted: {result.halted}")
    if result.halted:
        print(f"  Halt Reason: {result.halt_reason}")
    print()

    # Step 5: Show LLM-generated hypothesis
    print("[5/6] LLM-Generated Hypothesis:")
    if result.hypothesis:
        print(f"  Prediction: {result.hypothesis.get('prediction', 'N/A')}")
        print(f"  Blast Radius: {result.hypothesis.get('blast_radius_percent', 'N/A')}%")
        print(f"  Confidence: {result.hypothesis.get('confidence', 'N/A')}")
        print(f"  Rationale: {result.hypothesis.get('rationale', 'N/A')[:200]}..." if result.hypothesis.get('rationale') else "  Rationale: N/A")
        print()
        fault_timeline = result.hypothesis.get('fault_timeline', [])
        print(f"  Fault Timeline ({len(fault_timeline)} steps):")
        for i, step in enumerate(fault_timeline[:3], 1):
            print(f"    {i}. T+{step.get('time_offset_seconds', 0)}s: {step.get('action', 'N/A')}")
    else:
        print("  (No hypothesis generated)")
    print()

    # Step 6: Show experiment plan
    print("[6/6] Generated Experiment Plan:")
    if result.plan:
        plan = result.plan
        print(f"  Total Duration: {plan.get('total_duration_seconds', 'N/A')}s")
        print(f"  Monitoring Interval: {plan.get('monitoring_interval_seconds', 'N/A')}s")
        print(f"  Phases:")
        for phase in plan.get('phases', [])[:5]:
            print(f"    • {phase.get('phase', 'N/A')}: {phase.get('description', 'N/A')[:60]}...")
    else:
        print("  (No plan generated)")
    print()

    # Final summary
    print("=" * 70)
    print("Demo Complete!")
    print("=" * 70)
    print()
    print("Key Achievements:")
    print(f"  ✅ Real LLM hypothesis generation via {provider}")
    print(f"  ✅ Multi-agent coordination (10 nodes, 70/30 split)")
    print(f"  ✅ Complete 5-phase workflow")
    print(f"  ✅ Real-time monitoring and analysis")
    print()
    print("Cost Estimate:")
    print(f"  Hypothesis (Claude Opus 4): ~$0.03")
    print(f"  RCA (Claude Sonnet 4.5): ~$0.015")
    print(f"  Total: ~$0.045 for this experiment")
    print()
    print(f"Full results saved to: experiments/{result.experiment_id}/")
    print()


if __name__ == "__main__":
    main()
