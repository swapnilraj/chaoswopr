"""Real chaos injection integration tests.

These tests deploy REAL Kurtosis enclaves and apply actual chaos faults.
They require Docker and Kurtosis to be running. Tests are skipped
if infrastructure is not available.

WARNING: These tests create real containers and modify their network configuration.
Always cleanup after tests.
"""

from __future__ import annotations

import time
import uuid

import pytest

from chaoswopr.chaos.cleanup import CleanupDaemon
from chaoswopr.chaos.network_faults import (
    FaultType,
    NetworkFault,
    NetworkFaultInjector,
)
from chaoswopr.chaos.partition import (
    Island,
    NetworkPartition,
    PartitionMode,
    PartitionSimulator,
)
from chaoswopr.chaos.safe_injector import (
    RolloutConfig,
    SafeFaultInjector,
)
from chaoswopr.infrastructure.testnet.client_config import (
    ClientConfig,
    ClientDistribution,
)
from chaoswopr.infrastructure.testnet.deployer import TestnetDeployer
from chaoswopr.infrastructure.testnet.ethereum_package import EthereumPackageConfig
from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient
from chaoswopr.safety.blast_radius import BlastRadiusConfig
from chaoswopr.safety.circuit_breaker import CircuitBreaker

from .conftest import require_docker, require_kurtosis_engine


@require_kurtosis_engine
class TestRealNetworkFaults:
    """Test network fault injection on real containers."""

    @pytest.fixture
    def minimal_testnet(
        self,
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ):
        """Deploy a minimal 4-node testnet for fault injection testing."""
        config = EthereumPackageConfig(
            client_config=ClientConfig(
                node_count=4,
                execution=ClientDistribution({"nethermind": 1.0}),
                consensus=ClientDistribution({"prysm": 1.0}),
            ),
        )

        deployer = TestnetDeployer(
            kurtosis_client=kurtosis_client,
            package_config=config,
            enclave_name=unique_enclave_name,
        )

        result = deployer.deploy(wait_for_finality=False)

        yield deployer, result

        # Cleanup
        try:
            deployer.destroy()
        except Exception:
            try:
                kurtosis_client.destroy_enclave(unique_enclave_name)
            except Exception:
                pass

    @pytest.mark.timeout(600)
    def test_inject_packet_loss_real(
        self,
        minimal_testnet: tuple[TestnetDeployer, any],
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ) -> None:
        """Inject real packet loss to containers."""
        deployer, result = minimal_testnet
        if not result.success:
            pytest.skip(f"Testnet deployment failed: {result.error_message}")

        # Get service containers - use EL (execution layer) containers as they have package managers
        services = kurtosis_client.get_services(unique_enclave_name)
        if len(services) < 2:
            pytest.skip("Not enough services for testing")

        # Filter for EL containers (they start with "el-" and have package managers for installing tc)
        el_services = [s for s in services if s.name.startswith("el-")]
        if len(el_services) < 2:
            pytest.skip("Not enough EL services for testing")

        # Get container names (just the service names, not full container IDs)
        container_names = [s.name for s in el_services[:2]]  # Test with 2 EL nodes

        # Create network fault injector
        injector = NetworkFaultInjector(dry_run=False)

        try:
            # Inject 20% packet loss
            fault = NetworkFault(
                fault_type=FaultType.PACKET_LOSS,
                target_containers=container_names,
                packet_loss_percent=20.0,
            )

            fault_id = injector.inject(fault)
            assert fault_id is not None
            assert fault_id.startswith("net-")

            # Wait a bit for fault to take effect
            time.sleep(2)

            # Verify fault is active
            active = injector.list_active()
            assert fault_id in active

            # Remove fault
            removed = injector.remove(fault_id)
            assert removed is True

            # Verify removal
            active_after = injector.list_active()
            assert fault_id not in active_after

        finally:
            # Ensure cleanup
            injector.remove_all()

    @pytest.mark.timeout(600)
    def test_inject_latency_real(
        self,
        minimal_testnet: tuple[TestnetDeployer, any],
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ) -> None:
        """Inject real network latency to containers."""
        deployer, result = minimal_testnet
        if not result.success:
            pytest.skip(f"Testnet deployment failed: {result.error_message}")

        services = kurtosis_client.get_services(unique_enclave_name)
        el_services = [s for s in services if s.name.startswith("el-")]
        if len(el_services) < 1:
            pytest.skip("No EL services available")

        container_names = [el_services[0].name]

        injector = NetworkFaultInjector(dry_run=False)

        try:
            # Inject 100ms latency
            fault_id = injector.inject_latency(
                containers=container_names,
                latency_ms=100,
                jitter_ms=10,
            )

            assert fault_id is not None
            time.sleep(2)

            # Verify and cleanup
            assert injector.remove(fault_id) is True

        finally:
            injector.remove_all()


@require_kurtosis_engine
class TestRealNetworkPartitions:
    """Test network partition on real testnet."""

    @pytest.fixture
    def testnet_for_partition(
        self,
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ):
        """Deploy a 4-node testnet for partition testing."""
        config = EthereumPackageConfig(
            client_config=ClientConfig(
                node_count=4,
                execution=ClientDistribution({"nethermind": 1.0}),
                consensus=ClientDistribution({"prysm": 1.0}),
            ),
        )

        deployer = TestnetDeployer(
            kurtosis_client=kurtosis_client,
            package_config=config,
            enclave_name=unique_enclave_name,
        )

        result = deployer.deploy(wait_for_finality=False)

        yield deployer, result

        try:
            deployer.destroy()
        except Exception:
            try:
                kurtosis_client.destroy_enclave(unique_enclave_name)
            except Exception:
                pass

    @pytest.mark.timeout(600)
    def test_create_two_island_partition_real(
        self,
        testnet_for_partition: tuple[TestnetDeployer, any],
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ) -> None:
        """Create a real two-island network partition."""
        deployer, result = testnet_for_partition
        if not result.success:
            pytest.skip(f"Testnet deployment failed: {result.error_message}")

        services = kurtosis_client.get_services(unique_enclave_name)
        if len(services) < 4:
            pytest.skip("Need at least 4 services for partition test")

        # Split into majority (3 nodes) and minority (1 node)
        service_names = [s.name for s in services]
        majority = service_names[:3]
        minority = service_names[3:]

        simulator = PartitionSimulator(dry_run=False)

        try:
            # Create clean partition
            partition = NetworkPartition(
                mode=PartitionMode.CLEAN,
                islands=[
                    Island(name="majority", containers=majority),
                    Island(name="minority", containers=minority),
                ],
            )

            partition_id = simulator.create_partition(partition)
            assert partition_id is not None
            assert partition_id.startswith("partition-")

            # Wait for partition to take effect
            time.sleep(2)

            # Get topology
            topology = simulator.get_partition_topology(partition_id)
            assert topology is not None
            assert topology["summary"]["num_islands"] == 2
            assert topology["summary"]["total_nodes"] == 4

            # Remove partition
            removed = simulator.remove_partition(partition_id)
            assert removed is True

        finally:
            simulator.remove_all()


@require_kurtosis_engine
class TestRealSafetyIntegration:
    """Test safety wrapper with real faults."""

    @pytest.fixture
    def testnet_for_safety(
        self,
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ):
        """Deploy testnet for safety testing."""
        config = EthereumPackageConfig(
            client_config=ClientConfig(
                node_count=4,
                execution=ClientDistribution({"nethermind": 1.0}),
                consensus=ClientDistribution({"prysm": 1.0}),
            ),
        )

        deployer = TestnetDeployer(
            kurtosis_client=kurtosis_client,
            package_config=config,
            enclave_name=unique_enclave_name,
        )

        result = deployer.deploy(wait_for_finality=False)

        yield deployer, result

        try:
            deployer.destroy()
        except Exception:
            try:
                kurtosis_client.destroy_enclave(unique_enclave_name)
            except Exception:
                pass

    @pytest.mark.timeout(600)
    def test_safe_fault_injection_real(
        self,
        testnet_for_safety: tuple[TestnetDeployer, any],
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ) -> None:
        """Test safe fault injection with real testnet."""
        deployer, result = testnet_for_safety
        if not result.success:
            pytest.skip(f"Testnet deployment failed: {result.error_message}")

        services = kurtosis_client.get_services(unique_enclave_name)
        if len(services) < 2:
            pytest.skip("Not enough services")

        # Create safety components
        circuit_breaker = CircuitBreaker()
        circuit_breaker.arm()

        blast_radius_config = BlastRadiusConfig(max_affected_percent=33.0)

        rollout_config = RolloutConfig(enabled=False)  # Disable for testing

        safe_injector = SafeFaultInjector(
            circuit_breaker=circuit_breaker,
            blast_radius_config=blast_radius_config,
            total_nodes=4,
            rollout_config=rollout_config,
            dry_run=False,
        )

        try:
            # Inject fault through safety wrapper
            fault = NetworkFault(
                fault_type=FaultType.PACKET_LOSS,
                target_containers=[services[0].name],
                packet_loss_percent=10.0,
            )

            result = safe_injector.inject_network_fault(fault)
            assert result.success is True
            assert result.fault_id is not None

            time.sleep(2)

            # Verify impact calculation
            impact = safe_injector.get_current_impact()
            assert impact > 0.0

            # Remove fault
            removed = safe_injector.remove_fault(result.fault_id)
            assert removed is True

        finally:
            safe_injector.remove_all()


@require_kurtosis_engine
class TestRealCleanupDaemon:
    """Test cleanup daemon with real faults."""

    @pytest.fixture
    def testnet_for_cleanup(
        self,
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ):
        """Deploy testnet for cleanup testing."""
        config = EthereumPackageConfig(
            client_config=ClientConfig(
                node_count=4,
                execution=ClientDistribution({"nethermind": 1.0}),
                consensus=ClientDistribution({"prysm": 1.0}),
            ),
        )

        deployer = TestnetDeployer(
            kurtosis_client=kurtosis_client,
            package_config=config,
            enclave_name=unique_enclave_name,
        )

        result = deployer.deploy(wait_for_finality=False)

        yield deployer, result

        try:
            deployer.destroy()
        except Exception:
            try:
                kurtosis_client.destroy_enclave(unique_enclave_name)
            except Exception:
                pass

    @pytest.mark.timeout(600)
    def test_cleanup_daemon_real(
        self,
        testnet_for_cleanup: tuple[TestnetDeployer, any],
        kurtosis_client: KurtosisClient,
        unique_enclave_name: str,
    ) -> None:
        """Test cleanup daemon with real faults."""
        deployer, result = testnet_for_cleanup
        if not result.success:
            pytest.skip(f"Testnet deployment failed: {result.error_message}")

        services = kurtosis_client.get_services(unique_enclave_name)
        if len(services) < 2:
            pytest.skip("Not enough services")

        # Create injectors
        network_injector = NetworkFaultInjector(dry_run=False)
        node_injector = NetworkFaultInjector(dry_run=False)  # Placeholder
        partition_simulator = PartitionSimulator(dry_run=False)

        # Create cleanup daemon
        daemon = CleanupDaemon(
            network_injector=network_injector,
            node_injector=node_injector,
            partition_simulator=partition_simulator,
            heartbeat_timeout_seconds=60,
        )

        try:
            daemon.start()

            # Inject some faults
            fault = NetworkFault(
                fault_type=FaultType.PACKET_LOSS,
                target_containers=[services[0].name],
                packet_loss_percent=10.0,
            )
            fault_id = network_injector.inject(fault)
            daemon.register_fault(fault_id, "network")

            # Update heartbeat
            daemon.heartbeat()

            # Check status
            status = daemon.get_status()
            assert status["running"] is True
            assert status["orchestrator_alive"] is True
            assert status["active_fault_count"] == 1

            # Cleanup all
            removed = daemon.cleanup_all()
            assert removed >= 1

            # Verify cleanup
            final_status = daemon.get_status()
            assert final_status["active_fault_count"] == 0

            daemon.stop()

        finally:
            # Ensure cleanup
            network_injector.remove_all()
            partition_simulator.remove_all()
