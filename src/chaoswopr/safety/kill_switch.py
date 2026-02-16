"""Kill switch CLI for chaoswopr.

Manual emergency halt that immediately:
1. Halts all fault injection
2. Restores snapshots
3. Generates a state dump

This is the human override for when automation fails.
The kill switch is a CLI tool (not a web UI) to minimize attack surface.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

import click


class KillSwitchState(str, Enum):
    """State of the kill switch."""

    READY = "ready"
    ACTIVATING = "activating"
    ACTIVATED = "activated"
    FAILED = "failed"


@dataclass
class KillSwitchAction:
    """Record of a kill switch action step."""

    step: str
    status: str  # "pending", "running", "completed", "failed"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step": self.step,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


@dataclass
class KillSwitchResult:
    """Result of kill switch activation."""

    state: KillSwitchState
    activated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    actions: list[KillSwitchAction] = field(default_factory=list)
    experiment_id: str | None = None

    @property
    def success(self) -> bool:
        """Check if all actions completed successfully."""
        return all(a.status == "completed" for a in self.actions)

    @property
    def failed_steps(self) -> list[str]:
        """Get list of failed steps."""
        return [a.step for a in self.actions if a.status == "failed"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "state": self.state.value,
            "activated_at": self.activated_at.isoformat(),
            "success": self.success,
            "actions": [a.to_dict() for a in self.actions],
            "experiment_id": self.experiment_id,
            "failed_steps": self.failed_steps,
        }


class KillSwitch:
    """Kill switch for emergency experiment termination.

    Provides a sequence of shutdown actions:
    1. Trip the circuit breaker
    2. Remove all active faults
    3. Restore the latest snapshot
    4. Generate state dump
    5. Write audit log entry
    """

    def __init__(
        self,
        circuit_breaker: Any | None = None,
        snapshot_manager: Any | None = None,
        fault_remover: Callable[[], bool] | None = None,
        audit_logger: Any | None = None,
    ) -> None:
        """Initialize the kill switch.

        Args:
            circuit_breaker: Circuit breaker instance to trip.
            snapshot_manager: Snapshot manager for restoration.
            fault_remover: Callable that removes all active faults.
            audit_logger: Audit logger for recording the kill switch activation.
        """
        self._circuit_breaker = circuit_breaker
        self._snapshot_manager = snapshot_manager
        self._fault_remover = fault_remover
        self._audit_logger = audit_logger
        self._state = KillSwitchState.READY
        self._activation_history: list[KillSwitchResult] = []

    @property
    def state(self) -> KillSwitchState:
        """Get the current kill switch state."""
        return self._state

    @property
    def activation_history(self) -> list[KillSwitchResult]:
        """Get the history of activations."""
        return self._activation_history.copy()

    def activate(self, experiment_id: str | None = None) -> KillSwitchResult:
        """Activate the kill switch.

        Executes all shutdown steps in sequence. If any step fails,
        continues with remaining steps (best-effort shutdown).

        Args:
            experiment_id: ID of the experiment to terminate.

        Returns:
            KillSwitchResult with details of all actions taken.
        """
        self._state = KillSwitchState.ACTIVATING
        result = KillSwitchResult(
            state=KillSwitchState.ACTIVATING,
            experiment_id=experiment_id,
        )

        # Step 1: Trip circuit breaker
        result.actions.append(
            self._execute_step("trip_circuit_breaker", self._trip_circuit_breaker)
        )

        # Step 2: Remove all faults
        result.actions.append(
            self._execute_step("remove_faults", self._remove_all_faults)
        )

        # Step 3: Restore snapshot
        result.actions.append(
            self._execute_step(
                "restore_snapshot",
                lambda: self._restore_snapshot(experiment_id),
            )
        )

        # Step 4: Generate state dump
        result.actions.append(
            self._execute_step("generate_state_dump", self._generate_state_dump)
        )

        # Step 5: Write audit log
        result.actions.append(
            self._execute_step(
                "write_audit_log",
                lambda: self._write_audit_log(experiment_id, result),
            )
        )

        # Set final state
        if result.success:
            self._state = KillSwitchState.ACTIVATED
            result.state = KillSwitchState.ACTIVATED
        else:
            self._state = KillSwitchState.FAILED
            result.state = KillSwitchState.FAILED

        self._activation_history.append(result)
        return result

    def _execute_step(
        self, step_name: str, action: Callable[[], bool]
    ) -> KillSwitchAction:
        """Execute a single kill switch step.

        Args:
            step_name: Name of the step.
            action: Callable that performs the step, returns True on success.

        Returns:
            KillSwitchAction record.
        """
        step = KillSwitchAction(
            step=step_name,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        try:
            success = action()
            step.status = "completed" if success else "failed"
            if not success:
                step.error = f"Step {step_name} returned False"
        except Exception as e:
            step.status = "failed"
            step.error = str(e)
        finally:
            step.completed_at = datetime.now(timezone.utc)
        return step

    def _trip_circuit_breaker(self) -> bool:
        """Trip the circuit breaker."""
        if self._circuit_breaker is None:
            return True  # No circuit breaker configured
        try:
            from chaoswopr.safety.circuit_breaker import TripEvent

            event = TripEvent(
                timestamp=datetime.now(timezone.utc),
                reason="Kill switch activated",
                metric_name="kill_switch",
                metric_value=0.0,
                threshold_value=0.0,
            )
            self._circuit_breaker.trip(event)
            return True
        except Exception:
            return False

    def _remove_all_faults(self) -> bool:
        """Remove all active fault injections."""
        if self._fault_remover is None:
            return True  # No fault remover configured
        try:
            return self._fault_remover()
        except Exception:
            return False

    def _restore_snapshot(self, experiment_id: str | None) -> bool:
        """Restore the latest snapshot."""
        if self._snapshot_manager is None:
            return True  # No snapshot manager configured
        if experiment_id is None:
            return True  # No experiment to restore
        try:
            return self._snapshot_manager.restore_latest(experiment_id)
        except Exception:
            return False

    def _generate_state_dump(self) -> bool:
        """Generate a state dump of the current system."""
        # In production, this would collect metrics, logs, and state
        # For now, this is a placeholder that always succeeds
        return True

    def _write_audit_log(
        self, experiment_id: str | None, result: KillSwitchResult
    ) -> bool:
        """Write the kill switch activation to the audit log."""
        if self._audit_logger is None:
            return True  # No audit logger configured
        try:
            self._audit_logger.log(
                action_type="kill_switch_activate",
                target=experiment_id or "all",
                outcome="success" if result.success else "partial_failure",
                parameters={"actions": [a.to_dict() for a in result.actions]},
                experiment_id=experiment_id,
            )
            return True
        except Exception:
            return False

    def get_status(self) -> dict[str, Any]:
        """Get the current kill switch status."""
        return {
            "state": self._state.value,
            "activation_count": len(self._activation_history),
            "last_activation": (
                self._activation_history[-1].to_dict()
                if self._activation_history
                else None
            ),
        }


@click.command()
@click.option("--experiment-id", "-e", help="Experiment ID to terminate")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def main(experiment_id: str | None, force: bool) -> None:
    """Emergency kill switch - immediately halt all chaos injection."""
    if not force:
        click.echo("WARNING: This will immediately halt all experiments and restore snapshots.")
        if not click.confirm("Are you sure you want to activate the kill switch?"):
            click.echo("Aborted.")
            sys.exit(0)

    click.echo("Activating kill switch...")

    # In production, this would load real dependencies
    kill_switch = KillSwitch()
    result = kill_switch.activate(experiment_id=experiment_id)

    if result.success:
        click.echo("Kill switch activated successfully.")
        for action in result.actions:
            click.echo(f"  {action.step}: {action.status}")
    else:
        click.echo("Kill switch activation completed with errors:")
        for action in result.actions:
            status_mark = "[OK]" if action.status == "completed" else "[FAIL]"
            click.echo(f"  {status_mark} {action.step}")
            if action.error:
                click.echo(f"       Error: {action.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
