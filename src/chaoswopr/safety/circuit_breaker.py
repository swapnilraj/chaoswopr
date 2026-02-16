"""Circuit breaker framework for chaoswopr.

Implements a standalone circuit breaker service that monitors Prometheus
alert conditions and automatically halts experiments when safety thresholds
are breached.

States: ARMED -> TRIPPED -> RESET
- ARMED: Normal operation, monitoring thresholds
- TRIPPED: Safety threshold breached, experiment halted
- RESET: Manually reset after investigation

The circuit breaker is a standalone service (not embedded in agents)
so it functions even if the agent system crashes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class CircuitBreakerState(str, Enum):
    """State of the circuit breaker."""

    ARMED = "armed"
    TRIPPED = "tripped"
    RESET = "reset"


@dataclass
class ThresholdConfig:
    """Thresholds that trigger the circuit breaker.

    Attributes:
        finality_delay_max_seconds: Trip if finality delay exceeds this.
        slashing_rate_max_percent: Trip if slashing rate exceeds this.
        participation_rate_min_percent: Trip if participation drops below this.
    """

    finality_delay_max_seconds: float = 600.0  # 10 minutes
    slashing_rate_max_percent: float = 5.0
    participation_rate_min_percent: float = 66.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThresholdConfig:
        """Create from dictionary."""
        return cls(
            finality_delay_max_seconds=data.get("finality_delay_max_seconds", 600.0),
            slashing_rate_max_percent=data.get("slashing_rate_max_percent", 5.0),
            participation_rate_min_percent=data.get("participation_rate_min_percent", 66.0),
        )

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "finality_delay_max_seconds": self.finality_delay_max_seconds,
            "slashing_rate_max_percent": self.slashing_rate_max_percent,
            "participation_rate_min_percent": self.participation_rate_min_percent,
        }


@dataclass
class TripEvent:
    """Record of a circuit breaker trip event."""

    timestamp: datetime
    reason: str
    metric_name: str
    metric_value: float
    threshold_value: float
    experiment_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold_value": self.threshold_value,
            "experiment_id": self.experiment_id,
        }


class CircuitBreaker:
    """Circuit breaker that monitors metrics and trips on safety violations.

    The circuit breaker polls metric values (from Prometheus or other sources)
    and transitions to TRIPPED state when any threshold is breached. Once
    tripped, it stays tripped until manually reset.

    Callbacks can be registered for trip events to trigger automated responses
    (experiment halt, snapshot, notification, etc.).
    """

    def __init__(
        self,
        thresholds: ThresholdConfig | None = None,
        on_trip: Callable[[TripEvent], None] | None = None,
    ) -> None:
        """Initialize the circuit breaker.

        Args:
            thresholds: Threshold configuration for trip conditions.
            on_trip: Callback function invoked when the breaker trips.
        """
        self._thresholds = thresholds or ThresholdConfig()
        self._state = CircuitBreakerState.ARMED
        self._trip_events: list[TripEvent] = []
        self._last_check: datetime | None = None
        self._check_count = 0
        self._on_trip = on_trip
        self._trip_callbacks: list[Callable[[TripEvent], None]] = []
        if on_trip:
            self._trip_callbacks.append(on_trip)

    @property
    def state(self) -> CircuitBreakerState:
        """Get the current circuit breaker state."""
        return self._state

    @property
    def is_tripped(self) -> bool:
        """Check if the circuit breaker is in TRIPPED state."""
        return self._state == CircuitBreakerState.TRIPPED

    @property
    def is_armed(self) -> bool:
        """Check if the circuit breaker is in ARMED state."""
        return self._state == CircuitBreakerState.ARMED

    @property
    def thresholds(self) -> ThresholdConfig:
        """Get the threshold configuration."""
        return self._thresholds

    @property
    def trip_events(self) -> list[TripEvent]:
        """Get the list of trip events."""
        return self._trip_events.copy()

    @property
    def last_check(self) -> datetime | None:
        """Get the timestamp of the last check."""
        return self._last_check

    @property
    def check_count(self) -> int:
        """Get the total number of checks performed."""
        return self._check_count

    def register_trip_callback(self, callback: Callable[[TripEvent], None]) -> None:
        """Register a callback for trip events.

        Args:
            callback: Function to call when the breaker trips.
        """
        self._trip_callbacks.append(callback)

    def arm(self) -> None:
        """Arm the circuit breaker (enable monitoring).

        Transitions from RESET to ARMED state.
        """
        if self._state == CircuitBreakerState.TRIPPED:
            raise RuntimeError(
                "Cannot arm a tripped circuit breaker. Reset first."
            )
        self._state = CircuitBreakerState.ARMED

    def reset(self) -> None:
        """Reset the circuit breaker after a trip.

        Transitions from TRIPPED to RESET state.
        """
        self._state = CircuitBreakerState.RESET

    def trip(self, event: TripEvent) -> None:
        """Manually trip the circuit breaker.

        Args:
            event: The trip event details.
        """
        self._state = CircuitBreakerState.TRIPPED
        self._trip_events.append(event)

        # Invoke all registered callbacks
        for callback in self._trip_callbacks:
            try:
                callback(event)
            except Exception:
                # Callbacks must not prevent the trip
                pass

    def check_metrics(
        self,
        metrics: dict[str, float],
        experiment_id: str | None = None,
    ) -> bool:
        """Check current metrics against thresholds.

        Args:
            metrics: Dictionary of metric_name -> current_value.
                Expected keys: finality_delay_seconds, slashing_rate_percent,
                participation_rate_percent.
            experiment_id: ID of the current experiment (for trip event logging).

        Returns:
            True if all metrics are within thresholds, False if tripped.
        """
        now = datetime.now(timezone.utc)
        self._last_check = now
        self._check_count += 1

        # If already tripped, stay tripped
        if self._state == CircuitBreakerState.TRIPPED:
            return False

        # If not armed, skip checks
        if self._state != CircuitBreakerState.ARMED:
            return True

        # Check finality delay
        finality_delay = metrics.get("finality_delay_seconds")
        if finality_delay is not None and finality_delay > self._thresholds.finality_delay_max_seconds:
            event = TripEvent(
                timestamp=now,
                reason=f"Finality delay {finality_delay:.1f}s exceeds threshold "
                f"{self._thresholds.finality_delay_max_seconds:.1f}s",
                metric_name="finality_delay_seconds",
                metric_value=finality_delay,
                threshold_value=self._thresholds.finality_delay_max_seconds,
                experiment_id=experiment_id,
            )
            self.trip(event)
            return False

        # Check slashing rate
        slashing_rate = metrics.get("slashing_rate_percent")
        if slashing_rate is not None and slashing_rate > self._thresholds.slashing_rate_max_percent:
            event = TripEvent(
                timestamp=now,
                reason=f"Slashing rate {slashing_rate:.1f}% exceeds threshold "
                f"{self._thresholds.slashing_rate_max_percent:.1f}%",
                metric_name="slashing_rate_percent",
                metric_value=slashing_rate,
                threshold_value=self._thresholds.slashing_rate_max_percent,
                experiment_id=experiment_id,
            )
            self.trip(event)
            return False

        # Check participation rate
        participation_rate = metrics.get("participation_rate_percent")
        if (
            participation_rate is not None
            and participation_rate < self._thresholds.participation_rate_min_percent
        ):
            event = TripEvent(
                timestamp=now,
                reason=f"Participation rate {participation_rate:.1f}% below threshold "
                f"{self._thresholds.participation_rate_min_percent:.1f}%",
                metric_name="participation_rate_percent",
                metric_value=participation_rate,
                threshold_value=self._thresholds.participation_rate_min_percent,
                experiment_id=experiment_id,
            )
            self.trip(event)
            return False

        return True

    def get_status(self) -> dict[str, Any]:
        """Get the full status of the circuit breaker.

        Returns:
            Dictionary with current state, thresholds, and trip history.
        """
        return {
            "state": self._state.value,
            "thresholds": self._thresholds.to_dict(),
            "check_count": self._check_count,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "trip_count": len(self._trip_events),
            "trip_events": [e.to_dict() for e in self._trip_events],
        }
