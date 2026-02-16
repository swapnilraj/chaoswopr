"""Experiment plan compiler for the Orchestrator Agent.

Transforms a validated Hypothesis into an executable ExperimentPlan:
an ordered list of concrete actions with timing, monitoring checkpoints,
escalation/de-escalation triggers, and rollback conditions.

The plan compiler is the bridge between the abstract hypothesis and
the concrete fault injection dispatcher. It resolves:
  - Fault timeline into specific API calls (tc/netem, chaos-mesh, Node Agent)
  - Target percentages into concrete node/container lists
  - SLO thresholds into monitoring checkpoint definitions
  - Rollback conditions into circuit breaker configurations

The output ExperimentPlan is deterministic and fully self-contained:
given the same hypothesis and cluster state, the same plan is produced.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from chaoswopr.agents.hypothesis_engine import (
    FaultAction,
    FaultLevel,
    Hypothesis,
)

logger = logging.getLogger(__name__)


class ActionStatus(str, Enum):
    """Execution status of a plan action."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class CheckpointType(str, Enum):
    """Type of monitoring checkpoint."""

    HEALTH_CHECK = "health_check"
    SLO_CHECK = "slo_check"
    CIRCUIT_BREAKER_CHECK = "circuit_breaker_check"
    METRICS_SNAPSHOT = "metrics_snapshot"
    OBSERVATION_WINDOW = "observation_window"


@dataclass
class PlanAction:
    """A single executable action in an experiment plan.

    Each action maps to a concrete API call or monitoring operation.

    Attributes:
        action_id: Unique identifier for this action.
        step_number: Order in the execution sequence.
        time_offset_seconds: When to execute (seconds from plan start).
        action_type: Type of action to execute.
        fault_level: Level (network, node, protocol) or None for non-fault actions.
        target_nodes: Specific node/container identifiers to target.
        target_percent: Percentage of nodes (resolved to target_nodes at dispatch time).
        parameters: Action-specific parameters for the fault injection API.
        description: Human-readable description.
        status: Current execution status.
        retry_count: Number of retries allowed.
        rollback_on_failure: Whether to trigger rollback if this action fails.
        depends_on: Action IDs that must complete before this one.
    """

    action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    step_number: int = 0
    time_offset_seconds: int = 0
    action_type: str = ""
    fault_level: FaultLevel | None = None
    target_nodes: list[str] = field(default_factory=list)
    target_percent: float = 0.0
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    status: ActionStatus = ActionStatus.PENDING
    retry_count: int = 1
    rollback_on_failure: bool = True
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_id": self.action_id,
            "step_number": self.step_number,
            "time_offset_seconds": self.time_offset_seconds,
            "action_type": self.action_type,
            "fault_level": self.fault_level.value if self.fault_level else None,
            "target_nodes": self.target_nodes,
            "target_percent": self.target_percent,
            "parameters": self.parameters,
            "description": self.description,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "rollback_on_failure": self.rollback_on_failure,
            "depends_on": self.depends_on,
        }


@dataclass
class MonitoringCheckpoint:
    """A monitoring checkpoint within the experiment plan.

    Checkpoints define when to check metrics, SLOs, and circuit breaker
    state during experiment execution.

    Attributes:
        checkpoint_id: Unique identifier.
        checkpoint_type: Type of monitoring check.
        time_offset_seconds: When to execute this check.
        metrics_to_check: List of metric names to query.
        thresholds: Threshold values for pass/fail determination.
        abort_on_failure: Whether to abort the experiment if this check fails.
        description: Human-readable description.
    """

    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    checkpoint_type: CheckpointType = CheckpointType.HEALTH_CHECK
    time_offset_seconds: int = 0
    metrics_to_check: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    abort_on_failure: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_type": self.checkpoint_type.value,
            "time_offset_seconds": self.time_offset_seconds,
            "metrics_to_check": self.metrics_to_check,
            "thresholds": self.thresholds,
            "abort_on_failure": self.abort_on_failure,
            "description": self.description,
        }


@dataclass
class RollbackCondition:
    """A condition that triggers automatic experiment rollback.

    Attributes:
        condition_id: Unique identifier.
        metric_name: Metric to monitor for this condition.
        comparison: Comparison operator ("greater_than", "less_than").
        threshold: Threshold value that triggers rollback.
        description: Human-readable description.
    """

    condition_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    metric_name: str = ""
    comparison: str = "greater_than"
    threshold: float = 0.0
    description: str = ""

    def is_triggered(self, current_value: float) -> bool:
        """Check if this rollback condition is triggered.

        Args:
            current_value: Current metric value.

        Returns:
            True if rollback should be triggered.
        """
        if self.comparison == "greater_than":
            return current_value > self.threshold
        elif self.comparison == "less_than":
            return current_value < self.threshold
        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "condition_id": self.condition_id,
            "metric_name": self.metric_name,
            "comparison": self.comparison,
            "threshold": self.threshold,
            "description": self.description,
        }


@dataclass
class ExperimentPlan:
    """A fully compiled, executable experiment plan.

    This is the output of the plan compiler and the input to the fault
    injection dispatcher. It contains all information needed to execute
    the experiment without further interpretation.

    Attributes:
        plan_id: Unique identifier.
        hypothesis_id: ID of the source hypothesis.
        scenario_name: Name of the source scenario.
        actions: Ordered list of executable actions.
        checkpoints: Monitoring checkpoints throughout the experiment.
        rollback_conditions: Conditions that trigger automatic rollback.
        total_duration_seconds: Total planned experiment duration.
        blast_radius_percent: Maximum blast radius for this plan.
        created_at: When the plan was compiled.
    """

    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    hypothesis_id: str = ""
    scenario_name: str = ""
    actions: list[PlanAction] = field(default_factory=list)
    checkpoints: list[MonitoringCheckpoint] = field(default_factory=list)
    rollback_conditions: list[RollbackCondition] = field(default_factory=list)
    total_duration_seconds: int = 0
    blast_radius_percent: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get_pending_actions(self) -> list[PlanAction]:
        """Get all actions that haven't been executed yet.

        Returns:
            List of pending actions in execution order.
        """
        return [a for a in self.actions if a.status == ActionStatus.PENDING]

    def get_next_action(self) -> PlanAction | None:
        """Get the next action to execute.

        Returns:
            Next pending action, or None if all done.
        """
        pending = self.get_pending_actions()
        return pending[0] if pending else None

    def get_actions_at_time(self, elapsed_seconds: float) -> list[PlanAction]:
        """Get actions scheduled at or before a given time.

        Args:
            elapsed_seconds: Seconds elapsed since plan start.

        Returns:
            List of actions due for execution.
        """
        return [
            a for a in self.actions
            if a.status == ActionStatus.PENDING
            and a.time_offset_seconds <= elapsed_seconds
        ]

    def get_checkpoints_at_time(self, elapsed_seconds: float) -> list[MonitoringCheckpoint]:
        """Get monitoring checkpoints due at a given time.

        Args:
            elapsed_seconds: Seconds elapsed since plan start.

        Returns:
            List of checkpoints due for execution.
        """
        return [
            c for c in self.checkpoints
            if c.time_offset_seconds <= elapsed_seconds
        ]

    def is_complete(self) -> bool:
        """Check if all actions have been executed.

        Returns:
            True if no pending actions remain.
        """
        return all(
            a.status in (ActionStatus.COMPLETED, ActionStatus.SKIPPED, ActionStatus.ROLLED_BACK)
            for a in self.actions
        )

    def mark_action_complete(self, action_id: str) -> bool:
        """Mark an action as completed.

        Args:
            action_id: ID of the action to mark.

        Returns:
            True if action was found and marked.
        """
        for action in self.actions:
            if action.action_id == action_id:
                action.status = ActionStatus.COMPLETED
                return True
        return False

    def mark_action_failed(self, action_id: str) -> bool:
        """Mark an action as failed.

        Args:
            action_id: ID of the action to mark.

        Returns:
            True if action was found and marked.
        """
        for action in self.actions:
            if action.action_id == action_id:
                action.status = ActionStatus.FAILED
                return True
        return False

    def validate(self) -> list[str]:
        """Validate the experiment plan.

        Returns:
            List of validation error messages.
        """
        errors: list[str] = []

        if not self.actions:
            errors.append("Plan must have at least one action")

        if self.blast_radius_percent > 33.0:
            errors.append(
                f"blast_radius_percent {self.blast_radius_percent}% exceeds safety limit"
            )

        # Check action ordering
        for i in range(1, len(self.actions)):
            if self.actions[i].time_offset_seconds < self.actions[i - 1].time_offset_seconds:
                errors.append(
                    f"Actions not in chronological order: step {i} "
                    f"({self.actions[i].time_offset_seconds}s) < "
                    f"step {i-1} ({self.actions[i-1].time_offset_seconds}s)"
                )
                break

        # Check that rollback conditions have valid metrics
        for rc in self.rollback_conditions:
            if not rc.metric_name:
                errors.append(f"Rollback condition {rc.condition_id} has no metric_name")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "plan_id": self.plan_id,
            "hypothesis_id": self.hypothesis_id,
            "scenario_name": self.scenario_name,
            "actions": [a.to_dict() for a in self.actions],
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "rollback_conditions": [r.to_dict() for r in self.rollback_conditions],
            "total_duration_seconds": self.total_duration_seconds,
            "blast_radius_percent": self.blast_radius_percent,
            "created_at": self.created_at.isoformat(),
        }


class PlanCompiler:
    """Compiles hypotheses into executable experiment plans.

    Transforms the abstract fault timeline from a Hypothesis into
    concrete PlanActions with specific API calls, monitoring checkpoints,
    and rollback conditions.

    The compilation process:
    1. Convert each FaultAction into a PlanAction with resolved parameters
    2. Insert monitoring checkpoints between actions
    3. Generate rollback conditions from expected metrics
    4. Calculate total experiment duration
    5. Validate the complete plan

    Examples:
        >>> from chaoswopr.agents.hypothesis_engine import HypothesisEngine
        >>> engine = HypothesisEngine(dry_run=True)
        >>> hypothesis = engine.generate(scenario={"name": "test"})
        >>> compiler = PlanCompiler()
        >>> plan = compiler.compile(hypothesis)
        >>> errors = plan.validate()
        >>> assert not errors
    """

    def __init__(
        self,
        total_nodes: int = 50,
        checkpoint_interval_seconds: int = 30,
        dry_run: bool = False,
    ) -> None:
        """Initialize the plan compiler.

        Args:
            total_nodes: Total number of nodes in the testnet.
            checkpoint_interval_seconds: How often to insert monitoring checkpoints.
            dry_run: If True, produce plans without resolving node lists.
        """
        self._total_nodes = total_nodes
        self._checkpoint_interval = checkpoint_interval_seconds
        self._dry_run = dry_run
        self._compiled_count = 0

    @property
    def compiled_count(self) -> int:
        """Get the total number of plans compiled."""
        return self._compiled_count

    def compile(
        self,
        hypothesis: Hypothesis,
        available_nodes: list[str] | None = None,
    ) -> ExperimentPlan:
        """Compile a hypothesis into an executable experiment plan.

        Args:
            hypothesis: Validated hypothesis to compile.
            available_nodes: List of available node identifiers.
                If None, uses placeholder node IDs.

        Returns:
            A validated ExperimentPlan ready for execution.

        Raises:
            ValueError: If the hypothesis has validation errors.
        """
        # Validate hypothesis first
        errors = hypothesis.validate()
        if errors:
            raise ValueError(
                f"Cannot compile invalid hypothesis: {errors}"
            )

        # Create plan
        plan = ExperimentPlan(
            hypothesis_id=hypothesis.hypothesis_id,
            scenario_name=hypothesis.scenario_name,
            blast_radius_percent=hypothesis.blast_radius_percent,
        )

        # Compile fault actions into plan actions
        available = available_nodes or self._generate_placeholder_nodes()
        plan.actions = self._compile_actions(
            hypothesis.fault_timeline,
            available_nodes=available,
        )

        # Generate monitoring checkpoints
        plan.checkpoints = self._generate_checkpoints(
            hypothesis=hypothesis,
            plan_actions=plan.actions,
        )

        # Generate rollback conditions from expected metrics
        plan.rollback_conditions = self._generate_rollback_conditions(hypothesis)

        # Calculate total duration
        if plan.actions:
            plan.total_duration_seconds = max(
                a.time_offset_seconds for a in plan.actions
            )

        # Validate the compiled plan
        plan_errors = plan.validate()
        if plan_errors:
            logger.warning(
                "Compiled plan has validation errors: %s", plan_errors
            )

        self._compiled_count += 1

        logger.info(
            "Compiled plan %s from hypothesis %s (%d actions, %d checkpoints, %ds duration)",
            plan.plan_id,
            hypothesis.hypothesis_id,
            len(plan.actions),
            len(plan.checkpoints),
            plan.total_duration_seconds,
        )

        return plan

    def _compile_actions(
        self,
        fault_timeline: list[FaultAction],
        available_nodes: list[str],
    ) -> list[PlanAction]:
        """Compile fault actions into plan actions.

        Args:
            fault_timeline: Fault actions from hypothesis.
            available_nodes: Available node identifiers.

        Returns:
            List of compiled PlanActions.
        """
        actions: list[PlanAction] = []

        for i, fault_action in enumerate(fault_timeline):
            # Resolve target nodes from percentage
            target_nodes = self._resolve_targets(
                target_percent=fault_action.target_percent,
                available_nodes=available_nodes,
                fault_level=fault_action.fault_level,
            )

            # Map fault action to concrete API parameters
            parameters = self._resolve_parameters(fault_action)

            plan_action = PlanAction(
                step_number=i,
                time_offset_seconds=fault_action.time_offset_seconds,
                action_type=fault_action.action_type,
                fault_level=fault_action.fault_level,
                target_nodes=target_nodes,
                target_percent=fault_action.target_percent,
                parameters=parameters,
                description=fault_action.description or f"Step {i}: {fault_action.action_type}",
                retry_count=1 if fault_action.action_type in ("baseline", "observe", "complete") else 2,
                rollback_on_failure=fault_action.action_type not in (
                    "baseline", "observe", "complete", "remove_faults"
                ),
            )

            actions.append(plan_action)

        return actions

    def _resolve_targets(
        self,
        target_percent: float,
        available_nodes: list[str],
        fault_level: FaultLevel,
    ) -> list[str]:
        """Resolve a target percentage into specific node identifiers.

        Args:
            target_percent: Percentage of nodes to target.
            available_nodes: Available node identifiers.
            fault_level: Fault level for target resolution.

        Returns:
            List of specific node identifiers.
        """
        if target_percent <= 0:
            return []

        # Calculate number of nodes from percentage
        num_nodes = max(1, int(len(available_nodes) * target_percent / 100.0))

        # Enforce blast radius safety limit (33%)
        max_nodes = int(len(available_nodes) * 33.0 / 100.0)
        num_nodes = min(num_nodes, max_nodes)

        return available_nodes[:num_nodes]

    def _resolve_parameters(self, fault_action: FaultAction) -> dict[str, Any]:
        """Resolve fault action parameters into concrete API parameters.

        Maps generic hypothesis parameters to the specific parameter names
        expected by the fault injection APIs.

        Args:
            fault_action: Fault action to resolve parameters for.

        Returns:
            Resolved parameters dictionary.
        """
        params = dict(fault_action.parameters)

        # Add fault-level-specific default parameters
        if fault_action.fault_level == FaultLevel.NETWORK:
            params.setdefault("interface", "eth0")
        elif fault_action.fault_level == FaultLevel.NODE:
            params.setdefault("namespace", "default")
        elif fault_action.fault_level == FaultLevel.PROTOCOL:
            params.setdefault("coordination", "centralized")

        return params

    def _generate_checkpoints(
        self,
        hypothesis: Hypothesis,
        plan_actions: list[PlanAction],
    ) -> list[MonitoringCheckpoint]:
        """Generate monitoring checkpoints for the experiment.

        Inserts checkpoints:
        - Before and after each fault injection action
        - At regular intervals during the experiment
        - Based on expected metrics from the hypothesis

        Args:
            hypothesis: Source hypothesis.
            plan_actions: Compiled plan actions.

        Returns:
            List of MonitoringCheckpoints.
        """
        checkpoints: list[MonitoringCheckpoint] = []
        metric_names = [m.metric_name for m in hypothesis.expected_metrics]

        # Pre-flight health check at t=0
        checkpoints.append(
            MonitoringCheckpoint(
                checkpoint_type=CheckpointType.HEALTH_CHECK,
                time_offset_seconds=0,
                metrics_to_check=metric_names,
                abort_on_failure=True,
                description="Pre-flight health check",
            )
        )

        # Add checkpoints before and after fault injection actions
        for action in plan_actions:
            if action.action_type in ("baseline", "observe", "complete", "remove_faults"):
                continue

            # Checkpoint right before injection
            checkpoints.append(
                MonitoringCheckpoint(
                    checkpoint_type=CheckpointType.CIRCUIT_BREAKER_CHECK,
                    time_offset_seconds=max(0, action.time_offset_seconds - 5),
                    metrics_to_check=metric_names,
                    abort_on_failure=True,
                    description=f"Safety check before {action.action_type}",
                )
            )

            # Checkpoint after injection (observation window)
            checkpoints.append(
                MonitoringCheckpoint(
                    checkpoint_type=CheckpointType.OBSERVATION_WINDOW,
                    time_offset_seconds=action.time_offset_seconds + self._checkpoint_interval,
                    metrics_to_check=metric_names,
                    abort_on_failure=False,
                    description=f"Observation after {action.action_type}",
                )
            )

        # Add periodic SLO checks throughout the experiment
        if plan_actions:
            max_time = max(a.time_offset_seconds for a in plan_actions)
            current_time = self._checkpoint_interval
            while current_time < max_time:
                checkpoints.append(
                    MonitoringCheckpoint(
                        checkpoint_type=CheckpointType.SLO_CHECK,
                        time_offset_seconds=current_time,
                        metrics_to_check=metric_names,
                        abort_on_failure=False,
                        description=f"SLO check at t={current_time}s",
                    )
                )
                current_time += self._checkpoint_interval

        # Sort by time
        checkpoints.sort(key=lambda c: c.time_offset_seconds)

        # Deduplicate checkpoints at the same time
        seen_times: set[int] = set()
        unique_checkpoints: list[MonitoringCheckpoint] = []
        for cp in checkpoints:
            key = (cp.time_offset_seconds, cp.checkpoint_type.value)
            if key not in seen_times:
                seen_times.add(key)
                unique_checkpoints.append(cp)

        return unique_checkpoints

    def _generate_rollback_conditions(
        self,
        hypothesis: Hypothesis,
    ) -> list[RollbackCondition]:
        """Generate rollback conditions from hypothesis expected metrics.

        Creates conditions that trigger automatic rollback when metrics
        go beyond the expected ranges.

        Args:
            hypothesis: Source hypothesis.

        Returns:
            List of RollbackConditions.
        """
        conditions: list[RollbackCondition] = []

        for metric in hypothesis.expected_metrics:
            # Add max threshold condition
            if metric.expected_max < float("inf"):
                conditions.append(
                    RollbackCondition(
                        metric_name=metric.metric_name,
                        comparison="greater_than",
                        threshold=metric.expected_max,
                        description=(
                            f"Rollback if {metric.metric_name} exceeds "
                            f"{metric.expected_max}"
                        ),
                    )
                )

            # Add min threshold condition
            if metric.expected_min > 0:
                conditions.append(
                    RollbackCondition(
                        metric_name=metric.metric_name,
                        comparison="less_than",
                        threshold=metric.expected_min,
                        description=(
                            f"Rollback if {metric.metric_name} drops below "
                            f"{metric.expected_min}"
                        ),
                    )
                )

        return conditions

    def _generate_placeholder_nodes(self) -> list[str]:
        """Generate placeholder node identifiers for dry-run mode.

        Returns:
            List of placeholder node IDs.
        """
        return [f"node-{i:03d}" for i in range(self._total_nodes)]
