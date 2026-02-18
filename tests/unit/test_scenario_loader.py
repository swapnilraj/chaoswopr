"""Tests for the scenario loader and builder.

Tests YAML loading, string parsing, and programmatic scenario
construction for all supported chaos experiment types.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from chaoswopr.agents.scenario_loader import (
    ScenarioBuilder,
    ScenarioDefinition,
    load_scenario_file,
    load_scenario_string,
)

SCENARIOS_DIR = Path(__file__).parent.parent.parent / "scenarios"


class TestScenarioDefinition:
    """Tests for ScenarioDefinition."""

    def test_default_definition(self) -> None:
        defn = ScenarioDefinition()
        assert defn.name == ""
        assert defn.hypothesis == ""
        assert defn.fault_sequence == []
        assert defn.slo_thresholds == {}

    def test_to_dict(self) -> None:
        defn = ScenarioDefinition(
            name="test",
            hypothesis="Test hypothesis",
            fault_sequence=[{"time": "0s", "action": "baseline"}],
            slo_thresholds={"finality_delay_max_epochs": 5},
        )
        d = defn.to_dict()
        assert d["name"] == "test"
        assert d["hypothesis"] == "Test hypothesis"
        assert len(d["fault_sequence"]) == 1
        assert d["slo_thresholds"]["finality_delay_max_epochs"] == 5


class TestLoadScenarioString:
    """Tests for loading scenarios from YAML strings."""

    def test_load_basic_scenario(self) -> None:
        yaml_content = textwrap.dedent("""\
            name: test_scenario
            hypothesis: Test hypothesis for network latency
            fault_sequence:
              - time: "0s"
                action: baseline
              - time: "60s"
                action: inject_network_latency
                params:
                  latency: "200ms"
              - time: "360s"
                action: complete
            slo_thresholds:
              finality_delay_max_epochs: 5
            blast_radius:
              max_affected_percent: 20.0
        """)

        scenario = load_scenario_string(yaml_content)
        assert scenario.name == "test_scenario"
        assert "network latency" in scenario.hypothesis
        assert len(scenario.fault_sequence) == 3
        assert scenario.slo_thresholds["finality_delay_max_epochs"] == 5

    def test_load_minimal_scenario(self) -> None:
        yaml_content = textwrap.dedent("""\
            name: minimal
            hypothesis: Minimal test
            fault_sequence:
              - time: "0s"
                action: baseline
        """)

        scenario = load_scenario_string(yaml_content)
        assert scenario.name == "minimal"

    def test_load_invalid_yaml_type(self) -> None:
        with pytest.raises(ValueError, match="YAML mapping"):
            load_scenario_string("just a string")

    def test_load_empty_yaml(self) -> None:
        # None is returned by yaml.safe_load for empty string
        with pytest.raises(ValueError, match="YAML mapping"):
            load_scenario_string("")


class TestLoadScenarioFile:
    """Tests for loading scenarios from files."""

    def test_load_baseline_scenario(self) -> None:
        path = SCENARIOS_DIR / "baseline_observation.yaml"
        if not path.exists():
            pytest.skip("baseline_observation.yaml not found")

        scenario = load_scenario_file(path)
        assert scenario.name == "baseline_observation"
        assert len(scenario.fault_sequence) >= 2
        assert "finality" in scenario.hypothesis.lower()

    def test_load_basic_withholding_scenario(self) -> None:
        path = SCENARIOS_DIR / "basic_withholding.yaml"
        if not path.exists():
            pytest.skip("basic_withholding.yaml not found")

        scenario = load_scenario_file(path)
        assert scenario.name == "basic_withholding"
        assert "withhold" in scenario.hypothesis.lower()
        assert scenario.blast_radius["max_affected_percent"] == 30.0

    def test_load_finality_stress_test_scenario(self) -> None:
        path = SCENARIOS_DIR / "finality_stress_test.yaml"
        if not path.exists():
            pytest.skip("finality_stress_test.yaml not found")

        scenario = load_scenario_file(path)
        assert scenario.name == "finality_stress_test"
        assert "finality" in scenario.hypothesis.lower()
        assert len(scenario.fault_sequence) >= 4

    def test_load_nonexistent_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_scenario_file(Path("/nonexistent/scenario.yaml"))


class TestScenarioBuilder:
    """Tests for the programmatic scenario builder."""

    def test_baseline_observation(self) -> None:
        scenario = ScenarioBuilder.baseline_observation(
            duration_seconds=300,
            node_count=20,
        )
        assert scenario.name == "baseline_observation"
        assert scenario.blast_radius["max_affected_percent"] == 0.0
        assert len(scenario.fault_sequence) == 3
        assert scenario.fault_sequence[0]["action"] == "baseline"
        assert scenario.fault_sequence[-1]["action"] == "complete"
        assert scenario.network_config["node_count"] == 20

    def test_attestation_withholding(self) -> None:
        scenario = ScenarioBuilder.attestation_withholding(
            target_percent=30.0,
            withhold_probability=1.0,
            duration_seconds=600,
            node_count=10,
        )
        assert scenario.name == "attestation_withholding"
        assert "30%" in scenario.hypothesis or "30" in scenario.hypothesis
        assert scenario.blast_radius["max_affected_percent"] == 30.0
        assert len(scenario.fault_sequence) >= 3
        # Verify fault action has correct params
        fault_step = scenario.fault_sequence[1]
        assert fault_step["action"] == "attestation_withholding"
        assert fault_step["params"]["target_percent"] == 30.0

    def test_attestation_withholding_capped_at_33(self) -> None:
        scenario = ScenarioBuilder.attestation_withholding(target_percent=50.0)
        assert scenario.blast_radius["max_affected_percent"] == 33.0

    def test_network_latency(self) -> None:
        scenario = ScenarioBuilder.network_latency(
            target_percent=20.0,
            latency_ms=500,
            jitter_ms=100,
            node_count=10,
        )
        assert scenario.name == "network_latency_injection"
        assert "500ms" in scenario.hypothesis
        assert scenario.blast_radius["max_affected_percent"] == 20.0
        fault_step = scenario.fault_sequence[1]
        assert fault_step["action"] == "inject_network_latency"

    def test_node_failure(self) -> None:
        scenario = ScenarioBuilder.node_failure(
            target_percent=20.0,
            duration_seconds=300,
            node_count=10,
        )
        assert scenario.name == "node_failure"
        assert "20%" in scenario.hypothesis or "20" in scenario.hypothesis
        fault_step = scenario.fault_sequence[1]
        assert fault_step["action"] == "kill_nodes"
        assert fault_step["params"]["percent"] == 20.0

    def test_finality_stress_test(self) -> None:
        scenario = ScenarioBuilder.finality_stress_test(
            adversarial_ratio=0.3,
            node_count=10,
            duration_seconds=600,
        )
        assert scenario.name == "finality_stress_test"
        assert "latency" in scenario.hypothesis.lower()
        assert "withholding" in scenario.hypothesis.lower()
        # Should have multiple fault phases
        fault_actions = [s["action"] for s in scenario.fault_sequence]
        assert "inject_network_latency" in fault_actions
        assert "attestation_withholding" in fault_actions
        assert "remove_faults" in fault_actions
        assert "complete" in fault_actions

    def test_builder_scenario_is_valid_dict(self) -> None:
        scenario = ScenarioBuilder.attestation_withholding()
        d = scenario.to_dict()
        assert isinstance(d, dict)
        assert "name" in d
        assert "hypothesis" in d
        assert "fault_sequence" in d
        assert "slo_thresholds" in d

    def test_builder_scenarios_compatible_with_runner(self) -> None:
        """Verify that builder scenarios produce valid dicts for ExperimentRunner."""
        from chaoswopr.agents.experiment_runner import ExperimentRunner, ExperimentRunnerConfig
        from chaoswopr.agents.node_coordinator import FleetConfig

        scenario = ScenarioBuilder.attestation_withholding(
            target_percent=30.0,
            node_count=5,
        )

        config = ExperimentRunnerConfig(
            fleet_config=FleetConfig(num_agents=5, adversarial_ratio=0.3),
            dry_run=True,
        )
        runner = ExperimentRunner(config)
        result = runner.run_experiment(scenario.to_dict())
        assert result.success
        assert result.experiment_id != ""
