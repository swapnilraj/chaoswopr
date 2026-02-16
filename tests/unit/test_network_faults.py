"""Unit tests for network fault injection."""

from __future__ import annotations

import pytest

from chaoswopr.chaos.network_faults import (
    FaultType,
    NetworkFault,
    NetworkFaultInjector,
)


class TestNetworkFault:
    """Test NetworkFault configuration."""

    def test_valid_packet_loss_fault(self) -> None:
        """Valid packet loss fault passes validation."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
        )
        errors = fault.validate()
        assert errors == []

    def test_valid_latency_fault(self) -> None:
        """Valid latency fault passes validation."""
        fault = NetworkFault(
            fault_type=FaultType.LATENCY,
            target_containers=["container-1", "container-2"],
            latency_ms=100,
            jitter_ms=10,
        )
        errors = fault.validate()
        assert errors == []

    def test_empty_target_containers(self) -> None:
        """Empty target containers fails validation."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=[],
            packet_loss_percent=20.0,
        )
        errors = fault.validate()
        assert "target_containers cannot be empty" in errors

    def test_invalid_packet_loss_percent(self) -> None:
        """Invalid packet loss percentage fails validation."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=150.0,
        )
        errors = fault.validate()
        assert any("packet_loss_percent" in e for e in errors)

    def test_invalid_latency_ms(self) -> None:
        """Invalid latency fails validation."""
        fault = NetworkFault(
            fault_type=FaultType.LATENCY,
            target_containers=["container-1"],
            latency_ms=15000,
        )
        errors = fault.validate()
        assert any("latency_ms" in e for e in errors)

    def test_invalid_jitter_ms(self) -> None:
        """Jitter greater than latency fails validation."""
        fault = NetworkFault(
            fault_type=FaultType.LATENCY,
            target_containers=["container-1"],
            latency_ms=100,
            jitter_ms=150,
        )
        errors = fault.validate()
        assert any("jitter_ms" in e for e in errors)

    def test_to_dict(self) -> None:
        """to_dict returns proper dictionary."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
        )
        data = fault.to_dict()
        assert data["fault_type"] == "packet_loss"
        assert data["target_containers"] == ["container-1"]
        assert data["packet_loss_percent"] == 20.0


class TestNetworkFaultInjector:
    """Test NetworkFaultInjector."""

    @pytest.fixture
    def injector(self) -> NetworkFaultInjector:
        """Create a network fault injector in dry-run mode."""
        return NetworkFaultInjector(dry_run=True)

    def test_inject_valid_fault(self, injector: NetworkFaultInjector) -> None:
        """Inject valid fault returns fault ID."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        fault_id = injector.inject(fault)
        assert fault_id.startswith("net-")
        assert len(fault_id) == 12  # "net-" + 8 hex chars

    def test_inject_invalid_fault_raises(
        self, injector: NetworkFaultInjector
    ) -> None:
        """Inject invalid fault raises ValueError."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=[],
            packet_loss_percent=20.0,
        )
        with pytest.raises(ValueError, match="Invalid fault configuration"):
            injector.inject(fault)

    def test_remove_existing_fault(self, injector: NetworkFaultInjector) -> None:
        """Remove existing fault returns True."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        fault_id = injector.inject(fault)
        assert injector.remove(fault_id) is True

    def test_remove_nonexistent_fault(
        self, injector: NetworkFaultInjector
    ) -> None:
        """Remove nonexistent fault returns False."""
        assert injector.remove("net-12345678") is False

    def test_list_active_empty(self, injector: NetworkFaultInjector) -> None:
        """List active faults when none exist."""
        active = injector.list_active()
        assert active == {}

    def test_list_active_with_faults(
        self, injector: NetworkFaultInjector
    ) -> None:
        """List active faults with injected faults."""
        fault1 = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        fault2 = NetworkFault(
            fault_type=FaultType.LATENCY,
            target_containers=["container-2"],
            latency_ms=100,
            dry_run=True,
        )
        fault_id1 = injector.inject(fault1)
        fault_id2 = injector.inject(fault2)

        active = injector.list_active()
        assert len(active) == 2
        assert fault_id1 in active
        assert fault_id2 in active

    def test_remove_all(self, injector: NetworkFaultInjector) -> None:
        """Remove all faults."""
        fault1 = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        fault2 = NetworkFault(
            fault_type=FaultType.LATENCY,
            target_containers=["container-2"],
            latency_ms=100,
            dry_run=True,
        )
        injector.inject(fault1)
        injector.inject(fault2)

        count = injector.remove_all()
        assert count == 2
        assert injector.list_active() == {}

    def test_inject_packet_loss_convenience(
        self, injector: NetworkFaultInjector
    ) -> None:
        """Convenience method inject_packet_loss works."""
        fault_id = injector.inject_packet_loss(
            containers=["container-1"],
            loss_percent=20.0,
        )
        assert fault_id.startswith("net-")
        assert len(injector.list_active()) == 1

    def test_inject_latency_convenience(
        self, injector: NetworkFaultInjector
    ) -> None:
        """Convenience method inject_latency works."""
        fault_id = injector.inject_latency(
            containers=["container-1"],
            latency_ms=100,
            jitter_ms=10,
        )
        assert fault_id.startswith("net-")
        assert len(injector.list_active()) == 1

    def test_inject_bandwidth_limit_convenience(
        self, injector: NetworkFaultInjector
    ) -> None:
        """Convenience method inject_bandwidth_limit works."""
        fault_id = injector.inject_bandwidth_limit(
            containers=["container-1"],
            bandwidth_kbps=1000,
        )
        assert fault_id.startswith("net-")
        assert len(injector.list_active()) == 1

    def test_multiple_containers(self, injector: NetworkFaultInjector) -> None:
        """Fault can target multiple containers."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1", "container-2", "container-3"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        fault_id = injector.inject(fault)
        active = injector.list_active()
        assert len(active[fault_id].target_containers) == 3

    def test_latency_with_jitter(self, injector: NetworkFaultInjector) -> None:
        """Latency fault with jitter validates correctly."""
        fault = NetworkFault(
            fault_type=FaultType.LATENCY,
            target_containers=["container-1"],
            latency_ms=100,
            jitter_ms=10,
            dry_run=True,
        )
        errors = fault.validate()
        assert errors == []
        fault_id = injector.inject(fault)
        assert fault_id.startswith("net-")

    def test_corruption_fault(self, injector: NetworkFaultInjector) -> None:
        """Corruption fault validates and injects."""
        fault = NetworkFault(
            fault_type=FaultType.CORRUPTION,
            target_containers=["container-1"],
            corruption_percent=5.0,
            dry_run=True,
        )
        errors = fault.validate()
        assert errors == []
        fault_id = injector.inject(fault)
        assert fault_id.startswith("net-")

    def test_reorder_fault(self, injector: NetworkFaultInjector) -> None:
        """Reorder fault validates and injects."""
        fault = NetworkFault(
            fault_type=FaultType.REORDER,
            target_containers=["container-1"],
            reorder_percent=25.0,
            dry_run=True,
        )
        errors = fault.validate()
        assert errors == []
        fault_id = injector.inject(fault)
        assert fault_id.startswith("net-")
