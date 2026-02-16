"""Orchestrator Agent - master controller for chaos engineering experiments.

The Orchestrator Agent is the central coordinator of the chaoswopr multi-agent
system. It generates hypotheses, plans experiments, dispatches faults,
monitors execution, and triggers analysis.

State machine:
  IDLE -> PRE_FLIGHT -> HYPOTHESIS -> PLANNING -> EXECUTING -> MONITORING -> ANALYZING -> REPORTING -> IDLE

The Orchestrator uses a handrolled agent pattern with explicit state transitions.
LangGraph provides the state graph semantics for safety-critical orchestration.

Safety integration:
  - Polls circuit breaker state before each action
  - Halts experiment immediately on circuit breaker trip
  - Triggers rollback sequence on safety violations
  - All decisions are audit-logged
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from chaoswopr.safety.audit import ActionType, AuditLogger, Outcome
from chaoswopr.safety.circuit_breaker import CircuitBreaker, CircuitBreakerState, TripEvent

logger = logging.getLogger(__name__)


class OrchestratorState(str, Enum):
    """State of the Orchestrator Agent.

    State machine flow:
      IDLE -> PRE_FLIGHT -> HYPOTHESIS -> PLANNING -> EXECUTING
           -> MONITORING -> ANALYZING -> REPORTING -> IDLE

    Safety transitions (from any active state):
      * -> HALTED (on circuit breaker trip)
      HALTED -> IDLE (after rollback complete)
    """

    IDLE = "idle"
    PRE_FLIGHT = "pre_flight"
    HYPOTHESIS = "hypothesis"
    PLANNING = "planning"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    ANALYZING = "analyzing"
    REPORTING = "reporting"
    HALTED = "halted"
    ERROR = "error"


# Valid state transitions
VALID_TRANSITIONS: dict[OrchestratorState, list[OrchestratorState]] = {
    OrchestratorState.IDLE: [OrchestratorState.PRE_FLIGHT],
    OrchestratorState.PRE_FLIGHT: [
        OrchestratorState.HYPOTHESIS,
        OrchestratorState.HALTED,
        OrchestratorState.ERROR,
    ],
    OrchestratorState.HYPOTHESIS: [
        OrchestratorState.PLANNING,
        OrchestratorState.HALTED,
        OrchestratorState.ERROR,
    ],
    OrchestratorState.PLANNING: [
        OrchestratorState.EXECUTING,
        OrchestratorState.HALTED,
        OrchestratorState.ERROR,
    ],
    OrchestratorState.EXECUTING: [
        OrchestratorState.MONITORING,
        OrchestratorState.HALTED,
        OrchestratorState.ERROR,
    ],
    OrchestratorState.MONITORING: [
        OrchestratorState.ANALYZING,
        OrchestratorState.HALTED,
        OrchestratorState.ERROR,
    ],
    OrchestratorState.ANALYZING: [
        OrchestratorState.REPORTING,
        OrchestratorState.HALTED,
        OrchestratorState.ERROR,
    ],
    OrchestratorState.REPORTING: [
        OrchestratorState.IDLE,
        OrchestratorState.HALTED,
        OrchestratorState.ERROR,
    ],
    OrchestratorState.HALTED: [OrchestratorState.IDLE],
    OrchestratorState.ERROR: [OrchestratorState.IDLE],
}


@dataclass
class ExperimentContext:
    """Context for a running experiment.

    Holds all state needed during experiment execution, including
    the scenario, hypothesis, plan, and collected metrics.

    Attributes:
        experiment_id: Unique identifier for this experiment run.
        scenario: The loaded scenario YAML dictionary.
        hypothesis: Generated hypothesis (structured output).
        plan: Compiled experiment plan.
        active_faults: Currently injected faults (fault_id -> info).
        metrics_snapshots: Periodic metric snapshots during execution.
        events: All events during this experiment.
        start_time: When the experiment started.
        end_time: When the experiment ended.
    """

    experiment_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    scenario: dict[str, Any] = field(default_factory=dict)
    hypothesis: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    active_faults: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics_snapshots: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    halted: bool = False
    halt_reason: str | None = None

    def duration_seconds(self) -> float:
        """Calculate experiment duration in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or datetime.now(timezone.utc)
        return (end - self.start_time).total_seconds()

    def add_event(self, event_type: str, details: dict[str, Any] | None = None) -> None:
        """Record an experiment event.

        Args:
            event_type: Type of event.
            details: Event-specific details.
        """
        self.events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "details": details or {},
        })

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "experiment_id": self.experiment_id,
            "scenario_name": self.scenario.get("name", "unknown"),
            "hypothesis": self.hypothesis,
            "plan": self.plan,
            "active_fault_count": len(self.active_faults),
            "metrics_snapshot_count": len(self.metrics_snapshots),
            "event_count": len(self.events),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds(),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }


class OrchestratorAgent:
    """Master controller for chaos engineering experiments.

    The Orchestrator Agent manages the complete experiment lifecycle:
    1. PRE-FLIGHT: Validate cluster health and establish baselines
    2. HYPOTHESIS: Generate a testable hypothesis from scenario + state
    3. PLANNING: Compile hypothesis into executable experiment plan
    4. EXECUTING: Dispatch fault injections according to plan
    5. MONITORING: Observe metrics and check SLOs during chaos
    6. ANALYZING: Collect results and generate analysis
    7. REPORTING: Produce experiment report and playbook

    Safety is enforced at every state transition by checking the circuit
    breaker. The agent halts immediately if the circuit breaker trips.

    Examples:
        >>> from chaoswopr.safety.circuit_breaker import CircuitBreaker
        >>> cb = CircuitBreaker()
        >>> orchestrator = OrchestratorAgent(circuit_breaker=cb, dry_run=True)
        >>> orchestrator.start_experiment(scenario={"name": "test"})
        >>> orchestrator.state
        <OrchestratorState.PRE_FLIGHT: 'pre_flight'>
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        audit_logger: AuditLogger | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the Orchestrator Agent.

        Args:
            circuit_breaker: Circuit breaker for safety enforcement.
            audit_logger: Audit logger for recording all decisions.
            dry_run: If True, don't execute real actions.
        """
        self._circuit_breaker = circuit_breaker
        self._audit_logger = audit_logger or AuditLogger(default_agent_id="orchestrator")
        self._dry_run = dry_run

        # State
        self._state = OrchestratorState.IDLE
        self._context: ExperimentContext | None = None
        self._experiment_count = 0

        # Callbacks for state transitions
        self._transition_callbacks: list[Callable[[OrchestratorState, OrchestratorState], None]] = []

        # Register circuit breaker trip callback
        self._circuit_breaker.register_trip_callback(self._on_circuit_breaker_trip)

        logger.info("Orchestrator Agent initialized (dry_run=%s)", dry_run)

    @property
    def state(self) -> OrchestratorState:
        """Get the current orchestrator state."""
        return self._state

    @property
    def context(self) -> ExperimentContext | None:
        """Get the current experiment context."""
        return self._context

    @property
    def experiment_count(self) -> int:
        """Get the total number of experiments run."""
        return self._experiment_count

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Get the circuit breaker instance."""
        return self._circuit_breaker

    def register_transition_callback(
        self,
        callback: Callable[[OrchestratorState, OrchestratorState], None],
    ) -> None:
        """Register a callback for state transitions.

        Args:
            callback: Function called with (old_state, new_state).
        """
        self._transition_callbacks.append(callback)

    def start_experiment(self, scenario: dict[str, Any]) -> ExperimentContext:
        """Start a new experiment from a scenario.

        Transitions from IDLE to PRE_FLIGHT and creates a new experiment context.

        Args:
            scenario: Loaded scenario dictionary (from YAML).

        Returns:
            The new experiment context.

        Raises:
            RuntimeError: If not in IDLE state or circuit breaker is tripped.
        """
        if self._state != OrchestratorState.IDLE:
            raise RuntimeError(
                f"Cannot start experiment: orchestrator is in {self._state.value} state"
            )

        # Check circuit breaker before starting
        if self._circuit_breaker.is_tripped:
            raise RuntimeError("Cannot start experiment: circuit breaker is tripped")

        # Create experiment context
        self._context = ExperimentContext(scenario=scenario)
        self._context.start_time = datetime.now(timezone.utc)
        self._context.add_event("experiment_start", {"scenario": scenario.get("name", "unknown")})
        self._experiment_count += 1

        # Audit log
        self._audit_logger.log(
            action_type=ActionType.EXPERIMENT_START,
            target=scenario.get("name", "unknown"),
            outcome=Outcome.SUCCESS,
            agent_id="orchestrator",
            experiment_id=self._context.experiment_id,
            parameters={"scenario_name": scenario.get("name", "unknown")},
        )

        # Transition to PRE_FLIGHT
        self._transition_to(OrchestratorState.PRE_FLIGHT)

        logger.info(
            "Experiment %s started with scenario '%s'",
            self._context.experiment_id,
            scenario.get("name", "unknown"),
        )

        return self._context

    def advance(self) -> OrchestratorState:
        """Advance to the next state in the experiment lifecycle.

        Performs safety checks (circuit breaker) before each transition.
        Returns the new state after advancement.

        Returns:
            The new orchestrator state.

        Raises:
            RuntimeError: If in IDLE, HALTED, or ERROR state.
        """
        if self._state in (OrchestratorState.IDLE, OrchestratorState.HALTED, OrchestratorState.ERROR):
            raise RuntimeError(
                f"Cannot advance from {self._state.value} state"
            )

        # Safety check before every advance
        if not self._check_circuit_breaker():
            return self._state  # Already transitioned to HALTED

        # Determine next state
        next_state = self._get_next_state()
        if next_state is None:
            raise RuntimeError(f"No valid next state from {self._state.value}")

        self._transition_to(next_state)

        # If we just moved to IDLE, finalize the experiment
        if self._state == OrchestratorState.IDLE and self._context is not None:
            self._finalize_experiment()

        return self._state

    def halt_experiment(self, reason: str = "Manual halt") -> None:
        """Halt the current experiment.

        Transitions to HALTED state and records the reason.

        Args:
            reason: Reason for halting.
        """
        if self._state == OrchestratorState.IDLE:
            return  # Nothing to halt

        if self._context is not None:
            self._context.halted = True
            self._context.halt_reason = reason
            self._context.add_event("experiment_halt", {"reason": reason})

        self._audit_logger.log(
            action_type=ActionType.EXPERIMENT_ABORT,
            target=self._context.experiment_id if self._context else "unknown",
            outcome=Outcome.BLOCKED,
            agent_id="orchestrator",
            experiment_id=self._context.experiment_id if self._context else None,
            parameters={"reason": reason},
        )

        self._transition_to(OrchestratorState.HALTED)

        logger.warning("Experiment halted: %s", reason)

    def reset(self) -> None:
        """Reset from HALTED or ERROR state back to IDLE.

        Cleans up the experiment context and prepares for a new experiment.
        """
        if self._state not in (OrchestratorState.HALTED, OrchestratorState.ERROR):
            raise RuntimeError(
                f"Cannot reset from {self._state.value} state "
                f"(must be HALTED or ERROR)"
            )

        if self._context is not None:
            self._finalize_experiment()

        self._transition_to(OrchestratorState.IDLE)

        logger.info("Orchestrator reset to IDLE")

    def record_metrics(self, metrics: dict[str, float]) -> None:
        """Record a metrics snapshot for the current experiment.

        Also feeds metrics to the circuit breaker for safety checking.

        Args:
            metrics: Dictionary of metric_name -> value.
        """
        if self._context is None:
            return

        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
        }
        self._context.metrics_snapshots.append(snapshot)

        # Feed to circuit breaker
        self._circuit_breaker.check_metrics(
            metrics=metrics,
            experiment_id=self._context.experiment_id,
        )

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the Orchestrator.

        Returns:
            Dictionary with orchestrator state, experiment info, and safety status.
        """
        status: dict[str, Any] = {
            "state": self._state.value,
            "experiment_count": self._experiment_count,
            "circuit_breaker_state": self._circuit_breaker.state.value,
            "dry_run": self._dry_run,
        }

        if self._context is not None:
            status["experiment"] = self._context.to_dict()
        else:
            status["experiment"] = None

        return status

    def _transition_to(self, new_state: OrchestratorState) -> None:
        """Transition to a new state with validation.

        Args:
            new_state: Target state.

        Raises:
            ValueError: If the transition is not valid.
        """
        valid_targets = VALID_TRANSITIONS.get(self._state, [])

        # HALTED is always valid from any non-IDLE state
        if new_state == OrchestratorState.HALTED and self._state != OrchestratorState.IDLE:
            pass  # Always allow halt
        elif new_state not in valid_targets:
            raise ValueError(
                f"Invalid state transition: {self._state.value} -> {new_state.value}. "
                f"Valid targets: {[s.value for s in valid_targets]}"
            )

        old_state = self._state
        self._state = new_state

        # Invoke transition callbacks
        for callback in self._transition_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error("Transition callback error: %s", e)

        logger.debug(
            "State transition: %s -> %s",
            old_state.value,
            new_state.value,
        )

    def _get_next_state(self) -> OrchestratorState | None:
        """Determine the next state in the normal experiment flow.

        Returns:
            The next state, or None if no progression is possible.
        """
        progression = {
            OrchestratorState.PRE_FLIGHT: OrchestratorState.HYPOTHESIS,
            OrchestratorState.HYPOTHESIS: OrchestratorState.PLANNING,
            OrchestratorState.PLANNING: OrchestratorState.EXECUTING,
            OrchestratorState.EXECUTING: OrchestratorState.MONITORING,
            OrchestratorState.MONITORING: OrchestratorState.ANALYZING,
            OrchestratorState.ANALYZING: OrchestratorState.REPORTING,
            OrchestratorState.REPORTING: OrchestratorState.IDLE,
        }
        return progression.get(self._state)

    def _check_circuit_breaker(self) -> bool:
        """Check the circuit breaker state before an action.

        If the circuit breaker is tripped, transitions to HALTED state.

        Returns:
            True if safe to proceed, False if halted.
        """
        if self._circuit_breaker.is_tripped:
            self.halt_experiment(
                reason=f"Circuit breaker tripped: {self._get_trip_reason()}"
            )
            return False
        return True

    def _get_trip_reason(self) -> str:
        """Get the most recent circuit breaker trip reason.

        Returns:
            Trip reason string.
        """
        events = self._circuit_breaker.trip_events
        if events:
            return events[-1].reason
        return "Unknown"

    def _on_circuit_breaker_trip(self, event: TripEvent) -> None:
        """Callback when circuit breaker trips during an experiment.

        Args:
            event: The trip event details.
        """
        if self._state != OrchestratorState.IDLE:
            logger.critical(
                "Circuit breaker tripped during experiment: %s",
                event.reason,
            )
            self.halt_experiment(reason=f"Circuit breaker: {event.reason}")

    def _finalize_experiment(self) -> None:
        """Finalize the current experiment.

        Records end time and logs completion.
        """
        if self._context is None:
            return

        self._context.end_time = datetime.now(timezone.utc)

        outcome = Outcome.SUCCESS if not self._context.halted else Outcome.BLOCKED
        self._audit_logger.log(
            action_type=ActionType.EXPERIMENT_COMPLETE,
            target=self._context.experiment_id,
            outcome=outcome,
            agent_id="orchestrator",
            experiment_id=self._context.experiment_id,
            parameters={
                "duration_seconds": self._context.duration_seconds(),
                "halted": self._context.halted,
                "halt_reason": self._context.halt_reason,
                "metrics_snapshots": len(self._context.metrics_snapshots),
                "events": len(self._context.events),
            },
        )

        logger.info(
            "Experiment %s finalized (duration=%.1fs, halted=%s)",
            self._context.experiment_id,
            self._context.duration_seconds(),
            self._context.halted,
        )

        self._context = None
