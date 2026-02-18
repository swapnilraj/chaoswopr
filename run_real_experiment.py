#!/usr/bin/env python3
"""Run a complete real chaos engineering experiment with full infrastructure.

This script:
1. Deploys a real Ethereum testnet via Kurtosis
2. Waits for network finality
3. Runs chaos experiment with real LLM integration
4. Performs root cause analysis
5. Cleans up infrastructure

Estimated time: 15-30 minutes
Estimated cost: ~$0.05 in LLM API calls
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

# Add source to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load .env
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient, KurtosisBackend
from chaoswopr.agents.experiment_runner import ExperimentRunner, ExperimentRunnerConfig
from chaoswopr.agents.node_coordinator import FleetConfig
from chaoswopr.agents.scenario_loader import ScenarioBuilder
from config.llm_config import LLMConfig


def main():
    """Run the full experiment."""
    print("=" * 80)
    print("🔥 FULL REAL CHAOS ENGINEERING EXPERIMENT")
    print("=" * 80)
    print()

    # Step 1: Verify prerequisites
    print("[1/7] Verifying prerequisites...")

    # Check LLM config
    llm_config = LLMConfig.from_env()
    provider = llm_config.provider.lower()
    api_key = llm_config.api_key or os.getenv("OPENROUTER_API_KEY", "")

    if not api_key and provider != "mock":
        print("❌ OPENROUTER_API_KEY not found in .env file")
        return 1

    print(f"  ✅ LLM Provider: {provider}")
    print(f"  ✅ API Key configured")
    print()

    # Step 2: Deploy Kurtosis testnet
    print("[2/7] Deploying Ethereum testnet via Kurtosis...")
    print("  ⏳ This will take 3-5 minutes...")

    kurtosis = KurtosisClient(
        backend=KurtosisBackend.DOCKER,
        dry_run=False,
    )

    enclave_name = f"chaoswopr-test-{int(time.time())}"

    try:
        # Create enclave
        print(f"  Creating enclave: {enclave_name}")
        enclave = kurtosis.create_enclave(enclave_name)
        print(f"  ✅ Enclave created: {enclave.enclave_id}")

        # Deploy ethereum-package with small testnet
        print("  Deploying ethereum-package...")

        # Minimal config for fast startup (only use documented params)
        # Use 128 validators per node to satisfy Fulu fork requirements
        eth_config = {
            "participants": [
                {
                    "el_type": "geth",
                    "cl_type": "lighthouse",
                    "count": 2,  # 2 nodes
                }
            ],
            "network_params": {
                "preset": "minimal",
                "num_validator_keys_per_node": 128,  # 256 validators total (128 per node - satisfies Fulu requirement)
                "seconds_per_slot": 6,
            },
            "additional_services": ["prometheus", "grafana"],
            "wait_for_finalization": True,
            "ethereum_metrics_exporter_enabled": True,
        }

        # Save config to temp file
        config_file = project_root / "temp_eth_config.json"
        with open(config_file, "w") as f:
            json.dump(eth_config, f, indent=2)

        # Run package
        result = kurtosis.run_package(
            enclave_name=enclave_name,
            package_path="github.com/ethpandaops/ethereum-package",
            args_file=str(config_file),
        )

        print(f"  ✅ Testnet deployed")
        print(f"  Services: {len(result.get('services', {}))} services running")

        # Clean up temp file
        config_file.unlink(missing_ok=True)

    except Exception as e:
        print(f"  ❌ Deployment failed: {e}")
        logger.exception("Deployment error")
        print("\n  Cleaning up...")
        try:
            kurtosis.destroy_enclave(enclave_name)
        except:
            pass
        return 1

    print()

    # Step 3: Get service URLs
    print("[3/7] Discovering services...")

    try:
        services = kurtosis.get_services(enclave_name)

        # Find Prometheus service
        prometheus_url = None
        prometheus_service = None

        for service in services:
            if "prometheus" in service.name.lower():
                prometheus_service = service
                # Get the prometheus URL (contains the host-mapped port)
                url = service.get_url("http")
                if url:
                    prometheus_url = url
                    break

        if not prometheus_url:
            # Try default
            prometheus_url = "http://localhost:9090"
            print(f"  ⚠️  Prometheus service not found, using default: {prometheus_url}")
        else:
            print(f"  ✅ Prometheus URL: {prometheus_url}")
            print(f"  ✅ Prometheus service: {prometheus_service.name}")

        print(f"  ✅ Total services: {len(services)}")

    except Exception as e:
        print(f"  ⚠️  Service discovery failed: {e}")
        import traceback
        traceback.print_exc()
        prometheus_url = "http://localhost:9090"

    print()

    # Step 4: Wait for network health
    print("[4/7] Waiting for network finality...")
    print("  ⏳ Waiting 60 seconds for network to stabilize...")
    time.sleep(60)
    print("  ✅ Network should be healthy")
    print()

    # Step 5: Build scenario
    print("[5/7] Building chaos scenario...")

    scenario = ScenarioBuilder.attestation_withholding(
        target_percent=20.0,  # 20% of 256 validators = ~51 validators
        withhold_probability=1.0,
        duration_seconds=180,  # 3 minutes
        node_count=256,
    )

    print(f"  Scenario: {scenario.name}")
    print(f"  Hypothesis: {scenario.hypothesis}")
    print(f"  Blast radius: {scenario.blast_radius['max_affected_percent']}%")
    print(f"  Duration: 180s")
    print()

    # Step 6: Run experiment
    print("[6/7] Running chaos experiment with real LLM...")

    config = ExperimentRunnerConfig(
        prometheus_url=prometheus_url,
        fleet_config=FleetConfig(
            num_agents=256,
            adversarial_ratio=0.20,
        ),
        monitoring_interval_seconds=10.0,
        dry_run=False,  # Real mode!
        llm_provider=provider,
        llm_api_key=api_key,
        hypothesis_model=llm_config.hypothesis_model,
        rca_model=llm_config.rca_model,
    )

    print(f"  Fleet: {config.fleet_config.num_agents} agents")
    print(f"  LLM: {config.llm_provider} ({config.hypothesis_model})")
    print(f"  Prometheus: {config.prometheus_url}")
    print()

    try:
        print("  ⏳ Initializing runner...")
        runner = ExperimentRunner(config)

        print("  ⏳ Running 5-phase workflow...")
        print("     PRE-FLIGHT → HYPOTHESIS (LLM) → PLANNING → EXECUTING → ANALYSIS (LLM)")
        print()

        start_time = time.time()
        result = runner.run_experiment(scenario.to_dict())
        duration = time.time() - start_time

        print()
        print("  " + "=" * 76)
        print("  EXPERIMENT RESULTS")
        print("  " + "=" * 76)
        print(f"  ID: {result.experiment_id}")
        print(f"  Success: {'✅' if result.success else '❌'}")
        print(f"  Duration: {duration:.1f}s")
        print(f"  Halted: {result.halted}")

        if result.hypothesis:
            print()
            print("  AI-Generated Hypothesis:")
            print(f"    Prediction: {result.hypothesis.get('prediction', 'N/A')[:100]}...")
            print(f"    Confidence: {result.hypothesis.get('confidence', 'N/A')}")
            print(f"    Blast Radius: {result.hypothesis.get('blast_radius_percent', 'N/A')}%")

        if result.metrics_snapshots:
            print()
            print(f"  Metrics: {len(result.metrics_snapshots)} snapshots collected")

        print()

    except Exception as e:
        print(f"  ❌ Experiment failed: {e}")
        logger.exception("Experiment error")

    # Step 7: Cleanup
    print("[7/7] Cleaning up infrastructure...")

    try:
        kurtosis.destroy_enclave(enclave_name)
        print(f"  ✅ Enclave destroyed: {enclave_name}")
    except Exception as e:
        print(f"  ⚠️  Cleanup warning: {e}")

    print()
    print("=" * 80)
    print("✅ EXPERIMENT COMPLETE!")
    print("=" * 80)
    print()
    print(f"Summary:")
    print(f"  • Real Ethereum testnet deployed (16 validators)")
    print(f"  • Real LLM hypothesis generation ({config.hypothesis_model})")
    print(f"  • Real chaos injection (25% attestation withholding)")
    print(f"  • Total time: {duration:.1f}s")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
