"""Unit tests for the Experiment Plan Compiler.

Tests plan compilation from hypotheses, action resolution, monitoring
checkpoint generation, and rollback condition generation.
"""

from __future__ import annotations

import pytest

from chaoswopr.agents.hypothesis_engine import (
    ExpectedMetric,
    FaultAction,
    FaultLevel,
    Hypothesis,
    HypothesisEngine,
)
from chaoswopr.agents.plan_compiler import (
    ActionStatus,
    CheckpointType,
    ExperimentPlan,
    MonitoringCheckpoint,
    PlanAction,
    PlanCompiler,
    RollbackCondition,
)


class TestPlanAction:
    """Tests for PlanAction data class."""

    def test_creation(self) -> None:
        """PlanAction should be created with defaults."""
        action = PlanAction(
            step_number=0,
            time_offset_seconds=60,
            action_type="inject_latency",
        )
        assert action.step_number == 0
        assert action.status == ActionStatus.PENDING
        assert action.action_id is not None

    def test_to_dict(self) -> None:
        """PlanAction should serialize to dictionary."""
        action = PlanAction(
            action_type="test",
            fault_level=FaultLevel.NETWORK,
            target_nodes=["node-1", "node-2"],
        )
        d = action.to_dict()
        assert d["action_type"] == "test"
        assert d["fault_level"] == "network"
        assert len(d["target_nodes"]) == 2


class TestMonitoringCheckpoint:
    """Tests for MonitoringCheckpoint data class."""

    def test_creation(self) -> None:
        """Checkpoint should be created with defaults."""
        cp = MonitoringCheckpoint(
            checkpoint_type=CheckpointType.HEALTH_CHECK,
            time_offset_seconds=0,
        )
        assert cp.checkpoint_type == CheckpointType.HEALTH_CHECK
        assert cp.abort_on_failure is False

    def test_to_dict(self) -> None:
        """Checkpoint should serialize."""
        cp = MonitoringCheckpoint(
            checkpoint_type=CheckpointType.SLO_CHECK,
            metrics_to_check=["finality_delay"],
        )
        d = cp.to_dict()
        assert d["checkpoint_type"] == "slo_check"
        assert "finality_delay" in d["metrics_to_check"]


class TestRollbackCondition:
    """Tests for RollbackCondition data class."""

    def test_greater_than_triggered(self) -> None:
        """greater_than condition should trigger above threshold."""
        rc = RollbackCondition(
            metric_name="finality_delay",
            comparison="greater_than",
            threshold=600.0,
        )
        assert rc.is_triggered(700.0) is True
        assert rc.is_triggered(500.0) is False

    def test_less_than_triggered(self) -> None:
        """less_than condition should trigger below threshold."""
        rc = RollbackCondition(
            metric_name="participation_rate",
            comparison="less_than",
            threshold=66.0,
        )
        assert rc.is_triggered(50.0) is True
        assert rc.is_triggered(80.0) is False

    def test_to_dict(self) -> None:
        """RollbackCondition should serialize."""
        rc = RollbackCondition(metric_name="test", threshold=42.0)
        d = rc.to_dict()
        assert d["metric_name"] == "test"
        assert d["threshold"] == 42.0


class TestExperimentPlan:
    """Tests for ExperimentPlan data class."""

    def _make_plan(self, num_actions: int = 3) -> ExperimentPlan:
        """Create a test plan."""
        actions = [
            PlanAction(
                step_number=i,
                time_offset_seconds=i * 60,
                action_type=f"action_{i}",
            )
            for i in range(num_actions)
        ]
        return ExperimentPlan(
            actions=actions,
            total_duration_seconds=(num_actions - 1) * 60,
            blast_radius_percent=10.0,
        )

    def test_get_pending_actions(self) -> None:
        """get_pending_actions should return all pending actions."""
        plan = self._make_plan()
        assert len(plan.get_pending_actions()) == 3

    def test_get_next_action(self) -> None:
        """get_next_action should return first pending action."""
        plan = self._make_plan()
        next_action = plan.get_next_action()
        assert next_action is not None
        assert next_action.step_number == 0

    def test_get_next_action_after_completion(self) -> None:
        """get_next_action should skip completed actions."""
        plan = self._make_plan()
        plan.actions[0].status = ActionStatus.COMPLETED
        next_action = plan.get_next_action()
        assert next_action is not None
        assert next_action.step_number == 1

    def test_get_next_action_all_done(self) -> None:
        """get_next_action should return None when all done."""
        plan = self._make_plan()
        for action in plan.actions:
            action.status = ActionStatus.COMPLETED
        assert plan.get_next_action() is None

    def test_get_actions_at_time(self) -> None:
        """get_actions_at_time should return actions due by time."""
        plan = self._make_plan()
        due_actions = plan.get_actions_at_time(90)  # Should get actions at t=0, t=60
        assert len(due_actions) == 2

    def test_is_complete(self) -> None:
        """is_complete should be True when all actions done."""
        plan = self._make_plan()
        assert plan.is_complete() is False

        for action in plan.actions:
            action.status = ActionStatus.COMPLETED
        assert plan.is_complete() is True

    def test_mark_action_complete(self) -> None:
        """mark_action_complete should update status."""
        plan = self._make_plan()
        action_id = plan.actions[0].action_id
        assert plan.mark_action_complete(action_id) is True
        assert plan.actions[0].status == ActionStatus.COMPLETED

    def test_mark_action_failed(self) -> None:
        """mark_action_failed should update status."""
        plan = self._make_plan()
        action_id = plan.actions[0].action_id
        assert plan.mark_action_failed(action_id) is True
        assert plan.actions[0].status == ActionStatus.FAILED

    def test_mark_nonexistent_action(self) -> None:
        """Marking a nonexistent action should return False."""
        plan = self._make_plan()
        assert plan.mark_action_complete("nonexistent") is False

    def test_validate_valid_plan(self) -> None:
        """Valid plan should pass validation."""
        plan = self._make_plan()
        errors = plan.validate()
        assert errors == []

    def test_validate_empty_plan(self) -> None:
        """Empty plan should fail validation."""
        plan = ExperimentPlan()
        errors = plan.validate()
        assert any("at least one action" in e for e in errors)

    def test_validate_excessive_blast_radius(self) -> None:
        """Blast radius > 33% should fail validation."""
        plan = self._make_plan()
        plan.blast_radius_percent = 50.0
        errors = plan.validate()
        assert any("safety limit" in e for e in errors)

    def test_to_dict(self) -> None:
        """Plan should serialize to dictionary."""
        plan = self._make_plan()
        d = plan.to_dict()
        assert d["plan_id"] is not None
        assert len(d["actions"]) == 3
        assert d["blast_radius_percent"] == 10.0


class TestPlanCompiler:
    """Tests for the PlanCompiler."""

    def _make_compiler(self, **kwargs) -> PlanCompiler:
        """Create a test compiler."""
        kwargs.setdefault("total_nodes", 50)
        kwargs.setdefault("dry_run", True)
        return PlanCompiler(**kwargs)

    def _make_hypothesis(self, target_percent: float = 10.0) -> Hypothesis:
        """Create a valid hypothesis for compilation."""
        return Hypothesis(
            prediction="Test prediction",
            rationale="Test rationale",
            fault_timeline=[
                FaultAction(
                    time_offset_seconds=0,
                    action_type="baseline",
                    fault_level=FaultLevel.NETWORK,
                    target_percent=0,
                ),
                FaultAction(
                    time_offset_seconds=60,
                    action_type="inject_network_latency",
                    fault_level=FaultLevel.NETWORK,
                    target_percent=target_percent,
                    parameters={"latency_ms": 200},
                ),
                FaultAction(
                    time_offset_seconds=300,
                    action_type="observe",
                    fault_level=FaultLevel.NETWORK,
                    target_percent=0,
                ),
                FaultAction(
                    time_offset_seconds=600,
                    action_type="remove_faults",
                    fault_level=FaultLevel.NETWORK,
                    target_percent=0,
                ),
                FaultAction(
                    time_offset_seconds=900,
                    action_type="complete",
                    fault_level=FaultLevel.NETWORK,
                    target_percent=0,
                ),
            ],
            expected_metrics=[
                ExpectedMetric(
                    metric_name="finality_delay_seconds",
                    expected_max=120.0,
                ),
                ExpectedMetric(
                    metric_name="participation_rate_percent",
                    expected_min=80.0,
                ),
            ],
            blast_radius_percent=target_percent,
            success_criteria="Finality maintained",
        )

    def test_compile_valid_hypothesis(self) -> None:
        """compile should produce a valid plan from a valid hypothesis."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        assert plan is not None
        assert len(plan.actions) == 5
        assert plan.hypothesis_id == hypothesis.hypothesis_id
        assert plan.blast_radius_percent == 10.0
        assert plan.total_duration_seconds == 900

    def test_compile_invalid_hypothesis_raises(self) -> None:
        """compile should raise ValueError for invalid hypothesis."""
        compiler = self._make_compiler()
        hypothesis = Hypothesis()  # Empty, invalid

        with pytest.raises(ValueError, match="Cannot compile invalid"):
            compiler.compile(hypothesis)

    def test_actions_in_chronological_order(self) -> None:
        """Compiled actions should be in chronological order."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        times = [a.time_offset_seconds for a in plan.actions]
        assert times == sorted(times)

    def test_target_nodes_resolved(self) -> None:
        """Actions with target_percent > 0 should have resolved nodes."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis(target_percent=10.0)

        plan = compiler.compile(hypothesis)

        # The inject action (index 1) should have target nodes
        inject_action = plan.actions[1]
        assert len(inject_action.target_nodes) > 0
        expected_count = max(1, int(50 * 10.0 / 100.0))  # 5 nodes
        assert len(inject_action.target_nodes) == expected_count

    def test_target_nodes_with_custom_list(self) -> None:
        """compile with available_nodes should use those nodes."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis(target_percent=20.0)
        custom_nodes = [f"custom-{i}" for i in range(10)]

        plan = compiler.compile(hypothesis, available_nodes=custom_nodes)

        inject_action = plan.actions[1]
        assert all(n.startswith("custom-") for n in inject_action.target_nodes)

    def test_blast_radius_enforced_on_targets(self) -> None:
        """Target nodes should never exceed 33% of total nodes."""
        compiler = self._make_compiler(total_nodes=10)
        hypothesis = self._make_hypothesis(target_percent=30.0)

        plan = compiler.compile(hypothesis)

        inject_action = plan.actions[1]
        max_allowed = int(10 * 33.0 / 100.0)  # 3 nodes
        assert len(inject_action.target_nodes) <= max_allowed

    def test_monitoring_checkpoints_generated(self) -> None:
        """Checkpoints should be generated between actions."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        assert len(plan.checkpoints) > 0
        # Should have a pre-flight health check
        health_checks = [
            c for c in plan.checkpoints
            if c.checkpoint_type == CheckpointType.HEALTH_CHECK
        ]
        assert len(health_checks) >= 1

    def test_circuit_breaker_checkpoints_before_faults(self) -> None:
        """Circuit breaker checks should precede fault injections."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        cb_checks = [
            c for c in plan.checkpoints
            if c.checkpoint_type == CheckpointType.CIRCUIT_BREAKER_CHECK
        ]
        assert len(cb_checks) >= 1
        # First CB check should be before the inject action (t=60)
        assert cb_checks[0].time_offset_seconds < 60

    def test_rollback_conditions_generated(self) -> None:
        """Rollback conditions should be generated from expected metrics."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        assert len(plan.rollback_conditions) > 0

    def test_rollback_conditions_match_expected_metrics(self) -> None:
        """Rollback conditions should cover all bounded expected metrics."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        rc_metrics = {rc.metric_name for rc in plan.rollback_conditions}
        # Should have conditions for finality_delay (max) and participation_rate (min)
        assert "finality_delay_seconds" in rc_metrics
        assert "participation_rate_percent" in rc_metrics

    def test_rollback_condition_thresholds(self) -> None:
        """Rollback condition thresholds should match expected metric bounds."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        finality_rc = [
            rc for rc in plan.rollback_conditions
            if rc.metric_name == "finality_delay_seconds"
        ]
        assert len(finality_rc) == 1
        assert finality_rc[0].threshold == 120.0
        assert finality_rc[0].comparison == "greater_than"

    def test_control_actions_no_rollback(self) -> None:
        """Control actions (baseline, observe, complete) should not trigger rollback."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        control_actions = [
            a for a in plan.actions
            if a.action_type in ("baseline", "observe", "complete", "remove_faults")
        ]
        for action in control_actions:
            assert action.rollback_on_failure is False

    def test_fault_actions_have_retry(self) -> None:
        """Fault injection actions should have retry_count > 1."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        inject_action = [a for a in plan.actions if a.action_type == "inject_network_latency"]
        assert len(inject_action) == 1
        assert inject_action[0].retry_count >= 2

    def test_plan_validation(self) -> None:
        """Compiled plan should pass validation."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)
        errors = plan.validate()
        assert errors == []

    def test_compiled_count_increments(self) -> None:
        """Each compilation should increment count."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        compiler.compile(hypothesis)
        compiler.compile(hypothesis)
        assert compiler.compiled_count == 2

    def test_parameters_resolved(self) -> None:
        """Fault action parameters should be resolved in plan actions."""
        compiler = self._make_compiler()
        hypothesis = self._make_hypothesis()

        plan = compiler.compile(hypothesis)

        inject_action = plan.actions[1]
        assert "latency_ms" in inject_action.parameters
        assert inject_action.parameters["latency_ms"] == 200

    def test_integration_with_hypothesis_engine(self) -> None:
        """PlanCompiler should work with HypothesisEngine output."""
        engine = HypothesisEngine(dry_run=True)
        compiler = self._make_compiler()

        hypothesis = engine.generate_from_template(
            template_key="network_latency",
            target_percent=10.0,
        )

        plan = compiler.compile(hypothesis)
        assert plan is not None
        assert plan.validate() == []
        assert plan.total_duration_seconds > 0
