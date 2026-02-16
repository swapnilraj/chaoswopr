"""Observer Agent for real-time anomaly detection and analysis.

The Observer Agent monitors streaming metrics from Prometheus, detects anomalies,
monitors SLO breaches, and performs root cause analysis using LLM + RAG.

State machine:
  IDLE -> OBSERVING -> ANALYZING -> REPORTING -> OBSERVING (loop)

The Observer operates independently of other agents and provides a continuous
stream of observations during experiments.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient


class ObserverState(str, Enum):
    """State of the Observer Agent."""

    IDLE = "idle"
    OBSERVING = "observing"
    ANALYZING = "analyzing"
    REPORTING = "reporting"


class ObservationEventType(str, Enum):
    """Types of observation events."""

    ANOMALY_DETECTED = "anomaly_detected"
    SLO_BREACH = "slo_breach"
    ROOT_CAUSE_HYPOTHESIS = "root_cause_hypothesis"
    RECOVERY_OBSERVED = "recovery_observed"
    OBSERVATION_START = "observation_start"
    OBSERVATION_END = "observation_end"


@dataclass
class ObservationEvent:
    """An observation event from the Observer Agent.

    Attributes:
        event_type: Type of observation event.
        timestamp: When the event occurred.
        metric_name: Name of the metric related to this event.
        severity: Severity level (info, warning, critical).
        details: Additional event-specific details.
        experiment_id: Associated experiment ID.
    """

    event_type: ObservationEventType
    timestamp: datetime
    metric_name: str | None = None
    severity: str = "info"
    details: dict[str, Any] = field(default_factory=dict)
    experiment_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "metric_name": self.metric_name,
            "severity": self.severity,
            "details": self.details,
            "experiment_id": self.experiment_id,
        }


class ObserverAgent:
    """Observer Agent for real-time monitoring and analysis.

    The Observer continuously monitors metrics, detects anomalies using
    statistical methods, checks for SLO breaches, and generates root cause
    hypotheses using LLM + RAG when issues are detected.

    Examples:
        >>> from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient
        >>> prom_client = PrometheusClient(base_url="http://localhost:9090")
        >>> observer = ObserverAgent(prometheus_client=prom_client)
        >>> observer.start_observing(experiment_id="exp-001")
        >>> events = observer.observe()  # Run one observation cycle
        >>> observer.stop_observing()
    """

    def __init__(
        self,
        prometheus_client: PrometheusClient,
        anomaly_detector: Any | None = None,
        slo_monitor: Any | None = None,
        rca_engine: Any | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the Observer Agent.

        Args:
            prometheus_client: Prometheus client for querying metrics.
            anomaly_detector: Anomaly detection module (optional, will auto-create if None).
            slo_monitor: SLO monitoring module (optional, will auto-create if None).
            rca_engine: Root cause analysis engine (optional, will auto-create if None).
            dry_run: If True, don't actually query metrics.
        """
        self._prometheus = prometheus_client
        self._dry_run = dry_run

        # Auto-create components if not provided
        if anomaly_detector is None:
            from chaoswopr.agents.anomaly_detection import AnomalyDetector

            anomaly_detector = AnomalyDetector()

        if slo_monitor is None:
            from chaoswopr.agents.slo_monitor import SLOMonitor

            slo_monitor = SLOMonitor()

        if rca_engine is None:
            from chaoswopr.agents.rca_engine import RCAEngine

            rca_engine = RCAEngine(dry_run=dry_run)

        self._anomaly_detector = anomaly_detector
        self._slo_monitor = slo_monitor
        self._rca_engine = rca_engine

        # State
        self._state = ObserverState.IDLE
        self._current_experiment_id: str | None = None
        self._observation_count = 0
        self._events: list[ObservationEvent] = []
        self._last_observation_time: datetime | None = None

        # Metrics to observe (can be configured)
        self._observed_metrics = [
            "finality_delay_seconds",
            "participation_rate_percent",
            "slashing_rate_percent",
            "attestation_inclusion_delay",
            "block_proposal_rate",
        ]

    @property
    def state(self) -> ObserverState:
        """Get the current state."""
        return self._state

    @property
    def current_experiment_id(self) -> str | None:
        """Get the current experiment ID."""
        return self._current_experiment_id

    @property
    def observation_count(self) -> int:
        """Get the total number of observations performed."""
        return self._observation_count

    def start_observing(self, experiment_id: str) -> None:
        """Start observing an experiment.

        Args:
            experiment_id: ID of the experiment to observe.

        Raises:
            RuntimeError: If already observing.
        """
        if self._state != ObserverState.IDLE:
            raise RuntimeError(
                f"Cannot start observing: already observing experiment "
                f"{self._current_experiment_id}"
            )

        self._state = ObserverState.OBSERVING
        self._current_experiment_id = experiment_id
        self._observation_count = 0

        # Record observation start event
        event = ObservationEvent(
            event_type=ObservationEventType.OBSERVATION_START,
            timestamp=datetime.now(timezone.utc),
            experiment_id=experiment_id,
            details={"metrics": self._observed_metrics},
        )
        self._events.append(event)

    def stop_observing(self) -> None:
        """Stop observing the current experiment."""
        if self._state == ObserverState.IDLE:
            return

        # Record observation end event
        event = ObservationEvent(
            event_type=ObservationEventType.OBSERVATION_END,
            timestamp=datetime.now(timezone.utc),
            experiment_id=self._current_experiment_id,
            details={
                "observation_count": self._observation_count,
                "event_count": len([e for e in self._events if e.experiment_id == self._current_experiment_id]),
            },
        )
        self._events.append(event)

        self._state = ObserverState.IDLE
        self._current_experiment_id = None

    def observe(self) -> list[ObservationEvent]:
        """Run one observation cycle.

        Queries current metrics, runs anomaly detection, checks SLO breaches,
        and performs root cause analysis if needed.

        Returns:
            List of observation events detected in this cycle.
        """
        if self._state == ObserverState.IDLE:
            return []

        now = datetime.now(timezone.utc)
        self._last_observation_time = now
        self._observation_count += 1

        new_events: list[ObservationEvent] = []

        # In dry run mode, just increment count and return
        if self._dry_run:
            return new_events

        # Query current metrics
        current_metrics = self._query_metrics()

        # Run anomaly detection
        if self._anomaly_detector:
            anomalies = self._anomaly_detector.detect(current_metrics)
            for anomaly in anomalies:
                event = ObservationEvent(
                    event_type=ObservationEventType.ANOMALY_DETECTED,
                    timestamp=now,
                    metric_name=anomaly.get("metric_name"),
                    severity=anomaly.get("severity", "warning"),
                    details=anomaly,
                    experiment_id=self._current_experiment_id,
                )
                new_events.append(event)
                self._events.append(event)

        # Check SLO breaches
        if self._slo_monitor:
            breaches = self._slo_monitor.check_breaches(current_metrics)
            for breach in breaches:
                event = ObservationEvent(
                    event_type=ObservationEventType.SLO_BREACH,
                    timestamp=now,
                    metric_name=breach.get("metric_name"),
                    severity="critical",
                    details=breach,
                    experiment_id=self._current_experiment_id,
                )
                new_events.append(event)
                self._events.append(event)

        # Perform root cause analysis if anomalies or breaches detected
        if new_events and self._rca_engine:
            self._state = ObserverState.ANALYZING
            try:
                rca_result = self._rca_engine.analyze(
                    events=new_events,
                    metrics=current_metrics,
                    experiment_id=self._current_experiment_id,
                )
                if rca_result:
                    event = ObservationEvent(
                        event_type=ObservationEventType.ROOT_CAUSE_HYPOTHESIS,
                        timestamp=datetime.now(timezone.utc),
                        severity="info",
                        details=rca_result,
                        experiment_id=self._current_experiment_id,
                    )
                    new_events.append(event)
                    self._events.append(event)
            finally:
                self._state = ObserverState.OBSERVING

        return new_events

    def get_events(
        self,
        event_type: ObservationEventType | None = None,
        experiment_id: str | None = None,
    ) -> list[ObservationEvent]:
        """Get observation events.

        Args:
            event_type: Optional filter by event type.
            experiment_id: Optional filter by experiment ID.

        Returns:
            List of matching observation events.
        """
        events = self._events

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if experiment_id:
            events = [e for e in events if e.experiment_id == experiment_id]

        return events

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the Observer Agent.

        Returns:
            Dictionary with state, observation count, and event summary.
        """
        return {
            "state": self._state.value,
            "current_experiment_id": self._current_experiment_id,
            "observation_count": self._observation_count,
            "event_count": len(self._events),
            "last_observation_time": (
                self._last_observation_time.isoformat()
                if self._last_observation_time
                else None
            ),
        }

    def _query_metrics(self) -> dict[str, float]:
        """Query current metric values from Prometheus.

        Returns:
            Dictionary of metric_name -> current_value.
        """
        metrics: dict[str, float] = {}

        for metric_name in self._observed_metrics:
            result = self._prometheus.query(metric_name)
            if result.success:
                value = result.get_value()
                if value is not None:
                    metrics[metric_name] = value

        return metrics
