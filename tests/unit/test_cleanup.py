"""Unit tests for fault cleanup daemon."""

from __future__ import annotations

import time

import pytest

from chaoswopr.chaos.cleanup import (
    CleanupDaemon,
    FaultRegistry,
    FaultRegistryEntry,
    OrchestratorHeartbeat,
)
from chaoswopr.chaos.network_faults import NetworkFaultInjector
from chaoswopr.chaos.node_faults import NodeFaultInjector
from chaoswopr.chaos.partition import PartitionSimulator


class TestOrchestratorHeartbeat:
    """Test OrchestratorHeartbeat."""

    def test_initial_state(self) -> None:
        """Initial heartbeat is alive."""
        heartbeat = OrchestratorHeartbeat(timeout_seconds=60)
        assert heartbeat.is_alive is True
        assert heartbeat.check() is True

    def test_update_heartbeat(self) -> None:
        """Update heartbeat timestamp."""
        heartbeat = OrchestratorHeartbeat(timeout_seconds=60)
        initial_time = heartbeat.last_heartbeat

        time.sleep(0.1)
        heartbeat.update()

        assert heartbeat.last_heartbeat > initial_time
        assert heartbeat.is_alive is True

    def test_heartbeat_timeout(self) -> None:
        """Heartbeat times out after timeout period."""
        heartbeat = OrchestratorHeartbeat(timeout_seconds=1)
        heartbeat.last_heartbeat = time.time() - 2  # 2 seconds ago

        assert heartbeat.check() is False
        assert heartbeat.is_alive is False

    def test_time_since_last_heartbeat(self) -> None:
        """Calculate time since last heartbeat."""
        heartbeat = OrchestratorHeartbeat()
        heartbeat.last_heartbeat = time.time() - 5

        elapsed = heartbeat.time_since_last_heartbeat()
        assert elapsed >= 5.0
        assert elapsed < 6.0  # Allow small delta


class TestFaultRegistry:
    """Test FaultRegistry."""

    @pytest.fixture
    def registry(self) -> FaultRegistry:
        """Create a fault registry."""
        return FaultRegistry()

    def test_register_fault(self, registry: FaultRegistry) -> None:
        """Register a fault."""
        registry.register("fault-1", "network")
        assert registry.count() == 1

    def test_unregister_fault(self, registry: FaultRegistry) -> None:
        """Unregister a fault."""
        registry.register("fault-1", "network")
        assert registry.unregister("fault-1") is True
        assert registry.count() == 0

    def test_unregister_nonexistent_fault(
        self, registry: FaultRegistry
    ) -> None:
        """Unregister nonexistent fault returns False."""
        assert registry.unregister("nonexistent") is False

    def test_list_all(self, registry: FaultRegistry) -> None:
        """List all registered faults."""
        registry.register("fault-1", "network")
        registry.register("fault-2", "node")

        faults = registry.list_all()
        assert len(faults) == 2
        assert all(isinstance(f, FaultRegistryEntry) for f in faults)

    def test_count(self, registry: FaultRegistry) -> None:
        """Count registered faults."""
        assert registry.count() == 0

        registry.register("fault-1", "network")
        registry.register("fault-2", "node")
        assert registry.count() == 2

    def test_count_by_type(self, registry: FaultRegistry) -> None:
        """Count faults by type."""
        registry.register("fault-1", "network")
        registry.register("fault-2", "network")
        registry.register("fault-3", "node")

        counts = registry.count_by_type()
        assert counts["network"] == 2
        assert counts["node"] == 1

    def test_clear(self, registry: FaultRegistry) -> None:
        """Clear all faults."""
        registry.register("fault-1", "network")
        registry.register("fault-2", "node")

        cleared = registry.clear()
        assert cleared == 2
        assert registry.count() == 0

    def test_register_with_metadata(self, registry: FaultRegistry) -> None:
        """Register fault with metadata."""
        registry.register(
            "fault-1", "network", metadata={"target": "container-1"}
        )

        faults = registry.list_all()
        assert faults[0].metadata["target"] == "container-1"


class TestCleanupDaemon:
    """Test CleanupDaemon."""

    @pytest.fixture
    def network_injector(self) -> NetworkFaultInjector:
        """Create network fault injector."""
        return NetworkFaultInjector(dry_run=True)

    @pytest.fixture
    def node_injector(self) -> NodeFaultInjector:
        """Create node fault injector."""
        return NodeFaultInjector(dry_run=True)

    @pytest.fixture
    def partition_simulator(self) -> PartitionSimulator:
        """Create partition simulator."""
        return PartitionSimulator(dry_run=True)

    @pytest.fixture
    def daemon(
        self,
        network_injector: NetworkFaultInjector,
        node_injector: NodeFaultInjector,
        partition_simulator: PartitionSimulator,
    ) -> CleanupDaemon:
        """Create cleanup daemon."""
        return CleanupDaemon(
            network_injector=network_injector,
            node_injector=node_injector,
            partition_simulator=partition_simulator,
            heartbeat_timeout_seconds=60,
            check_interval_seconds=10,
        )

    def test_initial_state(self, daemon: CleanupDaemon) -> None:
        """Daemon starts in stopped state."""
        assert daemon.is_running() is False

    def test_start_stop(self, daemon: CleanupDaemon) -> None:
        """Start and stop daemon."""
        daemon.start()
        assert daemon.is_running() is True

        daemon.stop()
        assert daemon.is_running() is False

    def test_heartbeat(self, daemon: CleanupDaemon) -> None:
        """Update orchestrator heartbeat."""
        daemon.start()

        time.sleep(0.1)
        daemon.heartbeat()
        status = daemon.get_status()

        assert status["orchestrator_alive"] is True
        # After heartbeat, time_since_heartbeat should be very small (< 1 second)
        assert status["time_since_heartbeat"] < 1.0

    def test_register_fault(self, daemon: CleanupDaemon) -> None:
        """Register fault for tracking."""
        daemon.register_fault("fault-1", "network")

        status = daemon.get_status()
        assert status["active_fault_count"] == 1
        assert status["faults_by_type"]["network"] == 1

    def test_unregister_fault(self, daemon: CleanupDaemon) -> None:
        """Unregister fault."""
        daemon.register_fault("fault-1", "network")
        assert daemon.unregister_fault("fault-1") is True

        status = daemon.get_status()
        assert status["active_fault_count"] == 0

    def test_get_status(self, daemon: CleanupDaemon) -> None:
        """Get daemon status."""
        daemon.start()
        daemon.register_fault("fault-1", "network")
        daemon.register_fault("fault-2", "node")

        status = daemon.get_status()
        assert status["running"] is True
        assert status["orchestrator_alive"] is True
        assert status["active_fault_count"] == 2
        assert status["heartbeat_timeout"] == 60
        assert status["check_interval"] == 10

    def test_cleanup_all(
        self,
        daemon: CleanupDaemon,
        network_injector: NetworkFaultInjector,
        node_injector: NodeFaultInjector,
    ) -> None:
        """Cleanup all faults."""
        # Inject some faults
        from chaoswopr.chaos.network_faults import FaultType, NetworkFault
        from chaoswopr.chaos.node_faults import NodeFault, NodeFaultType

        net_fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["c1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        network_injector.inject(net_fault)

        node_fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={"app": "test"},
            dry_run=True,
        )
        node_injector.inject(node_fault)

        # Register in daemon
        daemon.register_fault("net-1", "network")
        daemon.register_fault("node-1", "node")

        # Cleanup
        removed = daemon.cleanup_all()
        assert removed == 2

        # Verify cleanup
        status = daemon.get_status()
        assert status["active_fault_count"] == 0

    def test_check_and_cleanup_alive(self, daemon: CleanupDaemon) -> None:
        """Check and cleanup when orchestrator is alive."""
        daemon.start()
        daemon.heartbeat()

        result = daemon.check_and_cleanup()
        assert result["orchestrator_alive"] is True
        assert result["cleanup_triggered"] is False
        assert result["faults_removed"] == 0

    def test_check_and_cleanup_dead(
        self,
        daemon: CleanupDaemon,
        network_injector: NetworkFaultInjector,
    ) -> None:
        """Check and cleanup when orchestrator is dead."""
        from chaoswopr.chaos.network_faults import FaultType, NetworkFault

        daemon.start()

        # Inject fault
        net_fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["c1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        network_injector.inject(net_fault)
        daemon.register_fault("net-1", "network")

        # Simulate heartbeat timeout
        daemon._heartbeat.last_heartbeat = time.time() - 120  # 2 minutes ago
        daemon._heartbeat.timeout_seconds = 60  # 1 minute timeout

        result = daemon.check_and_cleanup()
        assert result["orchestrator_alive"] is False
        assert result["cleanup_triggered"] is True
        assert result["faults_removed"] >= 1

    def test_multiple_fault_types(self, daemon: CleanupDaemon) -> None:
        """Track multiple fault types."""
        daemon.register_fault("net-1", "network")
        daemon.register_fault("net-2", "network")
        daemon.register_fault("node-1", "node")
        daemon.register_fault("part-1", "partition")

        status = daemon.get_status()
        assert status["active_fault_count"] == 4
        assert status["faults_by_type"]["network"] == 2
        assert status["faults_by_type"]["node"] == 1
        assert status["faults_by_type"]["partition"] == 1
