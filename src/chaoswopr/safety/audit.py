"""Audit log infrastructure for chaoswopr.

Provides a structured logging client that all components use to record
agent decisions and actions. Logs are written to both PostgreSQL (for querying)
and S3 (for tamper-evident storage).

Audit log schema:
- timestamp: When the action occurred
- agent_id: Which agent performed the action
- action_type: What type of action was performed
- target: What was the target of the action
- parameters: Action-specific parameters
- outcome: Result of the action (success, failure, etc.)
- trace_id: Unique trace ID for correlating related events
- experiment_id: Associated experiment (optional)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    """Standard action types for audit logging."""

    # Experiment lifecycle
    EXPERIMENT_CREATE = "experiment_create"
    EXPERIMENT_START = "experiment_start"
    EXPERIMENT_COMPLETE = "experiment_complete"
    EXPERIMENT_FAIL = "experiment_fail"
    EXPERIMENT_ABORT = "experiment_abort"

    # Fault injection
    FAULT_INJECT = "fault_inject"
    FAULT_REMOVE = "fault_remove"
    FAULT_ESCALATE = "fault_escalate"

    # Safety
    CIRCUIT_BREAKER_CHECK = "circuit_breaker_check"
    CIRCUIT_BREAKER_TRIP = "circuit_breaker_trip"
    CIRCUIT_BREAKER_RESET = "circuit_breaker_reset"
    BLAST_RADIUS_CHECK = "blast_radius_check"
    BLAST_RADIUS_VIOLATION = "blast_radius_violation"
    KILL_SWITCH_ACTIVATE = "kill_switch_activate"

    # Snapshots
    SNAPSHOT_CREATE = "snapshot_create"
    SNAPSHOT_RESTORE = "snapshot_restore"
    SNAPSHOT_DELETE = "snapshot_delete"

    # Monitoring
    METRIC_ANOMALY = "metric_anomaly"
    SLO_BREACH = "slo_breach"
    ALERT_FIRE = "alert_fire"

    # Agent decisions
    HYPOTHESIS_GENERATE = "hypothesis_generate"
    PLAN_CREATE = "plan_create"
    DECISION_MAKE = "decision_make"


class Outcome(str, Enum):
    """Standard outcomes for audit logging."""

    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


class AuditEntry:
    """A single audit log entry.

    Immutable after creation to maintain audit integrity.
    """

    def __init__(
        self,
        agent_id: str,
        action_type: str | ActionType,
        target: str,
        outcome: str | Outcome,
        parameters: dict[str, Any] | None = None,
        experiment_id: str | None = None,
        trace_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Create a new audit entry.

        Args:
            agent_id: ID of the agent performing the action.
            action_type: Type of action being performed.
            target: Target of the action.
            outcome: Result of the action.
            parameters: Action-specific parameters.
            experiment_id: Associated experiment ID.
            trace_id: Trace ID for event correlation.
            timestamp: When the action occurred (defaults to now).
        """
        self._timestamp = timestamp or datetime.now(timezone.utc)
        self._agent_id = agent_id
        self._action_type = action_type.value if isinstance(action_type, ActionType) else action_type
        self._target = target
        self._outcome = outcome.value if isinstance(outcome, Outcome) else outcome
        self._parameters = parameters or {}
        self._experiment_id = experiment_id
        self._trace_id = trace_id or str(uuid.uuid4())

    @property
    def timestamp(self) -> datetime:
        return self._timestamp

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def action_type(self) -> str:
        return self._action_type

    @property
    def target(self) -> str:
        return self._target

    @property
    def outcome(self) -> str:
        return self._outcome

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters.copy()

    @property
    def experiment_id(self) -> str | None:
        return self._experiment_id

    @property
    def trace_id(self) -> str:
        return self._trace_id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self._timestamp.isoformat(),
            "agent_id": self._agent_id,
            "action_type": self._action_type,
            "target": self._target,
            "outcome": self._outcome,
            "parameters": self._parameters,
            "experiment_id": self._experiment_id,
            "trace_id": self._trace_id,
        }


class AuditLogger:
    """Audit logger client used by all chaoswopr components.

    Collects audit entries and can flush them to storage backends
    (PostgreSQL and S3). Supports buffered writes for performance.
    """

    def __init__(
        self,
        default_agent_id: str = "unknown",
        buffer_size: int = 100,
    ) -> None:
        """Initialize the audit logger.

        Args:
            default_agent_id: Default agent ID for entries.
            buffer_size: Maximum entries to buffer before auto-flush.
        """
        self._default_agent_id = default_agent_id
        self._buffer_size = buffer_size
        self._buffer: list[AuditEntry] = []
        self._flushed_entries: list[AuditEntry] = []
        self._flush_callbacks: list[Any] = []

    @property
    def buffer(self) -> list[AuditEntry]:
        """Get the current buffer of unflushed entries."""
        return self._buffer.copy()

    @property
    def buffer_count(self) -> int:
        """Get the number of entries in the buffer."""
        return len(self._buffer)

    @property
    def total_entries(self) -> int:
        """Get the total number of entries logged (flushed + buffered)."""
        return len(self._flushed_entries) + len(self._buffer)

    def register_flush_callback(self, callback: Any) -> None:
        """Register a callback for flush events.

        The callback receives a list of AuditEntry objects.

        Args:
            callback: Function to call on flush.
        """
        self._flush_callbacks.append(callback)

    def log(
        self,
        action_type: str | ActionType,
        target: str,
        outcome: str | Outcome,
        agent_id: str | None = None,
        parameters: dict[str, Any] | None = None,
        experiment_id: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEntry:
        """Log an audit entry.

        Args:
            action_type: Type of action.
            target: Target of the action.
            outcome: Result of the action.
            agent_id: Agent performing the action (defaults to logger default).
            parameters: Action-specific parameters.
            experiment_id: Associated experiment ID.
            trace_id: Trace ID for correlation.

        Returns:
            The created AuditEntry.
        """
        entry = AuditEntry(
            agent_id=agent_id or self._default_agent_id,
            action_type=action_type,
            target=target,
            outcome=outcome,
            parameters=parameters,
            experiment_id=experiment_id,
            trace_id=trace_id,
        )
        self._buffer.append(entry)

        # Auto-flush if buffer is full
        if len(self._buffer) >= self._buffer_size:
            self.flush()

        return entry

    def flush(self) -> list[AuditEntry]:
        """Flush all buffered entries to storage.

        Returns:
            List of flushed entries.
        """
        if not self._buffer:
            return []

        entries = self._buffer.copy()
        self._buffer.clear()
        self._flushed_entries.extend(entries)

        # Invoke callbacks
        for callback in self._flush_callbacks:
            try:
                callback(entries)
            except Exception:
                pass  # Callbacks must not prevent logging

        return entries

    def get_entries(
        self,
        agent_id: str | None = None,
        action_type: str | None = None,
        experiment_id: str | None = None,
    ) -> list[AuditEntry]:
        """Query logged entries (both flushed and buffered).

        Args:
            agent_id: Filter by agent ID.
            action_type: Filter by action type.
            experiment_id: Filter by experiment ID.

        Returns:
            List of matching AuditEntry objects.
        """
        all_entries = self._flushed_entries + self._buffer
        results = all_entries

        if agent_id:
            results = [e for e in results if e.agent_id == agent_id]
        if action_type:
            at = action_type.value if isinstance(action_type, ActionType) else action_type
            results = [e for e in results if e.action_type == at]
        if experiment_id:
            results = [e for e in results if e.experiment_id == experiment_id]

        return results
