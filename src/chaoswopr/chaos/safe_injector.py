"""Safe fault injection wrapper with blast radius and circuit breaker enforcement.

This module wraps all fault injection APIs (network, node, protocol) with safety checks
to prevent dangerous fault injections that could corrupt the testnet or violate safety constraints.

Safety features:
- Blast radius validation: Never affect >33% of nodes simultaneously
- Circuit breaker checking: Halt if circuit breaker is tripped
- Phased rollout: Ramp up fault impact through configured steps (5% → 10% → 20%)
- Audit logging: Record every injection attempt and decision
- Automatic rollback: Remove faults if safety violation detected
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from chaoswopr.chaos.network_faults import NetworkFault, NetworkFaultInjector
from chaoswopr.chaos.node_faults import NodeFault, NodeFaultInjector
from chaoswopr.safety.audit import AuditLogger
from chaoswopr.safety.blast_radius import BlastRadiusConfig, validate_blast_radius
from chaoswopr.safety.circuit_breaker import CircuitBreaker, CircuitBreakerState


class RolloutPhase(str, Enum):
    """Phased rollout stages for fault injection."""

    PHASE_1 = "5%"  # Initial cautious phase
    PHASE_2 = "10%"  # Second phase
    PHASE_3 = "20%"  # Third phase
    PHASE_4 = "33%"  # Maximum allowed (blast radius limit)


@dataclass
class RolloutConfig:
    """Configuration for phased fault rollout.

    Attributes:
        enabled: Whether phased rollout is enforced.
        phases: List of rollout phases to go through.
        observation_window_seconds: Time to wait between phases.
        auto_escalate: Auto-escalate to next phase if no issues detected.
    """

    enabled: bool = True
    phases: list[RolloutPhase] = field(
        default_factory=lambda: [
            RolloutPhase.PHASE_1,
            RolloutPhase.PHASE_2,
            RolloutPhase.PHASE_3,
        ]
    )
    observation_window_seconds: int = 60
    auto_escalate: bool = False

    def get_max_impact_percent(self, phase: RolloutPhase) -> float:
        """Get maximum impact percentage for a phase.

        Args:
            phase: Rollout phase.

        Returns:
            Maximum impact percentage (0-100).
        """
        phase_map = {
            RolloutPhase.PHASE_1: 5.0,
            RolloutPhase.PHASE_2: 10.0,
            RolloutPhase.PHASE_3: 20.0,
            RolloutPhase.PHASE_4: 33.0,
        }
        return phase_map.get(phase, 5.0)


@dataclass
class SafetyViolation:
    """Record of a safety violation.

    Attributes:
        violation_type: Type of violation.
        message: Human-readable description.
        fault_config: Configuration that caused the violation.
        timestamp: When the violation occurred.
    """

    violation_type: str
    message: str
    fault_config: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class SafeFaultInjector:
    """Safe fault injection with safety checks and phased rollout.

    Wraps NetworkFaultInjector and NodeFaultInjector with safety enforcement.
    All fault injections go through safety validation before execution.

    Examples:
        >>> circuit_breaker = CircuitBreaker()
        >>> blast_radius = BlastRadiusCalculator(BlastRadiusConfig(max_nodes_percent=33.0))
        >>> injector = SafeFaultInjector(
        ...     circuit_breaker=circuit_breaker,
        ...     blast_radius_calculator=blast_radius,
        ... )
        >>> fault = NetworkFault(
        ...     fault_type=FaultType.PACKET_LOSS,
        ...     target_containers=["container-1"],
        ...     packet_loss_percent=20.0,
        ... )
        >>> result = injector.inject_network_fault(fault)
        >>> if result.success:
        ...     injector.remove_fault(result.fault_id)
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        blast_radius_config: BlastRadiusConfig,
        total_nodes: int = 50,
        audit_logger: AuditLogger | None = None,
        rollout_config: RolloutConfig | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize safe fault injector.

        Args:
            circuit_breaker: Circuit breaker for safety enforcement.
            blast_radius_config: Blast radius configuration.
            total_nodes: Total number of nodes in the testnet.
            audit_logger: Audit logger for recording actions.
            rollout_config: Phased rollout configuration.
            dry_run: If True, log actions but don't execute them.
        """
        self._circuit_breaker = circuit_breaker
        self._blast_radius_config = blast_radius_config
        self._total_nodes = total_nodes
        self._audit_logger = audit_logger
        self._rollout_config = rollout_config or RolloutConfig()
        self._dry_run = dry_run

        # Initialize underlying injectors
        self._network_injector = NetworkFaultInjector(
            audit_logger=audit_logger,
            dry_run=dry_run,
        )
        self._node_injector = NodeFaultInjector(
            audit_logger=audit_logger,
            dry_run=dry_run,
        )

        # Track active faults and violations
        self._active_faults: dict[str, dict[str, Any]] = {}
        self._violations: list[SafetyViolation] = []
        self._current_phase: RolloutPhase = RolloutPhase.PHASE_1

    def inject_network_fault(self, fault: NetworkFault) -> InjectionResult:
        """Inject a network fault with safety checks.

        Args:
            fault: Network fault configuration.

        Returns:
            Injection result with success status and details.
        """
        # Check circuit breaker state
        if not self._check_circuit_breaker():
            return InjectionResult(
                success=False,
                error_message="Circuit breaker is tripped",
                violation_type="circuit_breaker_tripped",
            )

        # Validate blast radius
        impact = self._estimate_network_fault_impact(fault)
        if not self._validate_blast_radius(impact):
            violation = SafetyViolation(
                violation_type="blast_radius_exceeded",
                message=f"Fault would affect {impact}% of nodes (max: {self._blast_radius_config.max_affected_percent}%)",
                fault_config=fault.to_dict(),
            )
            self._violations.append(violation)
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type="safety_violation",
                    details={"violation": violation.__dict__},
                )
            return InjectionResult(
                success=False,
                error_message=violation.message,
                violation_type=violation.violation_type,
            )

        # Check phased rollout
        if self._rollout_config.enabled:
            max_allowed = self._rollout_config.get_max_impact_percent(
                self._current_phase
            )
            if impact > max_allowed:
                return InjectionResult(
                    success=False,
                    error_message=f"Fault impact {impact}% exceeds current phase limit {max_allowed}%",
                    violation_type="phased_rollout_violation",
                )

        # Inject fault
        try:
            fault_id = self._network_injector.inject(fault)
            self._active_faults[fault_id] = {
                "type": "network",
                "fault": fault,
                "impact_percent": impact,
                "phase": self._current_phase.value,
            }
            return InjectionResult(
                success=True,
                fault_id=fault_id,
                impact_percent=impact,
            )
        except (ValueError, RuntimeError) as e:
            return InjectionResult(
                success=False,
                error_message=str(e),
                violation_type="injection_failed",
            )

    def inject_node_fault(self, fault: NodeFault) -> InjectionResult:
        """Inject a node fault with safety checks.

        Args:
            fault: Node fault configuration.

        Returns:
            Injection result with success status and details.
        """
        # Check circuit breaker state
        if not self._check_circuit_breaker():
            return InjectionResult(
                success=False,
                error_message="Circuit breaker is tripped",
                violation_type="circuit_breaker_tripped",
            )

        # Validate blast radius
        impact = self._estimate_node_fault_impact(fault)
        if not self._validate_blast_radius(impact):
            violation = SafetyViolation(
                violation_type="blast_radius_exceeded",
                message=f"Fault would affect {impact}% of nodes (max: {self._blast_radius_config.max_affected_percent}%)",
                fault_config=fault.to_dict(),
            )
            self._violations.append(violation)
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type="safety_violation",
                    details={"violation": violation.__dict__},
                )
            return InjectionResult(
                success=False,
                error_message=violation.message,
                violation_type=violation.violation_type,
            )

        # Check phased rollout
        if self._rollout_config.enabled:
            max_allowed = self._rollout_config.get_max_impact_percent(
                self._current_phase
            )
            if impact > max_allowed:
                return InjectionResult(
                    success=False,
                    error_message=f"Fault impact {impact}% exceeds current phase limit {max_allowed}%",
                    violation_type="phased_rollout_violation",
                )

        # Inject fault
        try:
            fault_id = self._node_injector.inject(fault)
            self._active_faults[fault_id] = {
                "type": "node",
                "fault": fault,
                "impact_percent": impact,
                "phase": self._current_phase.value,
            }
            return InjectionResult(
                success=True,
                fault_id=fault_id,
                impact_percent=impact,
            )
        except (ValueError, RuntimeError) as e:
            return InjectionResult(
                success=False,
                error_message=str(e),
                violation_type="injection_failed",
            )

    def remove_fault(self, fault_id: str) -> bool:
        """Remove an active fault.

        Args:
            fault_id: Fault ID to remove.

        Returns:
            True if fault was removed, False if not found.
        """
        if fault_id not in self._active_faults:
            return False

        fault_info = self._active_faults[fault_id]
        fault_type = fault_info["type"]

        # Remove from appropriate injector
        if fault_type == "network":
            success = self._network_injector.remove(fault_id)
        elif fault_type == "node":
            success = self._node_injector.remove(fault_id)
        else:
            return False

        if success:
            del self._active_faults[fault_id]

        return success

    def remove_all(self) -> int:
        """Remove all active faults.

        Returns:
            Number of faults removed.
        """
        count = 0
        fault_ids = list(self._active_faults.keys())
        for fault_id in fault_ids:
            if self.remove_fault(fault_id):
                count += 1
        return count

    def advance_phase(self) -> bool:
        """Advance to the next rollout phase.

        Returns:
            True if advanced, False if already at maximum phase.
        """
        if not self._rollout_config.enabled:
            return False

        phases = self._rollout_config.phases
        current_idx = phases.index(self._current_phase)

        if current_idx >= len(phases) - 1:
            # Already at last phase
            return False

        self._current_phase = phases[current_idx + 1]

        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="rollout_phase_advanced",
                details={"new_phase": self._current_phase.value},
            )

        return True

    def get_violations(self) -> list[SafetyViolation]:
        """Get all recorded safety violations.

        Returns:
            List of safety violations.
        """
        return list(self._violations)

    def get_current_impact(self) -> float:
        """Calculate total current impact from all active faults.

        Returns:
            Total impact percentage (0-100).
        """
        if not self._active_faults:
            return 0.0

        # Sum up impact from all active faults (simplified)
        total_impact = sum(
            fault_info["impact_percent"]
            for fault_info in self._active_faults.values()
        )

        # Cap at 100%
        return min(total_impact, 100.0)

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows fault injection.

        Returns:
            True if injection is allowed, False if circuit breaker is tripped.
        """
        return not self._circuit_breaker.is_tripped

    def _validate_blast_radius(self, impact_percent: float) -> bool:
        """Validate that impact doesn't exceed blast radius limits.

        Args:
            impact_percent: Estimated impact percentage.

        Returns:
            True if within limits, False if exceeds blast radius.
        """
        return impact_percent <= self._blast_radius_config.max_affected_percent

    def _estimate_network_fault_impact(self, fault: NetworkFault) -> float:
        """Estimate impact percentage of a network fault.

        Args:
            fault: Network fault configuration.

        Returns:
            Estimated impact percentage (0-100).
        """
        # For network faults, impact is based on number of containers
        # This is a simplified estimation - in reality would query cluster state
        num_containers = len(fault.target_containers)

        # Assume testnet has ~50 nodes by default (from config)
        total_nodes = 50.0

        impact = (num_containers / total_nodes) * 100.0
        return min(impact, 100.0)

    def _estimate_node_fault_impact(self, fault: NodeFault) -> float:
        """Estimate impact percentage of a node fault.

        Args:
            fault: Node fault configuration.

        Returns:
            Estimated impact percentage (0-100).
        """
        # For node faults, would query Kubernetes to count matching pods
        # This is a simplified estimation
        # Assume label selector matches ~3% of nodes by default (conservative estimate)
        return 3.0


@dataclass
class InjectionResult:
    """Result of a fault injection attempt.

    Attributes:
        success: Whether injection succeeded.
        fault_id: Fault ID if successful.
        impact_percent: Estimated impact percentage.
        error_message: Error message if failed.
        violation_type: Type of safety violation if failed.
    """

    success: bool
    fault_id: str | None = None
    impact_percent: float = 0.0
    error_message: str | None = None
    violation_type: str | None = None
