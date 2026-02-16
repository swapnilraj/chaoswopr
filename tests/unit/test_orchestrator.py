"""Unit tests for the Orchestrator Agent framework.

Tests the state machine, experiment lifecycle, circuit breaker integration,
and safety enforcement of the Orchestrator Agent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from chaoswopr.agents.orchestrator import (
    ExperimentContext,
    OrchestratorAgent,
    OrchestratorState,
    VALID_TRANSITIONS,
)
from chaoswopr.safety.audit import AuditLogger
from chaoswopr.safety.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    ThresholdConfig,
    TripEvent,
)


class TestOrchestratorState:
    """Tests for OrchestratorState enum."""

    def test_all_states_defined(self) -> None:
        """All expected states should be defined."""
        expected = {
            "idle", "pre_flight", "hypothesis", "planning",
            "executing", "monitoring", "analyzing", "reporting",
            "halted", "error",
        }
        actual = {s.value for s in OrchestratorState}
        assert actual == expected

    def test_valid_transitions_cover_all_states(self) -> None:
        """Every state should have at least one valid transition."""
        for state in OrchestratorState:
            assert state in VALID_TRANSITIONS, f"Missing transitions for {state.value}"


class TestExperimentContext:
    """Tests for ExperimentContext data class."""

    def test_creation(self) -> None:
        """Context should be created with default values."""
        ctx = ExperimentContext()
        assert ctx.experiment_id is not None
        assert len(ctx.experiment_id) == 8
        assert ctx.scenario == {}
        assert ctx.hypothesis is None
        assert ctx.halted is False

    def test_duration_with_no_start(self) -> None:
        """Duration should be 0 if not started."""
        ctx = ExperimentContext()
        assert ctx.duration_seconds() == 0.0

    def test_duration_with_start(self) -> None:
        """Duration should be calculated from start time."""
        ctx = ExperimentContext()
        ctx.start_time = datetime.now(timezone.utc)
        duration = ctx.duration_seconds()
        assert duration >= 0.0

    def test_add_event(self) -> None:
        """Events should be added with timestamp."""
        ctx = ExperimentContext()
        ctx.add_event("test_event", {"key": "value"})
        assert len(ctx.events) == 1
        assert ctx.events[0]["event_type"] == "test_event"
        assert ctx.events[0]["details"]["key"] == "value"

    def test_to_dict(self) -> None:
        """Context should serialize to dictionary."""
        ctx = ExperimentContext(
            scenario={"name": "test_scenario"},
        )
        ctx.start_time = datetime.now(timezone.utc)
        d = ctx.to_dict()
        assert d["scenario_name"] == "test_scenario"
        assert d["experiment_id"] is not None
        assert d["halted"] is False

    def test_to_dict_with_halt(self) -> None:
        """Halted context should show halt info."""
        ctx = ExperimentContext()
        ctx.halted = True
        ctx.halt_reason = "safety violation"
        d = ctx.to_dict()
        assert d["halted"] is True
        assert d["halt_reason"] == "safety violation"


class TestOrchestratorAgent:
    """Tests for the OrchestratorAgent core logic."""

    def _make_agent(self, **kwargs: Any) -> OrchestratorAgent:
        """Helper to create an OrchestratorAgent with defaults."""
        cb = kwargs.pop("circuit_breaker", CircuitBreaker())
        al = kwargs.pop("audit_logger", AuditLogger(default_agent_id="test"))
        return OrchestratorAgent(
            circuit_breaker=cb,
            audit_logger=al,
            dry_run=True,
            **kwargs,
        )

    def test_initial_state(self) -> None:
        """Agent should start in IDLE state."""
        agent = self._make_agent()
        assert agent.state == OrchestratorState.IDLE
        assert agent.context is None
        assert agent.experiment_count == 0

    def test_start_experiment(self) -> None:
        """Starting an experiment should transition to PRE_FLIGHT."""
        agent = self._make_agent()
        scenario = {"name": "test_scenario"}
        ctx = agent.start_experiment(scenario)

        assert agent.state == OrchestratorState.PRE_FLIGHT
        assert agent.context is not None
        assert agent.context.experiment_id == ctx.experiment_id
        assert agent.experiment_count == 1

    def test_start_experiment_returns_context(self) -> None:
        """start_experiment should return an ExperimentContext."""
        agent = self._make_agent()
        ctx = agent.start_experiment({"name": "test"})
        assert isinstance(ctx, ExperimentContext)
        assert ctx.start_time is not None

    def test_cannot_start_when_not_idle(self) -> None:
        """Cannot start a new experiment if not in IDLE state."""
        agent = self._make_agent()
        agent.start_experiment({"name": "test"})

        with pytest.raises(RuntimeError, match="orchestrator is in"):
            agent.start_experiment({"name": "another"})

    def test_cannot_start_with_tripped_breaker(self) -> None:
        """Cannot start experiment if circuit breaker is tripped."""
        cb = CircuitBreaker()
        cb.trip(TripEvent(
            timestamp=datetime.now(timezone.utc),
            reason="test trip",
            metric_name="test",
            metric_value=100.0,
            threshold_value=50.0,
        ))
        agent = self._make_agent(circuit_breaker=cb)

        with pytest.raises(RuntimeError, match="circuit breaker is tripped"):
            agent.start_experiment({"name": "test"})

    def test_advance_through_states(self) -> None:
        """Agent should advance through the normal state progression."""
        agent = self._make_agent()
        agent.start_experiment({"name": "test"})

        expected_states = [
            OrchestratorState.HYPOTHESIS,
            OrchestratorState.PLANNING,
            OrchestratorState.EXECUTING,
            OrchestratorState.MONITORING,
            OrchestratorState.ANALYZING,
            OrchestratorState.REPORTING,
            OrchestratorState.IDLE,
        ]

        for expected in expected_states:
            new_state = agent.advance()
            assert new_state == expected

    def test_advance_halts_on_circuit_breaker_trip(self) -> None:
        """Tripping circuit breaker should halt experiment via callback."""
        cb = CircuitBreaker()
        agent = self._make_agent(circuit_breaker=cb)
        agent.start_experiment({"name": "test"})

        # Trip the circuit breaker - callback should halt immediately
        cb.trip(TripEvent(
            timestamp=datetime.now(timezone.utc),
            reason="finality loss",
            metric_name="finality_delay_seconds",
            metric_value=700.0,
            threshold_value=600.0,
        ))

        # The callback should have already transitioned to HALTED
        assert agent.state == OrchestratorState.HALTED

    def test_advance_from_idle_raises(self) -> None:
        """Cannot advance from IDLE state."""
        agent = self._make_agent()
        with pytest.raises(RuntimeError, match="Cannot advance from idle"):
            agent.advance()

    def test_halt_experiment(self) -> None:
        """halt_experiment should transition to HALTED."""
        agent = self._make_agent()
        agent.start_experiment({"name": "test"})
        agent.halt_experiment(reason="manual stop")

        assert agent.state == OrchestratorState.HALTED
        assert agent.context.halted is True
        assert agent.context.halt_reason == "manual stop"

    def test_halt_from_idle_is_noop(self) -> None:
        """Halting from IDLE should be a no-op."""
        agent = self._make_agent()
        agent.halt_experiment()
        assert agent.state == OrchestratorState.IDLE

    def test_reset_from_halted(self) -> None:
        """Reset should transition from HALTED to IDLE."""
        agent = self._make_agent()
        agent.start_experiment({"name": "test"})
        agent.halt_experiment(reason="test")
        agent.reset()

        assert agent.state == OrchestratorState.IDLE
        assert agent.context is None

    def test_reset_from_error(self) -> None:
        """Reset should work from ERROR state too."""
        agent = self._make_agent()
        agent.start_experiment({"name": "test"})
        # Force error state
        agent._state = OrchestratorState.ERROR
        agent.reset()

        assert agent.state == OrchestratorState.IDLE

    def test_reset_from_idle_raises(self) -> None:
        """Cannot reset from IDLE state."""
        agent = self._make_agent()
        with pytest.raises(RuntimeError, match="must be HALTED or ERROR"):
            agent.reset()

    def test_record_metrics(self) -> None:
        """record_metrics should add snapshot to context."""
        agent = self._make_agent()
        agent.start_experiment({"name": "test"})
        agent.record_metrics({"finality_delay_seconds": 13.5})

        assert len(agent.context.metrics_snapshots) == 1
        assert agent.context.metrics_snapshots[0]["metrics"]["finality_delay_seconds"] == 13.5

    def test_record_metrics_feeds_circuit_breaker(self) -> None:
        """record_metrics should check circuit breaker with metrics."""
        cb = CircuitBreaker()
        agent = self._make_agent(circuit_breaker=cb)
        agent.start_experiment({"name": "test"})

        agent.record_metrics({"finality_delay_seconds": 13.5})
        assert cb.check_count == 1

    def test_record_metrics_trips_circuit_breaker(self) -> None:
        """Recording bad metrics should trip the circuit breaker."""
        cb = CircuitBreaker(
            thresholds=ThresholdConfig(finality_delay_max_seconds=10.0)
        )
        agent = self._make_agent(circuit_breaker=cb)
        agent.start_experiment({"name": "test"})

        # This should trip the breaker and halt the experiment
        agent.record_metrics({"finality_delay_seconds": 15.0})

        assert cb.is_tripped
        assert agent.state == OrchestratorState.HALTED

    def test_get_status(self) -> None:
        """get_status should return comprehensive status dict."""
        agent = self._make_agent()
        status = agent.get_status()

        assert status["state"] == "idle"
        assert status["experiment_count"] == 0
        assert status["circuit_breaker_state"] == "armed"
        assert status["experiment"] is None

    def test_get_status_during_experiment(self) -> None:
        """get_status should include experiment info when running."""
        agent = self._make_agent()
        agent.start_experiment({"name": "test_scenario"})

        status = agent.get_status()
        assert status["state"] == "pre_flight"
        assert status["experiment"] is not None
        assert status["experiment"]["scenario_name"] == "test_scenario"

    def test_transition_callback(self) -> None:
        """Registered callbacks should be invoked on transitions."""
        transitions = []

        def on_transition(old: OrchestratorState, new: OrchestratorState) -> None:
            transitions.append((old, new))

        agent = self._make_agent()
        agent.register_transition_callback(on_transition)
        agent.start_experiment({"name": "test"})

        assert len(transitions) == 1
        assert transitions[0] == (OrchestratorState.IDLE, OrchestratorState.PRE_FLIGHT)

    def test_experiment_finalization(self) -> None:
        """Completing an experiment should finalize context."""
        agent = self._make_agent()
        agent.start_experiment({"name": "test"})

        # Advance through all states
        while agent.state != OrchestratorState.IDLE:
            agent.advance()

        # Context should be cleared after finalization
        assert agent.context is None

    def test_audit_logging(self) -> None:
        """Experiment lifecycle should be audit logged."""
        audit = AuditLogger(default_agent_id="test")
        agent = self._make_agent(audit_logger=audit)
        agent.start_experiment({"name": "test"})

        # Should have at least 1 audit entry for experiment start
        entries = audit.get_entries()
        assert len(entries) >= 1
        assert entries[0].action_type == "experiment_start"

    def test_circuit_breaker_trip_callback(self) -> None:
        """Circuit breaker trip should halt experiment via callback."""
        cb = CircuitBreaker()
        agent = self._make_agent(circuit_breaker=cb)
        agent.start_experiment({"name": "test"})
        agent.advance()  # Move to HYPOTHESIS

        # Trip the breaker externally
        cb.trip(TripEvent(
            timestamp=datetime.now(timezone.utc),
            reason="external trip",
            metric_name="test_metric",
            metric_value=100.0,
            threshold_value=50.0,
        ))

        assert agent.state == OrchestratorState.HALTED

    def test_multiple_experiments(self) -> None:
        """Multiple experiments should track count correctly."""
        agent = self._make_agent()

        # Run first experiment
        agent.start_experiment({"name": "test1"})
        while agent.state != OrchestratorState.IDLE:
            agent.advance()

        # Run second experiment
        agent.start_experiment({"name": "test2"})
        while agent.state != OrchestratorState.IDLE:
            agent.advance()

        assert agent.experiment_count == 2


# Allow Any type hints in test helpers
from typing import Any
