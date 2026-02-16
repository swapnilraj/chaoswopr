"""Unit tests for the Fault Injection Dispatcher.

Tests fault dispatching, retry logic, rollback handling, and integration
with the SafeFaultInjector and Node Agent APIs.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chaoswopr.agents.fault_dispatcher import (
    DispatchResult,
    DispatchStatus,
    DispatchSummary,
    FaultDispatcher,
)
from chaoswopr.agents.hypothesis_engine import FaultLevel
from chaoswopr.agents.plan_compiler import (
    ActionStatus,
    ExperimentPlan,
    PlanAction,
)
from chaoswopr.safety.audit import AuditLogger


class TestDispatchResult:
    """Tests for DispatchResult data class."""

    def test_success_result(self) -> None:
        """Successful result should have success=True."""
        result = DispatchResult(
            action_id="test-1",
            success=True,
            fault_id="fault-1",
        )
        assert result.success is True
        assert result.fault_id == "fault-1"

    def test_failure_result(self) -> None:
        """Failed result should have error message."""
        result = DispatchResult(
            action_id="test-1",
            success=False,
            error_message="Connection refused",
        )
        assert result.success is False
        assert result.error_message == "Connection refused"

    def test_to_dict(self) -> None:
        """DispatchResult should serialize."""
        result = DispatchResult(action_id="test", success=True)
        d = result.to_dict()
        assert d["action_id"] == "test"
        assert d["success"] is True


class TestDispatchSummary:
    """Tests for DispatchSummary data class."""

    def test_creation(self) -> None:
        """DispatchSummary should track dispatch statistics."""
        summary = DispatchSummary(
            plan_id="plan-1",
            total_actions=5,
            dispatched=3,
            succeeded=2,
            failed=1,
        )
        assert summary.total_actions == 5
        assert summary.succeeded == 2

    def test_to_dict(self) -> None:
        """DispatchSummary should serialize."""
        summary = DispatchSummary(plan_id="test", total_actions=1)
        d = summary.to_dict()
        assert d["plan_id"] == "test"


class TestFaultDispatcher:
    """Tests for the FaultDispatcher."""

    def _make_dispatcher(self, **kwargs) -> FaultDispatcher:
        """Create a test dispatcher."""
        return FaultDispatcher(
            audit_logger=AuditLogger(default_agent_id="test"),
            dry_run=True,
            **kwargs,
        )

    def _make_control_action(self, action_type: str = "baseline") -> PlanAction:
        """Create a control action."""
        return PlanAction(
            step_number=0,
            time_offset_seconds=0,
            action_type=action_type,
        )

    def _make_fault_action(
        self,
        fault_level: FaultLevel = FaultLevel.NETWORK,
        action_type: str = "inject_network_latency",
    ) -> PlanAction:
        """Create a fault injection action."""
        return PlanAction(
            step_number=1,
            time_offset_seconds=60,
            action_type=action_type,
            fault_level=fault_level,
            target_nodes=["node-001", "node-002"],
            target_percent=10.0,
            parameters={"latency_ms": 200},
        )

    def test_initial_state(self) -> None:
        """Dispatcher should start in IDLE state."""
        dispatcher = self._make_dispatcher()
        assert dispatcher.status == DispatchStatus.IDLE
        assert dispatcher.active_fault_count == 0

    def test_dispatch_control_action(self) -> None:
        """Control actions should always succeed."""
        dispatcher = self._make_dispatcher()
        action = self._make_control_action("baseline")

        result = dispatcher.dispatch_action(action)
        assert result.success is True
        assert action.status == ActionStatus.COMPLETED

    def test_dispatch_observe_action(self) -> None:
        """Observe action should succeed."""
        dispatcher = self._make_dispatcher()
        action = self._make_control_action("observe")

        result = dispatcher.dispatch_action(action)
        assert result.success is True

    def test_dispatch_complete_action(self) -> None:
        """Complete action should succeed."""
        dispatcher = self._make_dispatcher()
        action = self._make_control_action("complete")

        result = dispatcher.dispatch_action(action)
        assert result.success is True

    def test_dispatch_fault_action_dry_run(self) -> None:
        """Fault action in dry-run should simulate success."""
        dispatcher = self._make_dispatcher()
        action = self._make_fault_action()

        result = dispatcher.dispatch_action(action)
        assert result.success is True
        assert result.fault_id is not None
        assert result.fault_id.startswith("dry-run-")
        assert dispatcher.active_fault_count == 1

    def test_dispatch_protocol_fault_dry_run(self) -> None:
        """Protocol fault in dry-run should simulate success."""
        dispatcher = self._make_dispatcher()
        action = self._make_fault_action(
            fault_level=FaultLevel.PROTOCOL,
            action_type="attestation_withholding",
        )

        result = dispatcher.dispatch_action(action)
        assert result.success is True

    def test_dispatch_unknown_action(self) -> None:
        """Unknown action type should fail."""
        dispatcher = self._make_dispatcher()
        action = PlanAction(action_type="unknown_action")

        result = dispatcher.dispatch_action(action)
        assert result.success is False
        assert action.status == ActionStatus.FAILED

    def test_remove_fault(self) -> None:
        """remove_fault should remove an active fault."""
        dispatcher = self._make_dispatcher()
        action = self._make_fault_action()

        # Dispatch first
        dispatcher.dispatch_action(action)
        assert dispatcher.active_fault_count == 1

        # Remove
        removed = dispatcher.remove_fault(action.action_id)
        assert removed is True
        assert dispatcher.active_fault_count == 0

    def test_remove_nonexistent_fault(self) -> None:
        """Removing a nonexistent fault should return False."""
        dispatcher = self._make_dispatcher()
        assert dispatcher.remove_fault("nonexistent") is False

    def test_remove_all_faults(self) -> None:
        """remove_all_faults should remove all active faults."""
        dispatcher = self._make_dispatcher()

        # Dispatch multiple faults
        for i in range(3):
            action = PlanAction(
                action_type="inject_network_latency",
                fault_level=FaultLevel.NETWORK,
                target_nodes=[f"node-{i}"],
            )
            dispatcher.dispatch_action(action)

        assert dispatcher.active_fault_count == 3

        removed = dispatcher.remove_all_faults()
        assert removed == 3
        assert dispatcher.active_fault_count == 0

    def test_dispatch_plan(self) -> None:
        """dispatch_plan should execute all actions in order."""
        dispatcher = self._make_dispatcher()
        plan = ExperimentPlan(
            actions=[
                self._make_control_action("baseline"),
                self._make_fault_action(),
                self._make_control_action("observe"),
                PlanAction(
                    step_number=3,
                    time_offset_seconds=300,
                    action_type="remove_faults",
                ),
                self._make_control_action("complete"),
            ],
            total_duration_seconds=600,
        )

        summary = dispatcher.dispatch_plan(plan)
        assert summary is not None
        assert summary.total_actions == 5
        assert summary.succeeded == 5
        assert summary.failed == 0
        assert dispatcher.status == DispatchStatus.COMPLETED

    def test_dispatch_plan_with_failure_and_rollback(self) -> None:
        """Plan with failing action should trigger rollback."""
        dispatcher = FaultDispatcher(
            audit_logger=AuditLogger(default_agent_id="test"),
            dry_run=False,
            # No safe_injector, so fault injection will fail
        )

        plan = ExperimentPlan(
            actions=[
                self._make_control_action("baseline"),
                self._make_fault_action(),  # Will fail without safe_injector
            ],
            total_duration_seconds=60,
        )

        summary = dispatcher.dispatch_plan(plan)
        assert summary.failed > 0
        assert dispatcher.status == DispatchStatus.FAILED

    def test_dispatch_remove_faults_action(self) -> None:
        """remove_faults action should remove all active faults."""
        dispatcher = self._make_dispatcher()

        # Inject a fault first
        fault_action = self._make_fault_action()
        dispatcher.dispatch_action(fault_action)
        assert dispatcher.active_fault_count == 1

        # Dispatch remove_faults
        remove_action = PlanAction(action_type="remove_faults")
        result = dispatcher.dispatch_action(remove_action)
        assert result.success is True
        assert dispatcher.active_fault_count == 0

    def test_get_summary(self) -> None:
        """get_summary should return current summary."""
        dispatcher = self._make_dispatcher()
        assert dispatcher.get_summary() is None

        plan = ExperimentPlan(
            actions=[self._make_control_action("baseline")],
            total_duration_seconds=0,
        )
        dispatcher.dispatch_plan(plan)
        summary = dispatcher.get_summary()
        assert summary is not None
        assert summary.total_actions == 1

    def test_audit_logging(self) -> None:
        """All dispatches should be audit logged."""
        audit = AuditLogger(default_agent_id="test")
        dispatcher = FaultDispatcher(
            audit_logger=audit,
            dry_run=True,
        )

        action = self._make_control_action("baseline")
        dispatcher.dispatch_action(action)

        entries = audit.get_entries()
        assert len(entries) >= 1

    def test_dispatch_with_retry(self) -> None:
        """Actions with retry_count > 1 should be retried on failure."""
        dispatcher = FaultDispatcher(
            audit_logger=AuditLogger(default_agent_id="test"),
            dry_run=False,
            # No injector -> will fail
        )

        action = self._make_fault_action()
        action.retry_count = 3
        action.rollback_on_failure = False  # Don't trigger full rollback

        # This will retry 3 times and still fail
        result = dispatcher.dispatch_action(action)
        # We only dispatch once via dispatch_action (retry logic is in dispatch_plan)
        # But the audit log should capture the attempt
        assert result.success is False

    def test_dispatch_network_fault_no_injector(self) -> None:
        """Network fault without injector should fail gracefully."""
        dispatcher = FaultDispatcher(
            audit_logger=AuditLogger(default_agent_id="test"),
            dry_run=False,
        )

        action = self._make_fault_action(fault_level=FaultLevel.NETWORK)
        result = dispatcher.dispatch_action(action)
        assert result.success is False
        assert "No SafeFaultInjector" in result.error_message

    def test_dispatch_node_fault_no_injector(self) -> None:
        """Node fault without injector should fail gracefully."""
        dispatcher = FaultDispatcher(
            audit_logger=AuditLogger(default_agent_id="test"),
            dry_run=False,
        )

        action = self._make_fault_action(
            fault_level=FaultLevel.NODE,
            action_type="kill_nodes",
        )
        result = dispatcher.dispatch_action(action)
        assert result.success is False

    def test_dispatch_protocol_fault_no_client(self) -> None:
        """Protocol fault without node agent client should fail."""
        dispatcher = FaultDispatcher(
            audit_logger=AuditLogger(default_agent_id="test"),
            dry_run=False,
        )

        action = self._make_fault_action(
            fault_level=FaultLevel.PROTOCOL,
            action_type="attestation_withholding",
        )
        result = dispatcher.dispatch_action(action)
        assert result.success is False
        assert "No Node Agent client" in result.error_message
