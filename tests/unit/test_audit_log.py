"""Unit tests for the audit log infrastructure."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from chaoswopr.safety.audit import (
    ActionType,
    AuditEntry,
    AuditLogger,
    Outcome,
)


class TestActionType:
    """Tests for the ActionType enum."""

    def test_experiment_actions(self) -> None:
        assert ActionType.EXPERIMENT_CREATE.value == "experiment_create"
        assert ActionType.EXPERIMENT_START.value == "experiment_start"
        assert ActionType.EXPERIMENT_COMPLETE.value == "experiment_complete"

    def test_safety_actions(self) -> None:
        assert ActionType.CIRCUIT_BREAKER_TRIP.value == "circuit_breaker_trip"
        assert ActionType.KILL_SWITCH_ACTIVATE.value == "kill_switch_activate"
        assert ActionType.BLAST_RADIUS_VIOLATION.value == "blast_radius_violation"


class TestOutcome:
    """Tests for the Outcome enum."""

    def test_outcomes(self) -> None:
        assert Outcome.SUCCESS.value == "success"
        assert Outcome.FAILURE.value == "failure"
        assert Outcome.BLOCKED.value == "blocked"


class TestAuditEntry:
    """Tests for the AuditEntry class."""

    def test_create_entry(self) -> None:
        entry = AuditEntry(
            agent_id="orchestrator",
            action_type=ActionType.EXPERIMENT_START,
            target="testnet-001",
            outcome=Outcome.SUCCESS,
        )
        assert entry.agent_id == "orchestrator"
        assert entry.action_type == "experiment_start"
        assert entry.target == "testnet-001"
        assert entry.outcome == "success"
        assert entry.trace_id is not None
        assert entry.timestamp is not None

    def test_entry_with_string_types(self) -> None:
        entry = AuditEntry(
            agent_id="test",
            action_type="custom_action",
            target="target",
            outcome="custom_outcome",
        )
        assert entry.action_type == "custom_action"
        assert entry.outcome == "custom_outcome"

    def test_entry_with_parameters(self) -> None:
        entry = AuditEntry(
            agent_id="test",
            action_type=ActionType.FAULT_INJECT,
            target="node-1",
            outcome=Outcome.SUCCESS,
            parameters={"latency_ms": 200, "node_percent": 20},
        )
        assert entry.parameters["latency_ms"] == 200

    def test_parameters_are_copied(self) -> None:
        """Modifying returned parameters should not affect the entry."""
        params = {"key": "value"}
        entry = AuditEntry(
            agent_id="test",
            action_type="test",
            target="test",
            outcome="success",
            parameters=params,
        )
        returned_params = entry.parameters
        returned_params["new_key"] = "new_value"
        assert "new_key" not in entry.parameters

    def test_entry_to_dict(self) -> None:
        entry = AuditEntry(
            agent_id="orchestrator",
            action_type=ActionType.EXPERIMENT_START,
            target="testnet-001",
            outcome=Outcome.SUCCESS,
            experiment_id="exp-001",
        )
        d = entry.to_dict()
        assert d["agent_id"] == "orchestrator"
        assert d["action_type"] == "experiment_start"
        assert d["experiment_id"] == "exp-001"
        assert d["trace_id"] is not None
        assert d["timestamp"] is not None

    def test_custom_trace_id(self) -> None:
        entry = AuditEntry(
            agent_id="test",
            action_type="test",
            target="test",
            outcome="success",
            trace_id="custom-trace-id",
        )
        assert entry.trace_id == "custom-trace-id"

    def test_custom_timestamp(self) -> None:
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        entry = AuditEntry(
            agent_id="test",
            action_type="test",
            target="test",
            outcome="success",
            timestamp=ts,
        )
        assert entry.timestamp == ts


class TestAuditLogger:
    """Tests for the AuditLogger."""

    def test_create_logger(self) -> None:
        logger = AuditLogger(default_agent_id="orchestrator")
        assert logger.buffer_count == 0
        assert logger.total_entries == 0

    def test_log_entry(self) -> None:
        logger = AuditLogger(default_agent_id="orchestrator")
        entry = logger.log(
            action_type=ActionType.EXPERIMENT_START,
            target="testnet-001",
            outcome=Outcome.SUCCESS,
        )
        assert entry.agent_id == "orchestrator"
        assert logger.buffer_count == 1

    def test_log_with_custom_agent(self) -> None:
        logger = AuditLogger(default_agent_id="default")
        entry = logger.log(
            action_type="test",
            target="test",
            outcome="success",
            agent_id="custom_agent",
        )
        assert entry.agent_id == "custom_agent"

    def test_flush(self) -> None:
        logger = AuditLogger()
        logger.log("test", "target", "success")
        logger.log("test", "target", "success")
        assert logger.buffer_count == 2

        flushed = logger.flush()
        assert len(flushed) == 2
        assert logger.buffer_count == 0
        assert logger.total_entries == 2

    def test_flush_empty_buffer(self) -> None:
        logger = AuditLogger()
        flushed = logger.flush()
        assert flushed == []

    def test_auto_flush_on_buffer_full(self) -> None:
        logger = AuditLogger(buffer_size=3)
        logger.log("test1", "target", "success")
        logger.log("test2", "target", "success")
        assert logger.buffer_count == 2

        logger.log("test3", "target", "success")
        # Buffer should have been flushed
        assert logger.buffer_count == 0
        assert logger.total_entries == 3

    def test_flush_callback(self) -> None:
        callback = MagicMock()
        logger = AuditLogger()
        logger.register_flush_callback(callback)

        logger.log("test", "target", "success")
        logger.flush()

        assert callback.called
        assert len(callback.call_args[0][0]) == 1

    def test_flush_callback_error_does_not_prevent_flush(self) -> None:
        def bad_callback(entries: list) -> None:
            raise RuntimeError("callback error")

        logger = AuditLogger()
        logger.register_flush_callback(bad_callback)

        logger.log("test", "target", "success")
        flushed = logger.flush()
        assert len(flushed) == 1  # Flush still succeeds

    def test_get_entries_all(self) -> None:
        logger = AuditLogger()
        logger.log("action1", "target1", "success", agent_id="agent1")
        logger.log("action2", "target2", "success", agent_id="agent2")
        entries = logger.get_entries()
        assert len(entries) == 2

    def test_get_entries_by_agent(self) -> None:
        logger = AuditLogger()
        logger.log("test", "target", "success", agent_id="agent1")
        logger.log("test", "target", "success", agent_id="agent2")
        logger.log("test", "target", "success", agent_id="agent1")

        entries = logger.get_entries(agent_id="agent1")
        assert len(entries) == 2

    def test_get_entries_by_action_type(self) -> None:
        logger = AuditLogger()
        logger.log(ActionType.EXPERIMENT_START, "target", "success")
        logger.log(ActionType.FAULT_INJECT, "target", "success")
        logger.log(ActionType.EXPERIMENT_START, "target", "success")

        entries = logger.get_entries(action_type=ActionType.EXPERIMENT_START.value)
        assert len(entries) == 2

    def test_get_entries_by_experiment(self) -> None:
        logger = AuditLogger()
        logger.log("test", "target", "success", experiment_id="exp-001")
        logger.log("test", "target", "success", experiment_id="exp-002")
        logger.log("test", "target", "success", experiment_id="exp-001")

        entries = logger.get_entries(experiment_id="exp-001")
        assert len(entries) == 2

    def test_get_entries_includes_flushed_and_buffered(self) -> None:
        logger = AuditLogger()
        logger.log("test1", "target", "success")
        logger.flush()
        logger.log("test2", "target", "success")

        entries = logger.get_entries()
        assert len(entries) == 2
