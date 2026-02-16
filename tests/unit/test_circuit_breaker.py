"""Unit tests for the circuit breaker framework.

Safety-critical tests ensuring the circuit breaker correctly
detects and responds to threshold violations.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chaoswopr.safety.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    ThresholdConfig,
    TripEvent,
)


class TestThresholdConfig:
    """Tests for ThresholdConfig."""

    def test_default_thresholds(self) -> None:
        config = ThresholdConfig()
        assert config.finality_delay_max_seconds == 600.0
        assert config.slashing_rate_max_percent == 5.0
        assert config.participation_rate_min_percent == 66.0

    def test_custom_thresholds(self) -> None:
        config = ThresholdConfig(
            finality_delay_max_seconds=300.0,
            slashing_rate_max_percent=3.0,
            participation_rate_min_percent=80.0,
        )
        assert config.finality_delay_max_seconds == 300.0
        assert config.slashing_rate_max_percent == 3.0

    def test_from_dict(self) -> None:
        data = {"finality_delay_max_seconds": 900.0, "slashing_rate_max_percent": 10.0}
        config = ThresholdConfig.from_dict(data)
        assert config.finality_delay_max_seconds == 900.0
        assert config.slashing_rate_max_percent == 10.0
        assert config.participation_rate_min_percent == 66.0  # default

    def test_to_dict(self) -> None:
        config = ThresholdConfig()
        d = config.to_dict()
        assert d["finality_delay_max_seconds"] == 600.0
        assert d["slashing_rate_max_percent"] == 5.0
        assert d["participation_rate_min_percent"] == 66.0


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState enum."""

    def test_states(self) -> None:
        assert CircuitBreakerState.ARMED.value == "armed"
        assert CircuitBreakerState.TRIPPED.value == "tripped"
        assert CircuitBreakerState.RESET.value == "reset"


class TestCircuitBreaker:
    """Tests for the CircuitBreaker core logic."""

    def test_initial_state_is_armed(self) -> None:
        breaker = CircuitBreaker()
        assert breaker.state == CircuitBreakerState.ARMED
        assert breaker.is_armed
        assert not breaker.is_tripped

    def test_check_count_starts_at_zero(self) -> None:
        breaker = CircuitBreaker()
        assert breaker.check_count == 0

    @pytest.mark.safety
    def test_healthy_metrics_pass(self) -> None:
        breaker = CircuitBreaker()
        result = breaker.check_metrics({
            "finality_delay_seconds": 13.0,
            "slashing_rate_percent": 0.0,
            "participation_rate_percent": 96.5,
        })
        assert result is True
        assert breaker.is_armed
        assert breaker.check_count == 1

    @pytest.mark.safety
    def test_finality_delay_trips(self) -> None:
        """Circuit breaker must trip when finality delay exceeds threshold."""
        breaker = CircuitBreaker()
        result = breaker.check_metrics({
            "finality_delay_seconds": 700.0,  # > 600s threshold
            "slashing_rate_percent": 0.0,
            "participation_rate_percent": 96.5,
        })
        assert result is False
        assert breaker.is_tripped
        assert len(breaker.trip_events) == 1
        assert "finality" in breaker.trip_events[0].reason.lower()

    @pytest.mark.safety
    def test_slashing_rate_trips(self) -> None:
        """Circuit breaker must trip when slashing rate exceeds threshold."""
        breaker = CircuitBreaker()
        result = breaker.check_metrics({
            "finality_delay_seconds": 13.0,
            "slashing_rate_percent": 6.0,  # > 5% threshold
            "participation_rate_percent": 96.5,
        })
        assert result is False
        assert breaker.is_tripped
        assert "slashing" in breaker.trip_events[0].reason.lower()

    @pytest.mark.safety
    def test_low_participation_trips(self) -> None:
        """Circuit breaker must trip when participation drops below threshold."""
        breaker = CircuitBreaker()
        result = breaker.check_metrics({
            "finality_delay_seconds": 13.0,
            "slashing_rate_percent": 0.0,
            "participation_rate_percent": 50.0,  # < 66% threshold
        })
        assert result is False
        assert breaker.is_tripped
        assert "participation" in breaker.trip_events[0].reason.lower()

    @pytest.mark.safety
    def test_tripped_stays_tripped(self) -> None:
        """Once tripped, subsequent checks should still return False."""
        breaker = CircuitBreaker()
        breaker.check_metrics({"finality_delay_seconds": 700.0})
        assert breaker.is_tripped

        # Even with healthy metrics, stays tripped
        result = breaker.check_metrics({
            "finality_delay_seconds": 13.0,
            "slashing_rate_percent": 0.0,
            "participation_rate_percent": 96.5,
        })
        assert result is False
        assert breaker.is_tripped

    def test_reset_then_arm(self) -> None:
        breaker = CircuitBreaker()
        breaker.check_metrics({"finality_delay_seconds": 700.0})
        assert breaker.is_tripped

        breaker.reset()
        assert breaker.state == CircuitBreakerState.RESET

        breaker.arm()
        assert breaker.is_armed

    def test_cannot_arm_when_tripped(self) -> None:
        breaker = CircuitBreaker()
        breaker.check_metrics({"finality_delay_seconds": 700.0})
        with pytest.raises(RuntimeError, match="Cannot arm"):
            breaker.arm()

    def test_trip_callback_invoked(self) -> None:
        callback = MagicMock()
        breaker = CircuitBreaker(on_trip=callback)
        breaker.check_metrics({"finality_delay_seconds": 700.0})
        assert callback.called
        assert isinstance(callback.call_args[0][0], TripEvent)

    def test_multiple_callbacks(self) -> None:
        callback1 = MagicMock()
        callback2 = MagicMock()
        breaker = CircuitBreaker(on_trip=callback1)
        breaker.register_trip_callback(callback2)
        breaker.check_metrics({"finality_delay_seconds": 700.0})
        assert callback1.called
        assert callback2.called

    def test_callback_exception_does_not_prevent_trip(self) -> None:
        def bad_callback(event: TripEvent) -> None:
            raise RuntimeError("callback error")

        breaker = CircuitBreaker(on_trip=bad_callback)
        breaker.check_metrics({"finality_delay_seconds": 700.0})
        assert breaker.is_tripped  # Still tripped despite callback error

    def test_missing_metrics_pass(self) -> None:
        """Missing metrics should not trigger a trip."""
        breaker = CircuitBreaker()
        result = breaker.check_metrics({})
        assert result is True

    def test_partial_metrics(self) -> None:
        """Only provided metrics should be checked."""
        breaker = CircuitBreaker()
        result = breaker.check_metrics({"finality_delay_seconds": 13.0})
        assert result is True

    def test_custom_thresholds(self) -> None:
        thresholds = ThresholdConfig(finality_delay_max_seconds=30.0)
        breaker = CircuitBreaker(thresholds=thresholds)
        result = breaker.check_metrics({"finality_delay_seconds": 50.0})
        assert result is False

    def test_get_status(self) -> None:
        breaker = CircuitBreaker()
        status = breaker.get_status()
        assert status["state"] == "armed"
        assert status["check_count"] == 0
        assert status["trip_count"] == 0
        assert "thresholds" in status

    def test_get_status_after_trip(self) -> None:
        breaker = CircuitBreaker()
        breaker.check_metrics({"finality_delay_seconds": 700.0})
        status = breaker.get_status()
        assert status["state"] == "tripped"
        assert status["trip_count"] == 1
        assert len(status["trip_events"]) == 1

    def test_experiment_id_in_trip_event(self) -> None:
        breaker = CircuitBreaker()
        breaker.check_metrics(
            {"finality_delay_seconds": 700.0},
            experiment_id="exp-001",
        )
        assert breaker.trip_events[0].experiment_id == "exp-001"

    def test_at_threshold_does_not_trip(self) -> None:
        """Values exactly at the threshold should not trip."""
        breaker = CircuitBreaker()
        result = breaker.check_metrics({
            "finality_delay_seconds": 600.0,  # exactly at threshold
            "slashing_rate_percent": 5.0,  # exactly at threshold
            "participation_rate_percent": 66.0,  # exactly at threshold
        })
        assert result is True

    def test_last_check_updated(self) -> None:
        breaker = CircuitBreaker()
        assert breaker.last_check is None
        breaker.check_metrics({"finality_delay_seconds": 13.0})
        assert breaker.last_check is not None

    @pytest.mark.safety
    def test_reset_not_armed_state(self) -> None:
        """After reset, the breaker is in RESET state, not ARMED."""
        breaker = CircuitBreaker()
        breaker.check_metrics({"finality_delay_seconds": 700.0})
        breaker.reset()
        assert breaker.state == CircuitBreakerState.RESET
        # Must explicitly arm
        result = breaker.check_metrics({"finality_delay_seconds": 700.0})
        assert result is True  # Not armed, so checks are skipped
