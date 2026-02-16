"""Real Kurtosis integration tests.

These tests deploy REAL Kurtosis enclaves with the ethereum-package.
They require Docker and Kurtosis to be running. Tests are skipped
if infrastructure is not available.

WARNING: These tests create real containers. Always cleanup.
"""

from __future__ import annotations

import time
import uuid

import pytest

from chaoswopr.infrastructure.testnet.beacon_api import BeaconAPIClient
from chaoswopr.infrastructure.testnet.client_config import ClientConfig, ClientDistribution
from chaoswopr.infrastructure.testnet.deployer import (
    DeploymentState,
    TestnetDeployer,
)
from chaoswopr.infrastructure.testnet.ethereum_package import EthereumPackageConfig
from chaoswopr.infrastructure.testnet.kurtosis_client import (
    EnclaveState,
    KurtosisClient,
)

from .conftest import require_docker, require_kurtosis, require_kurtosis_engine


@require_kurtosis
class TestKurtosisAvailability:
    """Verify Kurtosis infrastructure prerequisites."""

    def test_kurtosis_cli_available(self) -> None:
        """Kurtosis CLI must be installed and runnable."""
        client = KurtosisClient(dry_run=False)
        assert client.is_available(), "Kurtosis CLI not available"

    @require_docker
    def test_docker_available(self) -> None:
        """Docker must be running for Kurtosis to work."""
        import subprocess

        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, "Docker not running"

    @require_kurtosis_engine
    def test_kurtosis_engine_running(self) -> None:
        """Kurtosis engine must be running."""
        client = KurtosisClient(dry_run=False)
        assert client.is_engine_running(), "Kurtosis engine not running"


@require_kurtosis_engine
class TestRealEnclaveOperations:
    """Test real Kurtosis enclave lifecycle without deploying ethereum-package."""

    def test_create_and_destroy_enclave(self, kurtosis_client: KurtosisClient) -> None:
        """Create an empty enclave and destroy it."""
        name = f"chaoswopr-test-{uuid.uuid4().hex[:8]}"
        try:
            info = kurtosis_client.create_enclave(name)
            assert info.name == name
            assert info.state == EnclaveState.RUNNING
        finally:
            kurtosis_client.destroy_enclave(name)

    def test_list_enclaves(self, kurtosis_enclave: str, kurtosis_client: KurtosisClient) -> None:
        """List enclaves should include the created enclave."""
        enclaves = kurtosis_client.list_enclaves()
        names = [e.name for e in enclaves]
        assert kurtosis_enclave in names, (
            f"Expected '{kurtosis_enclave}' in enclaves, got {names}"
        )

    def test_enclave_info(self, kurtosis_enclave: str, kurtosis_client: KurtosisClient) -> None:
        """Get enclave info for a running enclave."""
        info = kurtosis_client.get_enclave_info(kurtosis_enclave)
        assert info is not None
        assert info.name == kurtosis_enclave

    def test_enclave_info_nonexistent(self, kurtosis_client: KurtosisClient) -> None:
        """Get enclave info for a nonexistent enclave returns None."""
        info = kurtosis_client.get_enclave_info("nonexistent-enclave-xyz")
        assert info is None


@require_kurtosis_engine
class TestRealTestnetDeployment:
    """Test real testnet deployment with ethereum-package.

    These tests deploy actual Ethereum testnets with minimal node counts.
    They are slow (1-5 minutes per test) and resource-intensive.
    """

    @pytest.fixture
    def minimal_config(self) -> EthereumPackageConfig:
        """Create a minimal 4-node testnet config for fast deployment.

        Note: Using nethermind-only to avoid geth blobSchedule bug in
        ethereum-genesis-generator v3.3.7. Geth requires v5.2.4+.
        """
        return EthereumPackageConfig(
            client_config=ClientConfig(
                node_count=4,
                execution=ClientDistribution({"nethermind": 1.0}),  # Avoid geth blobSchedule bug
                consensus=ClientDistribution({"lighthouse": 0.5, "prysm": 0.5}),
            ),
            spammer_config=EthereumPackageConfig().spammer_config,
        )

    @pytest.fixture
    def deployed_testnet(
        self,
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
        minimal_config: EthereumPackageConfig,
    ):
        """Deploy a minimal testnet and yield it for testing.

        Always tears down after the test, even on failure.
        """
        deployer = TestnetDeployer(
            kurtosis_client=kurtosis_client,
            package_config=minimal_config,
            enclave_name=unique_enclave_name,
        )

        result = deployer.deploy(
            wait_for_finality=False,
        )

        yield deployer, result

        # Always cleanup
        try:
            deployer.destroy()
        except Exception:
            # Force cleanup via kurtosis client
            try:
                kurtosis_client.destroy_enclave(unique_enclave_name)
            except Exception:
                pass

    @pytest.mark.timeout(600)
    def test_deploy_minimal_testnet(
        self, deployed_testnet: tuple[TestnetDeployer, any]
    ) -> None:
        """Deploy a minimal 4-node testnet and verify it starts."""
        deployer, result = deployed_testnet

        assert result.success, f"Deployment failed: {result.error_message}"
        assert result.state == DeploymentState.RUNNING
        assert deployer.state == DeploymentState.RUNNING

    @pytest.mark.timeout(600)
    def test_enclave_has_services(
        self,
        deployed_testnet: tuple[TestnetDeployer, any],
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ) -> None:
        """Deployed enclave should have running services."""
        deployer, result = deployed_testnet
        if not result.success:
            pytest.skip(f"Deployment failed: {result.error_message}")

        services = kurtosis_client.get_services(unique_enclave_name)
        assert len(services) > 0, "No services found in enclave"

        # Verify we have both EL and CL services
        service_names = [s.name for s in services]
        has_el = any("el-" in name or "geth" in name or "nethermind" in name for name in service_names)
        has_cl = any("cl-" in name or "lighthouse" in name or "prysm" in name for name in service_names)

        assert has_el, f"No EL services found in {service_names}"
        assert has_cl, f"No CL services found in {service_names}"

    @pytest.mark.timeout(600)
    def test_beacon_node_discoverable(
        self,
        deployed_testnet: tuple[TestnetDeployer, any],
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ) -> None:
        """Beacon node endpoints should be discoverable from enclave."""
        deployer, result = deployed_testnet
        if not result.success:
            pytest.skip(f"Deployment failed: {result.error_message}")

        beacon_services = kurtosis_client.find_beacon_services(unique_enclave_name)
        assert len(beacon_services) > 0, "No beacon services found"

    @pytest.mark.timeout(600)
    def test_beacon_api_reachable(
        self,
        deployed_testnet: tuple[TestnetDeployer, any],
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ) -> None:
        """Beacon node API should be reachable after deployment."""
        deployer, result = deployed_testnet
        if not result.success:
            pytest.skip(f"Deployment failed: {result.error_message}")

        beacon_services = kurtosis_client.find_beacon_services(unique_enclave_name)
        if not beacon_services:
            pytest.skip("No beacon services found")

        # Try to reach at least one beacon node
        for svc in beacon_services:
            for port_name in ["http", "beacon", "rest", "api"]:
                url = svc.get_url(port_name)
                if url:
                    client = BeaconAPIClient(base_url=url, timeout=30.0)
                    ready = client.wait_for_node_ready(
                        timeout_seconds=120.0,
                        poll_interval=5.0,
                    )
                    if ready:
                        health = client.health_check()
                        assert health.is_healthy, f"Beacon node at {url} not healthy"
                        client.close()
                        return

        pytest.fail("No beacon node became reachable")

    @pytest.mark.timeout(600)
    def test_testnet_teardown(self, kurtosis_client: KurtosisClient) -> None:
        """Verify clean teardown of a deployed testnet."""
        name = f"chaoswopr-test-{uuid.uuid4().hex[:8]}"
        deployer = TestnetDeployer(
            kurtosis_client=kurtosis_client,
            package_config=EthereumPackageConfig(
                client_config=ClientConfig(
                    node_count=4,
                    execution=ClientDistribution({"geth": 1.0}),
                    consensus=ClientDistribution({"lighthouse": 1.0}),
                ),
            ),
            enclave_name=name,
        )

        try:
            result = deployer.deploy(wait_for_finality=False)
            if result.success:
                assert deployer.destroy() is True
                assert deployer.state == DeploymentState.DESTROYED

                # Verify enclave is gone
                info = kurtosis_client.get_enclave_info(name)
                assert info is None, "Enclave should not exist after teardown"
        finally:
            # Double-ensure cleanup
            try:
                kurtosis_client.destroy_enclave(name)
            except Exception:
                pass


@require_kurtosis_engine
class TestFinalityDetection:
    """Test real finality detection using the Beacon API.

    These tests deploy a testnet and wait for actual finality.
    Finality typically occurs after 2-3 epochs (64-96 seconds on a
    12-second slot time testnet).
    """

    @pytest.mark.timeout(600)
    def test_finality_with_minimal_testnet(
        self,
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ) -> None:
        """Deploy a testnet and verify finality is achieved.

        Note: Using nethermind to avoid geth blobSchedule bug.
        """
        config = EthereumPackageConfig(
            client_config=ClientConfig(
                node_count=4,
                execution=ClientDistribution({"nethermind": 1.0}),  # Avoid geth bug
                consensus=ClientDistribution({"lighthouse": 1.0}),
            ),
        )

        deployer = TestnetDeployer(
            kurtosis_client=kurtosis_client,
            package_config=config,
            enclave_name=unique_enclave_name,
        )

        try:
            result = deployer.deploy(
                wait_for_finality=True,
                finality_timeout_seconds=300,
            )

            assert result.success, f"Deployment failed: {result.error_message}"
            assert result.finality_achieved, (
                f"Finality not achieved. Wait={result.finality_wait_seconds:.1f}s, "
                f"error={result.error_message}"
            )
            assert result.finality_epoch is not None
            assert result.finality_epoch >= 1
        finally:
            try:
                deployer.destroy()
            except Exception:
                kurtosis_client.destroy_enclave(unique_enclave_name)
