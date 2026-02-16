"""Unit tests for safe fault injection wrapper."""

from __future__ import annotations

import pytest

from chaoswopr.chaos.network_faults import FaultType, NetworkFault
from chaoswopr.chaos.node_faults import NodeFault, NodeFaultType
from chaoswopr.chaos.safe_injector import (
    InjectionResult,
    RolloutConfig,
    RolloutPhase,
    SafeFaultInjector,
    SafetyViolation,
)
from chaoswopr.safety.blast_radius import BlastRadiusConfig
from chaoswopr.safety.circuit_breaker import CircuitBreaker, CircuitBreakerState


class TestRolloutConfig:
    """Test RolloutConfig."""

    def test_default_config(self) -> None:
        """Default rollout config has expected values."""
        config = RolloutConfig()
        assert config.enabled is True
        assert len(config.phases) == 3
        assert config.observation_window_seconds == 60
        assert config.auto_escalate is False

    def test_get_max_impact_percent(self) -> None:
        """get_max_impact_percent returns correct values."""
        config = RolloutConfig()
        assert config.get_max_impact_percent(RolloutPhase.PHASE_1) == 5.0
        assert config.get_max_impact_percent(RolloutPhase.PHASE_2) == 10.0
        assert config.get_max_impact_percent(RolloutPhase.PHASE_3) == 20.0
        assert config.get_max_impact_percent(RolloutPhase.PHASE_4) == 33.0


class TestSafeFaultInjector:
    """Test SafeFaultInjector."""

    @pytest.fixture
    def circuit_breaker(self) -> CircuitBreaker:
        """Create a circuit breaker in ARMED state."""
        cb = CircuitBreaker()
        cb.arm()
        return cb

    @pytest.fixture
    def blast_radius_config(self) -> BlastRadiusConfig:
        """Create a blast radius configuration."""
        return BlastRadiusConfig(max_affected_percent=33.0)

    @pytest.fixture
    def injector(
        self, circuit_breaker: CircuitBreaker, blast_radius_config: BlastRadiusConfig
    ) -> SafeFaultInjector:
        """Create a safe fault injector."""
        return SafeFaultInjector(
            circuit_breaker=circuit_breaker,
            blast_radius_config=blast_radius_config,
            total_nodes=50,
            dry_run=True,
        )

    def test_inject_network_fault_success(
        self, injector: SafeFaultInjector
    ) -> None:
        """Inject valid network fault succeeds."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        result = injector.inject_network_fault(fault)
        assert result.success is True
        assert result.fault_id is not None
        assert result.fault_id.startswith("net-")

    def test_inject_network_fault_circuit_breaker_tripped(
        self,
        circuit_breaker: CircuitBreaker,
        blast_radius_config: BlastRadiusConfig,
    ) -> None:
        """Inject network fault fails when circuit breaker is tripped."""
        # Trip the circuit breaker
        circuit_breaker.trip("Test trip")

        injector = SafeFaultInjector(
            circuit_breaker=circuit_breaker,
            blast_radius_config=blast_radius_config,
            total_nodes=50,
            dry_run=True,
        )

        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        result = injector.inject_network_fault(fault)
        assert result.success is False
        assert result.violation_type == "circuit_breaker_tripped"

    def test_inject_network_fault_blast_radius_exceeded(
        self, injector: SafeFaultInjector
    ) -> None:
        """Inject network fault fails when blast radius exceeded."""
        # Create fault affecting too many containers
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=[f"container-{i}" for i in range(20)],  # 40% of nodes
            packet_loss_percent=20.0,
            dry_run=True,
        )
        result = injector.inject_network_fault(fault)
        assert result.success is False
        assert result.violation_type == "blast_radius_exceeded"

    def test_inject_network_fault_phased_rollout_violation(
        self, injector: SafeFaultInjector
    ) -> None:
        """Inject network fault fails when exceeding current phase limit."""
        # Create fault affecting 10% of nodes (exceeds Phase 1 limit of 5%)
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=[f"container-{i}" for i in range(5)],  # 10% of nodes
            packet_loss_percent=20.0,
            dry_run=True,
        )
        result = injector.inject_network_fault(fault)
        assert result.success is False
        assert result.violation_type == "phased_rollout_violation"

    def test_inject_node_fault_success(
        self, injector: SafeFaultInjector
    ) -> None:
        """Inject valid node fault succeeds."""
        fault = NodeFault(
            fault_type=NodeFaultType.CPU_STRESS,
            namespace="default",
            label_selectors={"app": "nethermind"},
            cpu_workers=2,
            cpu_load=80,
            dry_run=True,
        )
        result = injector.inject_node_fault(fault)
        assert result.success is True
        assert result.fault_id is not None
        assert result.fault_id.startswith("node-")

    def test_inject_node_fault_circuit_breaker_tripped(
        self,
        circuit_breaker: CircuitBreaker,
        blast_radius_config: BlastRadiusConfig,
    ) -> None:
        """Inject node fault fails when circuit breaker is tripped."""
        # Trip the circuit breaker
        circuit_breaker.trip("Test trip")

        injector = SafeFaultInjector(
            circuit_breaker=circuit_breaker,
            blast_radius_config=blast_radius_config,
            total_nodes=50,
            dry_run=True,
        )

        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={"app": "lighthouse"},
            dry_run=True,
        )
        result = injector.inject_node_fault(fault)
        assert result.success is False
        assert result.violation_type == "circuit_breaker_tripped"

    def test_remove_fault(self, injector: SafeFaultInjector) -> None:
        """Remove active fault succeeds."""
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        result = injector.inject_network_fault(fault)
        assert result.success is True

        removed = injector.remove_fault(result.fault_id)
        assert removed is True

    def test_remove_nonexistent_fault(
        self, injector: SafeFaultInjector
    ) -> None:
        """Remove nonexistent fault returns False."""
        removed = injector.remove_fault("net-12345678")
        assert removed is False

    def test_remove_all(self, injector: SafeFaultInjector) -> None:
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

        injector.inject_network_fault(fault1)
        injector.inject_network_fault(fault2)

        count = injector.remove_all()
        assert count == 2

    def test_advance_phase(self, injector: SafeFaultInjector) -> None:
        """Advance to next rollout phase."""
        # Should start at Phase 1
        assert injector._current_phase == RolloutPhase.PHASE_1

        # Advance to Phase 2
        advanced = injector.advance_phase()
        assert advanced is True
        assert injector._current_phase == RolloutPhase.PHASE_2

        # Advance to Phase 3
        advanced = injector.advance_phase()
        assert advanced is True
        assert injector._current_phase == RolloutPhase.PHASE_3

        # Can't advance beyond last phase
        advanced = injector.advance_phase()
        assert advanced is False
        assert injector._current_phase == RolloutPhase.PHASE_3

    def test_get_violations(self, injector: SafeFaultInjector) -> None:
        """Get recorded safety violations."""
        # Inject fault that exceeds blast radius
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=[f"container-{i}" for i in range(20)],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        result = injector.inject_network_fault(fault)
        assert result.success is False

        violations = injector.get_violations()
        assert len(violations) == 1
        assert violations[0].violation_type == "blast_radius_exceeded"

    def test_get_current_impact(self, injector: SafeFaultInjector) -> None:
        """Calculate total current impact."""
        # No faults initially
        assert injector.get_current_impact() == 0.0

        # Inject fault
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=["container-1"],
            packet_loss_percent=20.0,
            dry_run=True,
        )
        result = injector.inject_network_fault(fault)
        assert result.success is True

        # Should have some impact now
        impact = injector.get_current_impact()
        assert impact > 0.0

    def test_phased_rollout_disabled(
        self,
        circuit_breaker: CircuitBreaker,
        blast_radius_config: BlastRadiusConfig,
    ) -> None:
        """Phased rollout can be disabled."""
        rollout_config = RolloutConfig(enabled=False)
        injector = SafeFaultInjector(
            circuit_breaker=circuit_breaker,
            blast_radius_config=blast_radius_config,
            total_nodes=50,
            rollout_config=rollout_config,
            dry_run=True,
        )

        # Should be able to inject fault that exceeds Phase 1 limit
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=[f"container-{i}" for i in range(5)],  # 10%
            packet_loss_percent=20.0,
            dry_run=True,
        )
        result = injector.inject_network_fault(fault)
        assert result.success is True

    def test_injection_result_success(self) -> None:
        """InjectionResult for successful injection."""
        result = InjectionResult(
            success=True,
            fault_id="net-12345678",
            impact_percent=10.0,
        )
        assert result.success is True
        assert result.fault_id == "net-12345678"
        assert result.impact_percent == 10.0
        assert result.error_message is None

    def test_injection_result_failure(self) -> None:
        """InjectionResult for failed injection."""
        result = InjectionResult(
            success=False,
            error_message="Blast radius exceeded",
            violation_type="blast_radius_exceeded",
        )
        assert result.success is False
        assert result.fault_id is None
        assert result.error_message == "Blast radius exceeded"
        assert result.violation_type == "blast_radius_exceeded"
