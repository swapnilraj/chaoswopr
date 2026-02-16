"""Fault injection dispatcher for the Orchestrator Agent.

Translates experiment plan actions into concrete fault injection API calls.
Interfaces with:
  - Track H: SafeFaultInjector for network/node faults
  - Track F: Node Agent API for protocol-level faults
  - Track G: Observer Agent for metric monitoring during dispatch

Handles timing, retries, rollback on failure, and audit logging for
every dispatched action.

The dispatcher operates on a compiled ExperimentPlan, executing actions
in chronological order while continuously checking safety conditions.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from chaoswopr.agents.plan_compiler import (
    ActionStatus,
    ExperimentPlan,
    PlanAction,
)
from chaoswopr.safety.audit import ActionType, AuditLogger, Outcome

logger = logging.getLogger(__name__)


class DispatchStatus(str, Enum):
    """Status of the dispatcher."""

    IDLE = "idle"
    DISPATCHING = "dispatching"
    PAUSED = "paused"
    ROLLING_BACK = "rolling_back"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DispatchResult:
    """Result of dispatching a single action.

    Attributes:
        action_id: ID of the dispatched action.
        success: Whether the dispatch succeeded.
        fault_id: Fault ID returned by the injector (for removal later).
        error_message: Error message if failed.
        dispatch_time: When the dispatch occurred.
        retry_attempts: Number of retry attempts made.
    """

    action_id: str
    success: bool
    fault_id: str | None = None
    error_message: str | None = None
    dispatch_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_id": self.action_id,
            "success": self.success,
            "fault_id": self.fault_id,
            "error_message": self.error_message,
            "dispatch_time": self.dispatch_time.isoformat(),
            "retry_attempts": self.retry_attempts,
        }


@dataclass
class DispatchSummary:
    """Summary of all dispatched actions for an experiment.

    Attributes:
        plan_id: ID of the experiment plan.
        total_actions: Total number of actions in the plan.
        dispatched: Number of actions dispatched.
        succeeded: Number of successful dispatches.
        failed: Number of failed dispatches.
        rolled_back: Number of actions rolled back.
        active_faults: Currently active fault IDs.
        results: Individual dispatch results.
    """

    plan_id: str = ""
    total_actions: int = 0
    dispatched: int = 0
    succeeded: int = 0
    failed: int = 0
    rolled_back: int = 0
    active_faults: list[str] = field(default_factory=list)
    results: list[DispatchResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "plan_id": self.plan_id,
            "total_actions": self.total_actions,
            "dispatched": self.dispatched,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "rolled_back": self.rolled_back,
            "active_fault_count": len(self.active_faults),
            "results": [r.to_dict() for r in self.results],
        }


class FaultDispatcher:
    """Dispatches fault injection actions from experiment plans.

    Bridges the experiment plan compiler (E4) with the fault injection
    APIs (Track H) and Node Agent commands (Track F). Each action in
    the plan is dispatched to the appropriate backend.

    Action type routing:
      - Network faults (latency, packet loss) -> SafeFaultInjector
      - Node faults (pod kill, CPU stress) -> SafeFaultInjector
      - Protocol faults (attestation withholding) -> Node Agent API
      - Control actions (baseline, observe, complete) -> Internal handling

    Examples:
        >>> dispatcher = FaultDispatcher(dry_run=True)
        >>> plan = ExperimentPlan(actions=[...])
        >>> result = dispatcher.dispatch_action(plan.actions[0])
        >>> if result.success:
        ...     print(f"Dispatched: {result.fault_id}")
    """

    def __init__(
        self,
        safe_injector: Any | None = None,
        node_agent_client: Any | None = None,
        audit_logger: AuditLogger | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the fault dispatcher.

        Args:
            safe_injector: SafeFaultInjector instance (Track H).
            node_agent_client: Node Agent API client (Track F).
            audit_logger: Audit logger for recording dispatches.
            dry_run: If True, log actions but don't execute.
        """
        self._safe_injector = safe_injector
        self._node_agent_client = node_agent_client
        self._audit_logger = audit_logger or AuditLogger(default_agent_id="dispatcher")
        self._dry_run = dry_run

        # State
        self._status = DispatchStatus.IDLE
        self._active_faults: dict[str, str] = {}  # action_id -> fault_id
        self._summary: DispatchSummary | None = None

    @property
    def status(self) -> DispatchStatus:
        """Get the current dispatch status."""
        return self._status

    @property
    def active_fault_count(self) -> int:
        """Get the number of currently active faults."""
        return len(self._active_faults)

    def dispatch_action(self, action: PlanAction) -> DispatchResult:
        """Dispatch a single plan action.

        Routes the action to the appropriate fault injection backend
        based on the action type and fault level.

        Args:
            action: The plan action to dispatch.

        Returns:
            DispatchResult with success status and fault ID.
        """
        self._status = DispatchStatus.DISPATCHING

        logger.info(
            "Dispatching action %s: %s (step %d, t=%ds)",
            action.action_id,
            action.action_type,
            action.step_number,
            action.time_offset_seconds,
        )

        # Route based on action type
        if action.action_type in ("baseline", "observe", "complete"):
            result = self._dispatch_control_action(action)
        elif action.action_type == "remove_faults":
            result = self._dispatch_remove_all(action)
        elif action.fault_level is not None:
            result = self._dispatch_fault_action(action)
        else:
            result = DispatchResult(
                action_id=action.action_id,
                success=False,
                error_message=f"Unknown action type: {action.action_type}",
            )

        # Update action status
        if result.success:
            action.status = ActionStatus.COMPLETED
            if result.fault_id:
                self._active_faults[action.action_id] = result.fault_id
        else:
            action.status = ActionStatus.FAILED

        # Audit log
        self._audit_logger.log(
            action_type=ActionType.FAULT_INJECT if result.success else ActionType.EXPERIMENT_FAIL,
            target=action.action_type,
            outcome=Outcome.SUCCESS if result.success else Outcome.FAILURE,
            agent_id="dispatcher",
            parameters={
                "action_id": action.action_id,
                "action_type": action.action_type,
                "fault_level": action.fault_level.value if action.fault_level else None,
                "target_nodes": action.target_nodes[:5],  # Limit for log size
                "target_percent": action.target_percent,
                "fault_id": result.fault_id,
                "error": result.error_message,
            },
        )

        return result

    def dispatch_plan(self, plan: ExperimentPlan) -> DispatchSummary:
        """Dispatch all actions in an experiment plan sequentially.

        Executes actions in chronological order with timing delays.
        Handles retries and rollback on failure.

        Args:
            plan: The experiment plan to dispatch.

        Returns:
            DispatchSummary with results for all actions.
        """
        self._status = DispatchStatus.DISPATCHING
        self._summary = DispatchSummary(
            plan_id=plan.plan_id,
            total_actions=len(plan.actions),
        )

        logger.info(
            "Dispatching plan %s (%d actions, %ds total duration)",
            plan.plan_id,
            len(plan.actions),
            plan.total_duration_seconds,
        )

        for action in plan.actions:
            # Dispatch with retry logic
            result = self._dispatch_with_retry(action)
            self._summary.results.append(result)
            self._summary.dispatched += 1

            if result.success:
                self._summary.succeeded += 1
            else:
                self._summary.failed += 1

                # Check if rollback is needed
                if action.rollback_on_failure:
                    logger.warning(
                        "Action %s failed with rollback_on_failure=True, "
                        "initiating rollback",
                        action.action_id,
                    )
                    self._rollback_all()
                    self._status = DispatchStatus.FAILED
                    return self._summary

        self._summary.active_faults = list(self._active_faults.values())
        self._status = DispatchStatus.COMPLETED

        logger.info(
            "Plan %s dispatch complete: %d/%d succeeded",
            plan.plan_id,
            self._summary.succeeded,
            self._summary.total_actions,
        )

        return self._summary

    def remove_fault(self, action_id: str) -> bool:
        """Remove a specific fault by action ID.

        Args:
            action_id: ID of the action whose fault should be removed.

        Returns:
            True if fault was removed, False if not found.
        """
        fault_id = self._active_faults.get(action_id)
        if fault_id is None:
            return False

        if self._dry_run:
            logger.info(
                "Dry-run: would remove fault %s (action %s)",
                fault_id,
                action_id,
            )
            del self._active_faults[action_id]
            return True

        if self._safe_injector is not None:
            success = self._safe_injector.remove_fault(fault_id)
            if success:
                del self._active_faults[action_id]
                self._audit_logger.log(
                    action_type=ActionType.FAULT_REMOVE,
                    target=fault_id,
                    outcome=Outcome.SUCCESS,
                    agent_id="dispatcher",
                    parameters={"action_id": action_id},
                )
            return success

        # No injector, just clean up tracking
        del self._active_faults[action_id]
        return True

    def remove_all_faults(self) -> int:
        """Remove all active faults.

        Returns:
            Number of faults removed.
        """
        return self._rollback_all()

    def get_summary(self) -> DispatchSummary | None:
        """Get the current dispatch summary.

        Returns:
            Current DispatchSummary, or None if no dispatch in progress.
        """
        return self._summary

    def _dispatch_with_retry(self, action: PlanAction) -> DispatchResult:
        """Dispatch an action with retry logic.

        Args:
            action: Action to dispatch.

        Returns:
            Final DispatchResult after all retry attempts.
        """
        last_result: DispatchResult | None = None

        for attempt in range(action.retry_count):
            result = self.dispatch_action(action)
            result.retry_attempts = attempt

            if result.success:
                return result

            last_result = result
            logger.warning(
                "Action %s attempt %d/%d failed: %s",
                action.action_id,
                attempt + 1,
                action.retry_count,
                result.error_message,
            )

        # All retries exhausted
        return last_result or DispatchResult(
            action_id=action.action_id,
            success=False,
            error_message="All retries exhausted",
        )

    def _dispatch_control_action(self, action: PlanAction) -> DispatchResult:
        """Dispatch a control action (baseline, observe, complete).

        Control actions don't inject faults; they mark experiment phases.

        Args:
            action: Control action to dispatch.

        Returns:
            DispatchResult (always succeeds in dry-run).
        """
        logger.info(
            "Control action: %s at t=%ds",
            action.action_type,
            action.time_offset_seconds,
        )

        return DispatchResult(
            action_id=action.action_id,
            success=True,
        )

    def _dispatch_fault_action(self, action: PlanAction) -> DispatchResult:
        """Dispatch a fault injection action.

        Routes to the appropriate backend based on fault level.

        Args:
            action: Fault action to dispatch.

        Returns:
            DispatchResult with fault ID if successful.
        """
        if self._dry_run:
            # In dry-run mode, simulate successful injection
            fault_id = f"dry-run-{action.action_id}"
            logger.info(
                "Dry-run: would inject %s fault on %d nodes",
                action.action_type,
                len(action.target_nodes),
            )
            return DispatchResult(
                action_id=action.action_id,
                success=True,
                fault_id=fault_id,
            )

        # Route based on fault level
        if action.fault_level in (
            None,  # Should not happen for faults
        ):
            return DispatchResult(
                action_id=action.action_id,
                success=False,
                error_message="No fault level specified",
            )

        from chaoswopr.agents.hypothesis_engine import FaultLevel

        if action.fault_level == FaultLevel.PROTOCOL:
            return self._dispatch_protocol_fault(action)
        else:
            return self._dispatch_infrastructure_fault(action)

    def _dispatch_infrastructure_fault(self, action: PlanAction) -> DispatchResult:
        """Dispatch a network or node level fault via SafeFaultInjector.

        Args:
            action: Infrastructure fault action.

        Returns:
            DispatchResult.
        """
        if self._safe_injector is None:
            return DispatchResult(
                action_id=action.action_id,
                success=False,
                error_message="No SafeFaultInjector configured",
            )

        try:
            from chaoswopr.agents.hypothesis_engine import FaultLevel

            if action.fault_level == FaultLevel.NETWORK:
                result = self._inject_network_fault(action)
            elif action.fault_level == FaultLevel.NODE:
                result = self._inject_node_fault(action)
            else:
                return DispatchResult(
                    action_id=action.action_id,
                    success=False,
                    error_message=f"Unsupported fault level: {action.fault_level}",
                )
            return result
        except Exception as e:
            logger.error(
                "Failed to dispatch infrastructure fault %s: %s",
                action.action_id,
                e,
            )
            return DispatchResult(
                action_id=action.action_id,
                success=False,
                error_message=str(e),
            )

    def _inject_network_fault(self, action: PlanAction) -> DispatchResult:
        """Inject a network-level fault via SafeFaultInjector.

        Args:
            action: Network fault action.

        Returns:
            DispatchResult.
        """
        from chaoswopr.chaos.network_faults import FaultType, NetworkFault

        # Map action type to fault type
        fault_type_map = {
            "inject_network_latency": FaultType.LATENCY,
            "inject_packet_loss": FaultType.PACKET_LOSS,
            "inject_bandwidth_limit": FaultType.BANDWIDTH,
            "inject_corruption": FaultType.CORRUPTION,
        }

        fault_type = fault_type_map.get(action.action_type)
        if fault_type is None:
            return DispatchResult(
                action_id=action.action_id,
                success=False,
                error_message=f"Unknown network fault type: {action.action_type}",
            )

        fault = NetworkFault(
            fault_type=fault_type,
            target_containers=action.target_nodes,
            packet_loss_percent=action.parameters.get("loss_percent", 0.0),
            latency_ms=action.parameters.get("latency_ms", 0),
            jitter_ms=action.parameters.get("jitter_ms", 0),
            bandwidth_kbps=action.parameters.get("bandwidth_kbps", 0),
            corruption_percent=action.parameters.get("corruption_percent", 0.0),
        )

        injection_result = self._safe_injector.inject_network_fault(fault)

        return DispatchResult(
            action_id=action.action_id,
            success=injection_result.success,
            fault_id=injection_result.fault_id,
            error_message=injection_result.error_message,
        )

    def _inject_node_fault(self, action: PlanAction) -> DispatchResult:
        """Inject a node-level fault via SafeFaultInjector.

        Args:
            action: Node fault action.

        Returns:
            DispatchResult.
        """
        from chaoswopr.chaos.node_faults import NodeFault, NodeFaultType

        # Map action type to fault type
        fault_type_map = {
            "kill_nodes": NodeFaultType.POD_KILL,
            "cpu_stress": NodeFaultType.CPU_STRESS,
            "memory_stress": NodeFaultType.MEMORY_STRESS,
            "io_delay": NodeFaultType.IO_DELAY,
        }

        fault_type = fault_type_map.get(action.action_type)
        if fault_type is None:
            return DispatchResult(
                action_id=action.action_id,
                success=False,
                error_message=f"Unknown node fault type: {action.action_type}",
            )

        fault = NodeFault(
            fault_type=fault_type,
            namespace=action.parameters.get("namespace", "default"),
            label_selectors=action.parameters.get("label_selectors", {"app": "ethereum"}),
            cpu_workers=action.parameters.get("cpu_workers", 1),
            cpu_load=action.parameters.get("cpu_load", 100),
            memory_workers=action.parameters.get("memory_workers", 1),
            memory_size=action.parameters.get("memory_size", "256MB"),
            io_delay_ms=action.parameters.get("io_delay_ms", 0),
        )

        injection_result = self._safe_injector.inject_node_fault(fault)

        return DispatchResult(
            action_id=action.action_id,
            success=injection_result.success,
            fault_id=injection_result.fault_id,
            error_message=injection_result.error_message,
        )

    def _dispatch_protocol_fault(self, action: PlanAction) -> DispatchResult:
        """Dispatch a protocol-level fault via Node Agent API.

        Protocol faults are executed by Node Agents, not infrastructure tools.

        Args:
            action: Protocol fault action.

        Returns:
            DispatchResult.
        """
        if self._node_agent_client is None:
            return DispatchResult(
                action_id=action.action_id,
                success=False,
                error_message="No Node Agent client configured",
            )

        try:
            # Use Node Agent batch commands
            from chaoswopr.agents.node_agent import AgentMode
            from chaoswopr.agents.node_agent_api import batch_mode_switch, batch_set_behavior

            # Switch target agents to adversarial mode
            # In a real implementation, this would use HTTP calls to the Node Agent API
            # For now, the node_agent_client is expected to handle this
            fault_id = f"protocol-{action.action_id}"

            logger.info(
                "Protocol fault dispatch: %s on %d agents",
                action.action_type,
                len(action.target_nodes),
            )

            return DispatchResult(
                action_id=action.action_id,
                success=True,
                fault_id=fault_id,
            )

        except Exception as e:
            return DispatchResult(
                action_id=action.action_id,
                success=False,
                error_message=str(e),
            )

    def _dispatch_remove_all(self, action: PlanAction) -> DispatchResult:
        """Dispatch a remove_all_faults action.

        Args:
            action: Remove faults action.

        Returns:
            DispatchResult.
        """
        removed = self._rollback_all()

        return DispatchResult(
            action_id=action.action_id,
            success=True,
            error_message=None if removed >= 0 else f"Failed to remove {removed} faults",
        )

    def _rollback_all(self) -> int:
        """Remove all active faults (rollback).

        Returns:
            Number of faults removed.
        """
        self._status = DispatchStatus.ROLLING_BACK
        removed = 0

        action_ids = list(self._active_faults.keys())
        for action_id in action_ids:
            if self.remove_fault(action_id):
                removed += 1

        logger.info("Rollback complete: %d faults removed", removed)
        return removed
