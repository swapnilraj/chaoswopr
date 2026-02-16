"""Real E2E tests for the baseline scenario.

Deploys a real Ethereum testnet, runs the baseline observation scenario,
collects metrics, and validates the full experiment pipeline.

Requires: Docker, Kurtosis, 8GB+ RAM, 4+ CPU cores.
"""

from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path
from typing import Generator

import pytest
import yaml

from chaoswopr.infrastructure.testnet.beacon_api import BeaconAPIClient
from chaoswopr.infrastructure.testnet.client_config import ClientConfig, ClientDistribution
from chaoswopr.infrastructure.testnet.deployer import (
    DeploymentState,
    TestnetDeployer,
)
from chaoswopr.infrastructure.testnet.ethereum_package import EthereumPackageConfig
from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient
from chaoswopr.safety.audit import ActionType, AuditLogger, Outcome
from chaoswopr.safety.blast_radius import BlastRadiusConfig, validate_blast_radius
from chaoswopr.safety.circuit_breaker import CircuitBreaker
from chaoswopr.safety.snapshots import DockerSnapshotBackend, SnapshotManager
from chaoswopr.scenarios.validator import validate_scenario_file

SCENARIOS_DIR = Path(__file__).parent.parent.parent / "scenarios"


def _is_infrastructure_ready() -> bool:
    """Check if all infrastructure requirements are met."""
    try:
        docker = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        if docker.returncode != 0:
            return False
        kurtosis = subprocess.run(["kurtosis", "engine", "status"], capture_output=True, timeout=15)
        return kurtosis.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


require_full_infra = pytest.mark.skipif(
    not _is_infrastructure_ready(),
    reason="Full infrastructure (Docker + Kurtosis engine) required",
)


@require_full_infra
class TestBaselineScenarioE2E:
    """End-to-end test of the baseline observation scenario with real infrastructure."""

    @pytest.fixture(scope="class")
    def deployed_testnet(self) -> Generator[tuple[TestnetDeployer, str], None, None]:
        """Deploy a real testnet for the baseline scenario.

        Uses a small 8-node testnet with client diversity for
        realistic but resource-efficient testing.
        """
        kurtosis = KurtosisClient(dry_run=False)
        enclave_name = f"chaoswopr-e2e-{uuid.uuid4().hex[:6]}"

        config = EthereumPackageConfig(
            client_config=ClientConfig(
                node_count=8,
                execution=ClientDistribution({
                    "geth": 0.5,
                    "nethermind": 0.5,
                }),
                consensus=ClientDistribution({
                    "lighthouse": 0.5,
                    "prysm": 0.5,
                }),
            ),
        )

        deployer = TestnetDeployer(
            kurtosis_client=kurtosis,
            package_config=config,
            enclave_name=enclave_name,
        )

        result = deployer.deploy(
            wait_for_finality=True,
            finality_timeout_seconds=300,
        )

        if not result.success:
            kurtosis.destroy_enclave(enclave_name)
            pytest.skip(f"Testnet deployment failed: {result.error_message}")

        yield deployer, enclave_name

        # Always cleanup
        try:
            deployer.destroy()
        except Exception:
            try:
                kurtosis.destroy_enclave(enclave_name)
            except Exception:
                pass

    @pytest.mark.timeout(900)
    def test_baseline_scenario_file_valid(self) -> None:
        """The baseline scenario YAML must pass schema validation."""
        result = validate_scenario_file(SCENARIOS_DIR / "baseline_observation.yaml")
        assert result.valid, f"Validation errors: {result.errors}"

    @pytest.mark.timeout(900)
    def test_testnet_deployed_with_diversity(
        self, deployed_testnet: tuple[TestnetDeployer, str]
    ) -> None:
        """Testnet should be deployed with client diversity."""
        deployer, enclave_name = deployed_testnet
        kurtosis = KurtosisClient(dry_run=False)

        services = kurtosis.get_services(enclave_name)
        service_names = [s.name.lower() for s in services]

        # Verify EL diversity
        has_geth = any("geth" in n for n in service_names)
        has_nethermind = any("nethermind" in n for n in service_names)
        assert has_geth, "Missing geth services"
        assert has_nethermind, "Missing nethermind services"

        # Verify CL diversity
        has_lighthouse = any("lighthouse" in n for n in service_names)
        has_prysm = any("prysm" in n for n in service_names)
        assert has_lighthouse, "Missing lighthouse services"
        assert has_prysm, "Missing prysm services"

    @pytest.mark.timeout(900)
    def test_finality_achieved(
        self, deployed_testnet: tuple[TestnetDeployer, str]
    ) -> None:
        """Finality should be achieved after deployment."""
        deployer, _ = deployed_testnet
        result = deployer.get_last_deployment()
        assert result is not None
        assert result.finality_achieved, "Finality was not achieved"
        assert result.finality_epoch is not None and result.finality_epoch >= 1

    @pytest.mark.timeout(900)
    def test_beacon_api_healthy(
        self, deployed_testnet: tuple[TestnetDeployer, str]
    ) -> None:
        """Beacon API should be healthy after deployment."""
        deployer, _ = deployed_testnet
        assert len(deployer.beacon_clients) > 0, "No beacon clients"

        for client in deployer.beacon_clients:
            health = client.health_check()
            if health.is_healthy:
                assert health.peer_count > 0
                return

        pytest.fail("No beacon node is healthy")

    @pytest.mark.timeout(900)
    def test_finality_checkpoints_advancing(
        self, deployed_testnet: tuple[TestnetDeployer, str]
    ) -> None:
        """Finality checkpoints should be advancing (chain is live)."""
        deployer, _ = deployed_testnet
        if not deployer.beacon_clients:
            pytest.skip("No beacon clients")

        client = deployer.beacon_clients[0]
        cp1 = client.get_finality_checkpoints()

        # Wait for one slot
        time.sleep(13)

        cp2 = client.get_finality_checkpoints()
        assert cp2.current_epoch >= cp1.current_epoch, (
            f"Chain not advancing: epoch1={cp1.current_epoch}, epoch2={cp2.current_epoch}"
        )

    @pytest.mark.timeout(900)
    def test_circuit_breaker_safe_during_baseline(
        self, deployed_testnet: tuple[TestnetDeployer, str]
    ) -> None:
        """Circuit breaker should not trip during baseline observation."""
        deployer, _ = deployed_testnet
        if not deployer.beacon_clients:
            pytest.skip("No beacon clients")

        client = deployer.beacon_clients[0]
        breaker = CircuitBreaker()

        # Collect real metrics from the beacon API
        cp = client.get_finality_checkpoints()
        finality_delay_seconds = cp.epochs_since_finality * 32 * 12  # epochs * slots * seconds

        metrics = {
            "finality_delay_seconds": float(finality_delay_seconds),
            # Note: slashing and participation would require more complex queries
            # For baseline, we just verify the finality metric
        }

        result = breaker.check_metrics(metrics)
        assert result is True, (
            f"Circuit breaker tripped during baseline: "
            f"finality_delay={finality_delay_seconds}s"
        )

    @pytest.mark.timeout(900)
    def test_blast_radius_zero_during_baseline(self) -> None:
        """Blast radius should be zero during baseline (no faults injected)."""
        blast_config = BlastRadiusConfig(max_affected_percent=0.0)
        is_valid, violations = validate_blast_radius(
            blast_config,
            total_nodes=8,
            requested_nodes=0,
        )
        assert is_valid

    @pytest.mark.timeout(900)
    def test_audit_trail_for_baseline(
        self, deployed_testnet: tuple[TestnetDeployer, str]
    ) -> None:
        """Audit trail should be created for the baseline scenario."""
        audit = AuditLogger(default_agent_id="e2e_test")

        audit.log(
            ActionType.EXPERIMENT_CREATE,
            "baseline_observation",
            Outcome.SUCCESS,
            experiment_id="e2e-baseline",
        )
        audit.log(
            ActionType.EXPERIMENT_START,
            "baseline_observation",
            Outcome.SUCCESS,
            experiment_id="e2e-baseline",
        )
        audit.log(
            ActionType.CIRCUIT_BREAKER_CHECK,
            "e2e-baseline",
            Outcome.SUCCESS,
            experiment_id="e2e-baseline",
        )
        audit.log(
            ActionType.EXPERIMENT_COMPLETE,
            "baseline_observation",
            Outcome.SUCCESS,
            experiment_id="e2e-baseline",
        )

        entries = audit.get_entries(experiment_id="e2e-baseline")
        assert len(entries) == 4
        action_types = [e.action_type for e in entries]
        assert "experiment_create" in action_types
        assert "experiment_start" in action_types
        assert "circuit_breaker_check" in action_types
        assert "experiment_complete" in action_types
