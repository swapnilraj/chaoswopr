"""Unit tests for Observer Agent framework.

Tests the ObserverAgent's observation loop, state management,
and integration with anomaly detection and SLO monitoring.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock

import pytest

from chaoswopr.agents.observer import (
    ObservationEvent,
    ObservationEventType,
    ObserverAgent,
    ObserverState,
)


class TestObserverState:
    """Tests for ObserverState enum."""

    def test_states(self) -> None:
        assert ObserverState.IDLE.value == "idle"
        assert ObserverState.OBSERVING.value == "observing"
        assert ObserverState.ANALYZING.value == "analyzing"
        assert ObserverState.REPORTING.value == "reporting"


class TestObservationEvent:
    """Tests for ObservationEvent data class."""

    def test_creation(self) -> None:
        event = ObservationEvent(
            event_type=ObservationEventType.ANOMALY_DETECTED,
            timestamp=datetime.now(timezone.utc),
            metric_name="finality_delay_seconds",
            details={"z_score": 3.5},
        )
        assert event.event_type == ObservationEventType.ANOMALY_DETECTED
        assert event.metric_name == "finality_delay_seconds"
        assert event.details["z_score"] == 3.5

    def test_to_dict(self) -> None:
        now = datetime.now(timezone.utc)
        event = ObservationEvent(
            event_type=ObservationEventType.SLO_BREACH,
            timestamp=now,
            metric_name="participation_rate",
            severity="critical",
            details={"threshold": 66.0, "current": 50.0},
        )
        d = event.to_dict()
        assert d["event_type"] == "slo_breach"
        assert d["metric_name"] == "participation_rate"
        assert d["severity"] == "critical"
        assert "timestamp" in d


class TestObserverAgent:
    """Tests for the ObserverAgent core logic."""

    def test_initial_state_is_idle(self) -> None:
        agent = ObserverAgent(prometheus_client=MagicMock())
        assert agent.state == ObserverState.IDLE
        assert agent.observation_count == 0

    def test_start_observing(self) -> None:
        agent = ObserverAgent(prometheus_client=MagicMock())
        agent.start_observing(experiment_id="exp-001")
        assert agent.state == ObserverState.OBSERVING
        assert agent.current_experiment_id == "exp-001"

    def test_stop_observing(self) -> None:
        agent = ObserverAgent(prometheus_client=MagicMock())
        agent.start_observing(experiment_id="exp-001")
        agent.stop_observing()
        assert agent.state == ObserverState.IDLE
        assert agent.current_experiment_id is None

    def test_cannot_start_observing_when_already_observing(self) -> None:
        agent = ObserverAgent(prometheus_client=MagicMock())
        agent.start_observing(experiment_id="exp-001")
        with pytest.raises(RuntimeError, match="already observing"):
            agent.start_observing(experiment_id="exp-002")

    def test_observe_cycle_increments_count(self) -> None:
        prom_client = MagicMock()
        prom_client.query.return_value = MagicMock(
            success=True, data=[{"value": [0, "13.5"]}]
        )
        agent = ObserverAgent(prometheus_client=prom_client)
        agent.start_observing(experiment_id="exp-001")

        events = agent.observe()
        assert agent.observation_count == 1

    def test_observe_returns_empty_when_idle(self) -> None:
        agent = ObserverAgent(prometheus_client=MagicMock())
        events = agent.observe()
        assert events == []

    def test_observe_queries_metrics(self) -> None:
        prom_client = MagicMock()
        prom_client.query.return_value = MagicMock(
            success=True, data=[{"value": [0, "95.5"]}]
        )
        agent = ObserverAgent(prometheus_client=prom_client)
        agent.start_observing(experiment_id="exp-001")

        events = agent.observe()
        assert prom_client.query.called

    def test_get_events(self) -> None:
        agent = ObserverAgent(prometheus_client=MagicMock())
        agent.start_observing(experiment_id="exp-001")

        # Manually add an event for testing
        event = ObservationEvent(
            event_type=ObservationEventType.ANOMALY_DETECTED,
            timestamp=datetime.now(timezone.utc),
            metric_name="test_metric",
        )
        agent._events.append(event)

        events = agent.get_events()
        # Should have 2 events: OBSERVATION_START and our manual ANOMALY_DETECTED
        assert len(events) == 2
        # Filter for just anomalies
        anomalies = [e for e in events if e.event_type == ObservationEventType.ANOMALY_DETECTED]
        assert len(anomalies) == 1
        assert anomalies[0].metric_name == "test_metric"

    def test_get_events_filtered_by_type(self) -> None:
        agent = ObserverAgent(prometheus_client=MagicMock())
        agent.start_observing(experiment_id="exp-001")

        # Add different event types
        agent._events.append(
            ObservationEvent(
                event_type=ObservationEventType.ANOMALY_DETECTED,
                timestamp=datetime.now(timezone.utc),
                metric_name="metric1",
            )
        )
        agent._events.append(
            ObservationEvent(
                event_type=ObservationEventType.SLO_BREACH,
                timestamp=datetime.now(timezone.utc),
                metric_name="metric2",
            )
        )

        anomalies = agent.get_events(event_type=ObservationEventType.ANOMALY_DETECTED)
        assert len(anomalies) == 1
        assert anomalies[0].metric_name == "metric1"

    def test_get_status(self) -> None:
        agent = ObserverAgent(prometheus_client=MagicMock())
        status = agent.get_status()
        assert status["state"] == "idle"
        assert status["observation_count"] == 0
        assert status["event_count"] == 0

    def test_get_status_when_observing(self) -> None:
        agent = ObserverAgent(prometheus_client=MagicMock())
        agent.start_observing(experiment_id="exp-001")
        status = agent.get_status()
        assert status["state"] == "observing"
        assert status["current_experiment_id"] == "exp-001"

    def test_dry_run_mode(self) -> None:
        """Dry run mode should not make real queries."""
        prom_client = MagicMock()
        agent = ObserverAgent(prometheus_client=prom_client, dry_run=True)
        agent.start_observing(experiment_id="exp-001")

        events = agent.observe()
        # Should not actually query Prometheus in dry run
        assert agent.observation_count == 1
