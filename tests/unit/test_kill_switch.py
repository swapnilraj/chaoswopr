"""Unit tests for the kill switch CLI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chaoswopr.safety.kill_switch import (
    KillSwitch,
    KillSwitchResult,
    KillSwitchState,
)


class TestKillSwitchState:
    """Tests for KillSwitchState enum."""

    def test_states(self) -> None:
        assert KillSwitchState.READY.value == "ready"
        assert KillSwitchState.ACTIVATING.value == "activating"
        assert KillSwitchState.ACTIVATED.value == "activated"
        assert KillSwitchState.FAILED.value == "failed"


class TestKillSwitch:
    """Tests for the KillSwitch class."""

    def test_initial_state(self) -> None:
        ks = KillSwitch()
        assert ks.state == KillSwitchState.READY
        assert len(ks.activation_history) == 0

    def test_activate_no_dependencies(self) -> None:
        """Kill switch should work even with no components configured."""
        ks = KillSwitch()
        result = ks.activate()
        assert result.success
        assert ks.state == KillSwitchState.ACTIVATED
        assert len(result.actions) == 5

    def test_activate_with_experiment_id(self) -> None:
        ks = KillSwitch()
        result = ks.activate(experiment_id="exp-001")
        assert result.experiment_id == "exp-001"
        assert result.success

    def test_activate_trips_circuit_breaker(self) -> None:
        cb = MagicMock()
        ks = KillSwitch(circuit_breaker=cb)
        result = ks.activate()
        assert cb.trip.called
        assert result.success

    def test_activate_removes_faults(self) -> None:
        remover = MagicMock(return_value=True)
        ks = KillSwitch(fault_remover=remover)
        result = ks.activate()
        assert remover.called
        assert result.success

    def test_activate_restores_snapshot(self) -> None:
        sm = MagicMock()
        sm.restore_latest.return_value = True
        ks = KillSwitch(snapshot_manager=sm)
        result = ks.activate(experiment_id="exp-001")
        sm.restore_latest.assert_called_with("exp-001")
        assert result.success

    def test_activate_writes_audit_log(self) -> None:
        audit = MagicMock()
        ks = KillSwitch(audit_logger=audit)
        result = ks.activate()
        assert audit.log.called

    def test_fault_remover_failure_continues(self) -> None:
        """If fault removal fails, other steps should still execute."""
        remover = MagicMock(side_effect=RuntimeError("fault removal failed"))
        ks = KillSwitch(fault_remover=remover)
        result = ks.activate()
        # Should have failed the fault removal step
        assert not result.success
        assert "remove_faults" in result.failed_steps
        # But other steps should have completed
        non_fault_actions = [a for a in result.actions if a.step != "remove_faults"]
        assert all(a.status == "completed" for a in non_fault_actions)

    def test_circuit_breaker_failure_continues(self) -> None:
        cb = MagicMock()
        cb.trip.side_effect = RuntimeError("cb failed")
        ks = KillSwitch(circuit_breaker=cb)
        result = ks.activate()
        assert "trip_circuit_breaker" in result.failed_steps
        assert ks.state == KillSwitchState.FAILED

    def test_activation_history_tracked(self) -> None:
        ks = KillSwitch()
        ks.activate(experiment_id="exp-001")
        ks.activate(experiment_id="exp-002")
        assert len(ks.activation_history) == 2

    def test_get_status(self) -> None:
        ks = KillSwitch()
        status = ks.get_status()
        assert status["state"] == "ready"
        assert status["activation_count"] == 0
        assert status["last_activation"] is None

    def test_get_status_after_activation(self) -> None:
        ks = KillSwitch()
        ks.activate()
        status = ks.get_status()
        assert status["state"] == "activated"
        assert status["activation_count"] == 1
        assert status["last_activation"] is not None


class TestKillSwitchResult:
    """Tests for KillSwitchResult."""

    def test_success_when_all_completed(self) -> None:
        from chaoswopr.safety.kill_switch import KillSwitchAction

        result = KillSwitchResult(
            state=KillSwitchState.ACTIVATED,
            actions=[
                KillSwitchAction(step="step1", status="completed"),
                KillSwitchAction(step="step2", status="completed"),
            ],
        )
        assert result.success
        assert result.failed_steps == []

    def test_failure_when_step_fails(self) -> None:
        from chaoswopr.safety.kill_switch import KillSwitchAction

        result = KillSwitchResult(
            state=KillSwitchState.FAILED,
            actions=[
                KillSwitchAction(step="step1", status="completed"),
                KillSwitchAction(step="step2", status="failed", error="test error"),
            ],
        )
        assert not result.success
        assert result.failed_steps == ["step2"]

    def test_to_dict(self) -> None:
        result = KillSwitchResult(state=KillSwitchState.ACTIVATED)
        d = result.to_dict()
        assert d["state"] == "activated"
        assert d["success"] is True
        assert "activated_at" in d
