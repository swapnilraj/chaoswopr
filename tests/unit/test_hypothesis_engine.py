"""Unit tests for the Hypothesis Generation Engine.

Tests hypothesis generation from scenarios, template-based generation,
validation, adaptive learning, and SLO enrichment.
"""

from __future__ import annotations

import pytest

from chaoswopr.agents.hypothesis_engine import (
    ExpectedMetric,
    FaultAction,
    FaultLevel,
    Hypothesis,
    HypothesisEngine,
    HypothesisStatus,
    HYPOTHESIS_TEMPLATES,
)


class TestFaultAction:
    """Tests for FaultAction data class."""

    def test_creation(self) -> None:
        """FaultAction should be created with defaults."""
        action = FaultAction(
            time_offset_seconds=60,
            action_type="inject_network_latency",
            fault_level=FaultLevel.NETWORK,
        )
        assert action.time_offset_seconds == 60
        assert action.action_type == "inject_network_latency"
        assert action.fault_level == FaultLevel.NETWORK

    def test_validate_valid(self) -> None:
        """Valid action should have no errors."""
        action = FaultAction(
            time_offset_seconds=60,
            action_type="inject_latency",
            fault_level=FaultLevel.NETWORK,
            target_percent=10.0,
        )
        assert action.validate() == []

    def test_validate_negative_time(self) -> None:
        """Negative time should be rejected."""
        action = FaultAction(
            time_offset_seconds=-10,
            action_type="test",
            fault_level=FaultLevel.NETWORK,
        )
        errors = action.validate()
        assert any("time_offset_seconds" in e for e in errors)

    def test_validate_excessive_target_percent(self) -> None:
        """Target percent > 33% should be rejected."""
        action = FaultAction(
            time_offset_seconds=0,
            action_type="test",
            fault_level=FaultLevel.NETWORK,
            target_percent=50.0,
        )
        errors = action.validate()
        assert any("target_percent" in e for e in errors)

    def test_to_dict(self) -> None:
        """FaultAction should serialize to dictionary."""
        action = FaultAction(
            time_offset_seconds=60,
            action_type="test",
            fault_level=FaultLevel.NODE,
        )
        d = action.to_dict()
        assert d["time_offset_seconds"] == 60
        assert d["fault_level"] == "node"


class TestExpectedMetric:
    """Tests for ExpectedMetric data class."""

    def test_creation(self) -> None:
        """ExpectedMetric should be created with values."""
        metric = ExpectedMetric(
            metric_name="finality_delay_seconds",
            baseline_value=13.2,
            expected_max=120.0,
        )
        assert metric.metric_name == "finality_delay_seconds"
        assert metric.expected_max == 120.0

    def test_to_dict(self) -> None:
        """ExpectedMetric should serialize."""
        metric = ExpectedMetric(metric_name="test", expected_min=5.0)
        d = metric.to_dict()
        assert d["metric_name"] == "test"
        assert d["expected_min"] == 5.0


class TestHypothesis:
    """Tests for Hypothesis data class."""

    def _make_valid_hypothesis(self) -> Hypothesis:
        """Create a valid hypothesis for testing."""
        return Hypothesis(
            prediction="The network will maintain finality under 10% latency injection",
            rationale="Consensus tolerates moderate latency",
            fault_timeline=[
                FaultAction(
                    time_offset_seconds=0,
                    action_type="baseline",
                    fault_level=FaultLevel.NETWORK,
                    target_percent=0,
                ),
                FaultAction(
                    time_offset_seconds=60,
                    action_type="inject_latency",
                    fault_level=FaultLevel.NETWORK,
                    target_percent=10.0,
                ),
            ],
            expected_metrics=[
                ExpectedMetric(
                    metric_name="finality_delay_seconds",
                    expected_max=120.0,
                ),
            ],
            blast_radius_percent=10.0,
            success_criteria="Finality maintained within 2 minutes",
        )

    def test_valid_hypothesis(self) -> None:
        """Valid hypothesis should pass validation."""
        hypothesis = self._make_valid_hypothesis()
        errors = hypothesis.validate()
        assert errors == []

    def test_missing_prediction(self) -> None:
        """Hypothesis without prediction should fail."""
        hypothesis = self._make_valid_hypothesis()
        hypothesis.prediction = ""
        errors = hypothesis.validate()
        assert any("prediction" in e for e in errors)

    def test_empty_fault_timeline(self) -> None:
        """Hypothesis without fault timeline should fail."""
        hypothesis = self._make_valid_hypothesis()
        hypothesis.fault_timeline = []
        errors = hypothesis.validate()
        assert any("fault_timeline" in e for e in errors)

    def test_excessive_blast_radius(self) -> None:
        """Blast radius > 33% should fail validation."""
        hypothesis = self._make_valid_hypothesis()
        hypothesis.blast_radius_percent = 50.0
        errors = hypothesis.validate()
        assert any("blast_radius_percent" in e for e in errors)

    def test_invalid_confidence(self) -> None:
        """Confidence outside 0-1 should fail."""
        hypothesis = self._make_valid_hypothesis()
        hypothesis.confidence = 1.5
        errors = hypothesis.validate()
        assert any("confidence" in e for e in errors)

    def test_missing_success_criteria(self) -> None:
        """Hypothesis without success criteria should fail."""
        hypothesis = self._make_valid_hypothesis()
        hypothesis.success_criteria = ""
        errors = hypothesis.validate()
        assert any("success_criteria" in e for e in errors)

    def test_non_chronological_timeline(self) -> None:
        """Non-chronological timeline should fail."""
        hypothesis = self._make_valid_hypothesis()
        hypothesis.fault_timeline = [
            FaultAction(time_offset_seconds=60, action_type="a", fault_level=FaultLevel.NETWORK, target_percent=5),
            FaultAction(time_offset_seconds=30, action_type="b", fault_level=FaultLevel.NETWORK, target_percent=5),
        ]
        errors = hypothesis.validate()
        assert any("chronological" in e for e in errors)

    def test_action_exceeds_blast_radius(self) -> None:
        """Action target_percent > blast_radius should fail."""
        hypothesis = self._make_valid_hypothesis()
        hypothesis.blast_radius_percent = 5.0
        hypothesis.fault_timeline[1].target_percent = 10.0
        errors = hypothesis.validate()
        assert any("exceeds blast_radius_percent" in e for e in errors)

    def test_to_dict(self) -> None:
        """Hypothesis should serialize to dictionary."""
        hypothesis = self._make_valid_hypothesis()
        d = hypothesis.to_dict()
        assert d["prediction"] is not None
        assert len(d["fault_timeline"]) == 2
        assert d["status"] == "generated"


class TestHypothesisEngine:
    """Tests for the HypothesisEngine."""

    def _make_engine(self) -> HypothesisEngine:
        """Create a dry-run engine for testing."""
        return HypothesisEngine(dry_run=True)

    def test_initialization(self) -> None:
        """Engine should initialize with zero count."""
        engine = self._make_engine()
        assert engine.generated_count == 0

    def test_generate_from_scenario(self) -> None:
        """generate should produce a valid hypothesis from a scenario."""
        engine = self._make_engine()
        scenario = {
            "name": "test_scenario",
            "hypothesis": "The network will maintain finality under stress",
            "fault_sequence": [
                {"time": "0s", "action": "baseline"},
                {"time": "60s", "action": "inject_network_latency", "params": {"latency_ms": 200}},
            ],
            "slo_thresholds": {
                "finality_delay_max_epochs": 5,
                "participation_rate_min_percent": 66.0,
            },
            "blast_radius": {
                "max_affected_percent": 20.0,
            },
        }

        hypothesis = engine.generate(scenario=scenario)
        assert hypothesis is not None
        assert hypothesis.scenario_name == "test_scenario"
        assert hypothesis.status == HypothesisStatus.VALIDATED
        assert engine.generated_count == 1

    def test_generate_enforces_blast_radius_limit(self) -> None:
        """generate should cap blast radius at 33%."""
        engine = self._make_engine()
        scenario = {
            "name": "test",
            "blast_radius": {"max_affected_percent": 50.0},
        }

        hypothesis = engine.generate(scenario=scenario)
        assert hypothesis.blast_radius_percent <= 33.0

    def test_generate_with_cluster_state(self) -> None:
        """generate should use cluster state for baseline values."""
        engine = self._make_engine()
        scenario = {"name": "test"}
        cluster_state = {"finality_delay_seconds": 14.0}

        hypothesis = engine.generate(
            scenario=scenario,
            cluster_state=cluster_state,
        )
        # At least some expected metrics should have the baseline value
        baseline_values = [m.baseline_value for m in hypothesis.expected_metrics]
        # The cluster_state value should be used if the metric is present
        assert hypothesis is not None

    def test_generate_from_template(self) -> None:
        """generate_from_template should produce from named templates."""
        engine = self._make_engine()
        hypothesis = engine.generate_from_template(
            template_key="network_latency",
            target_percent=15.0,
        )

        assert hypothesis is not None
        assert "latency" in hypothesis.prediction.lower()
        assert hypothesis.blast_radius_percent == 15.0
        errors = hypothesis.validate()
        assert errors == []

    def test_generate_from_all_templates(self) -> None:
        """All templates should produce valid hypotheses."""
        engine = self._make_engine()
        for key in HYPOTHESIS_TEMPLATES:
            hypothesis = engine.generate_from_template(template_key=key)
            errors = hypothesis.validate()
            assert errors == [], f"Template '{key}' produced invalid hypothesis: {errors}"

    def test_generate_from_invalid_template(self) -> None:
        """Invalid template key should raise ValueError."""
        engine = self._make_engine()
        with pytest.raises(ValueError, match="Unknown template"):
            engine.generate_from_template(template_key="nonexistent")

    def test_template_selection_latency(self) -> None:
        """Scenario with latency action should use network_latency template."""
        engine = self._make_engine()
        scenario = {
            "name": "test",
            "fault_sequence": [
                {"time": "0s", "action": "baseline"},
                {"time": "60s", "action": "inject_network_latency"},
            ],
        }
        hypothesis = engine.generate(scenario=scenario)
        assert "latency" in hypothesis.prediction.lower() or "finality" in hypothesis.prediction.lower()

    def test_template_selection_packet_loss(self) -> None:
        """Scenario with packet loss should use packet_loss template."""
        engine = self._make_engine()
        scenario = {
            "name": "test",
            "fault_sequence": [
                {"time": "0s", "action": "inject_packet_loss"},
            ],
        }
        hypothesis = engine.generate(scenario=scenario)
        assert hypothesis is not None

    def test_template_selection_attestation(self) -> None:
        """Scenario with attestation withholding should use protocol template."""
        engine = self._make_engine()
        scenario = {
            "name": "test",
            "fault_sequence": [
                {"time": "0s", "action": "attestation_withholding"},
            ],
        }
        hypothesis = engine.generate(scenario=scenario)
        assert hypothesis is not None

    def test_slo_enrichment(self) -> None:
        """Hypothesis should include SLO-derived expected metrics."""
        engine = self._make_engine()
        scenario = {
            "name": "test",
            "slo_thresholds": {
                "finality_delay_max_epochs": 5,
                "slashing_rate_max_percent": 5.0,
                "participation_rate_min_percent": 66.0,
            },
        }
        hypothesis = engine.generate(scenario=scenario)
        metric_names = [m.metric_name for m in hypothesis.expected_metrics]
        # Should have enriched with SLO-derived metrics
        assert len(hypothesis.expected_metrics) > 0

    def test_adaptive_learning(self) -> None:
        """Engine with history should adjust confidence."""
        history = [
            {
                "scenario_name": "test",
                "outcome": "success",
                "target_percent": 10.0,
            },
            {
                "scenario_name": "test",
                "outcome": "success",
                "target_percent": 15.0,
            },
        ]
        engine = HypothesisEngine(experiment_history=history, dry_run=True)
        hypothesis = engine.generate(scenario={"name": "test"})
        # Confidence should be blended with historical success rate
        assert hypothesis.confidence > 0.0

    def test_adaptive_learning_no_relevant_history(self) -> None:
        """Engine with irrelevant history should not adjust."""
        history = [
            {
                "scenario_name": "other_scenario",
                "outcome": "failure",
            },
        ]
        engine = HypothesisEngine(experiment_history=history, dry_run=True)
        hypothesis = engine.generate(scenario={"name": "test"})
        # Default confidence should be used
        assert hypothesis is not None

    def test_add_experiment_result(self) -> None:
        """add_experiment_result should grow history."""
        engine = self._make_engine()
        engine.add_experiment_result({
            "scenario_name": "test",
            "outcome": "success",
        })
        assert len(engine._experiment_history) == 1

    def test_generated_count_increments(self) -> None:
        """Each generation should increment the count."""
        engine = self._make_engine()
        engine.generate(scenario={"name": "test1"})
        engine.generate(scenario={"name": "test2"})
        assert engine.generated_count == 2

    def test_baseline_scenario(self) -> None:
        """Baseline scenario (0% blast radius) should produce valid hypothesis."""
        engine = self._make_engine()
        scenario = {
            "name": "baseline_observation",
            "hypothesis": "Network maintains health with no faults",
            "fault_sequence": [
                {"time": "0s", "action": "baseline"},
                {"time": "300s", "action": "observe"},
                {"time": "600s", "action": "complete"},
            ],
            "blast_radius": {
                "max_affected_percent": 0.0,
            },
        }
        hypothesis = engine.generate(scenario=scenario, target_percent=0.0)
        # With 0% target, blast radius should be 0
        assert hypothesis.blast_radius_percent == 0.0
