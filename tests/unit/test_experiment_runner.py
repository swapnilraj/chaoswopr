"""Tests for the ExperimentRunner.

Tests end-to-end experiment execution in dry-run mode,
verifying the complete 5-phase workflow.
"""

from __future__ import annotations

import pytest

from chaoswopr.agents.experiment_runner import (
    ExperimentResult,
    ExperimentRunner,
    ExperimentRunnerConfig,
)
from chaoswopr.agents.node_coordinator import FleetConfig
from chaoswopr.agents.orchestrator import OrchestratorState


class TestExperimentResult:
    """Tests for ExperimentResult."""

    def test_default_result(self) -> None:
        result = ExperimentResult()
        assert result.experiment_id == ""
        assert result.success is False
        assert result.halted is False
        assert result.observation_events == []

    def test_result_to_dict(self) -> None:
        result = ExperimentResult(
            experiment_id="exp-001",
            scenario_name="test",
            success=True,
            duration_seconds=120.5,
        )
        d = result.to_dict()
        assert d["experiment_id"] == "exp-001"
        assert d["success"] is True
        assert d["duration_seconds"] == 120.5


class TestExperimentRunnerConfig:
    """Tests for ExperimentRunnerConfig."""

    def test_default_config(self) -> None:
        config = ExperimentRunnerConfig()
        assert config.dry_run is True
        assert config.monitoring_interval_seconds == 5.0

    def test_custom_config(self) -> None:
        config = ExperimentRunnerConfig(
            prometheus_url="http://prom:9090",
            fleet_config=FleetConfig(num_agents=20),
            dry_run=True,
        )
        assert config.fleet_config.num_agents == 20


class TestExperimentRunner:
    """Tests for the ExperimentRunner."""

    def _make_runner(
        self,
        num_agents: int = 10,
        adversarial_ratio: float = 0.3,
    ) -> ExperimentRunner:
        config = ExperimentRunnerConfig(
            fleet_config=FleetConfig(
                num_agents=num_agents,
                adversarial_ratio=adversarial_ratio,
            ),
            dry_run=True,
        )
        return ExperimentRunner(config)

    def _make_scenario(self, name: str = "test_scenario") -> dict:
        return {
            "name": name,
            "hypothesis": "Network maintains finality under latency injection",
            "fault_sequence": [
                {"time": "0s", "action": "baseline"},
                {
                    "time": "60s",
                    "action": "inject_network_latency",
                    "params": {"nodes": "20%", "latency": "200ms"},
                },
            ],
            "slo_thresholds": {
                "finality_delay_max_epochs": 5,
                "slashing_rate_max_percent": 5,
            },
            "blast_radius": {
                "max_affected_percent": 20,
            },
        }

    def test_run_experiment_completes(self) -> None:
        runner = self._make_runner()
        scenario = self._make_scenario()

        result = runner.run_experiment(scenario)

        assert result.success
        assert result.experiment_id != ""
        assert result.scenario_name == "test_scenario"
        assert result.duration_seconds > 0
        assert result.hypothesis is not None
        assert result.plan is not None
        assert not result.halted

    def test_orchestrator_returns_to_idle(self) -> None:
        runner = self._make_runner()
        scenario = self._make_scenario()

        runner.run_experiment(scenario)

        assert runner.orchestrator.state == OrchestratorState.IDLE

    def test_fleet_is_created_and_started(self) -> None:
        runner = self._make_runner(num_agents=5, adversarial_ratio=0.4)
        scenario = self._make_scenario()

        result = runner.run_experiment(scenario)

        fleet_status = result.fleet_status
        assert fleet_status["total_agents"] == 5

    def test_hypothesis_is_generated(self) -> None:
        runner = self._make_runner()
        scenario = self._make_scenario()

        result = runner.run_experiment(scenario)

        assert result.hypothesis is not None
        assert "prediction" in result.hypothesis
        assert "fault_timeline" in result.hypothesis

    def test_plan_is_compiled(self) -> None:
        runner = self._make_runner()
        scenario = self._make_scenario()

        result = runner.run_experiment(scenario)

        assert result.plan is not None
        assert "actions" in result.plan
        assert len(result.plan["actions"]) > 0

    def test_metrics_are_collected(self) -> None:
        runner = self._make_runner()
        scenario = self._make_scenario()

        result = runner.run_experiment(scenario)

        # In dry-run mode, should have at least some snapshots
        assert len(result.metrics_snapshots) > 0

    def test_experiment_with_attestation_withholding_scenario(self) -> None:
        runner = self._make_runner(num_agents=10, adversarial_ratio=0.3)
        scenario = {
            "name": "attestation_withholding_test",
            "hypothesis": "Finality maintained with 30% attestation withholding",
            "fault_sequence": [
                {"time": "0s", "action": "baseline"},
                {
                    "time": "60s",
                    "action": "attestation_withholding",
                    "params": {"withhold_probability": 1.0},
                },
            ],
            "slo_thresholds": {
                "finality_delay_max_epochs": 5,
            },
        }

        result = runner.run_experiment(scenario)
        assert result.success

    def test_multiple_experiments_sequential(self) -> None:
        runner = self._make_runner(num_agents=5)

        scenario_1 = self._make_scenario("experiment_1")
        result_1 = runner.run_experiment(scenario_1)
        assert result_1.success

        scenario_2 = self._make_scenario("experiment_2")
        result_2 = runner.run_experiment(scenario_2)
        assert result_2.success

        # Experiment IDs should be different
        assert result_1.experiment_id != result_2.experiment_id

    def test_experiment_count_increments(self) -> None:
        runner = self._make_runner(num_agents=3)

        assert runner.orchestrator.experiment_count == 0

        runner.run_experiment(self._make_scenario("exp1"))
        assert runner.orchestrator.experiment_count == 1

        runner.run_experiment(self._make_scenario("exp2"))
        assert runner.orchestrator.experiment_count == 2

    def test_get_status(self) -> None:
        runner = self._make_runner()
        status = runner.get_status()

        assert "orchestrator_state" in status
        assert "observer_state" in status
        assert "fleet_status" in status
        assert "bus_stats" in status
        assert status["dry_run"] is True

    def test_experiment_with_node_failure_scenario(self) -> None:
        runner = self._make_runner(num_agents=10, adversarial_ratio=0.3)
        scenario = {
            "name": "node_failure_test",
            "hypothesis": "Finality maintained when 20% of nodes fail",
            "fault_sequence": [
                {"time": "0s", "action": "baseline"},
                {"time": "60s", "action": "kill_nodes", "params": {"percent": 20}},
            ],
            "slo_thresholds": {
                "finality_delay_max_epochs": 5,
            },
            "blast_radius": {
                "max_affected_percent": 20,
            },
        }

        result = runner.run_experiment(scenario)
        assert result.success

    def test_observer_receives_events(self) -> None:
        runner = self._make_runner(num_agents=5)
        scenario = self._make_scenario()

        result = runner.run_experiment(scenario)

        # Observer should have at least start/end events
        assert len(result.observation_events) >= 2  # start + end events


class TestExperimentRunnerIntegration:
    """Integration tests for the ExperimentRunner with messaging."""

    def test_message_bus_records_events(self) -> None:
        runner = self._make_runner(num_agents=5)
        scenario = self._make_scenario()

        runner.run_experiment(scenario)

        # Check message bus has recorded events
        bus_stats = runner.message_coordinator.bus.get_stats()
        assert bus_stats["messages_published"] > 0

    def test_fleet_agents_registered_in_coordinator(self) -> None:
        runner = self._make_runner(num_agents=5)
        scenario = self._make_scenario()

        runner.run_experiment(scenario)

        # During experiment, agents should have been registered
        # After cleanup they are stopped but coordinator tracks them
        assert runner.node_coordinator.fleet_size == 5

    def _make_runner(
        self,
        num_agents: int = 10,
        adversarial_ratio: float = 0.3,
    ) -> ExperimentRunner:
        config = ExperimentRunnerConfig(
            fleet_config=FleetConfig(
                num_agents=num_agents,
                adversarial_ratio=adversarial_ratio,
            ),
            dry_run=True,
        )
        return ExperimentRunner(config)

    def _make_scenario(self, name: str = "integration_test") -> dict:
        return {
            "name": name,
            "hypothesis": "Network handles latency injection",
            "fault_sequence": [
                {"time": "0s", "action": "baseline"},
                {"time": "60s", "action": "inject_network_latency"},
            ],
            "slo_thresholds": {
                "finality_delay_max_epochs": 5,
            },
        }
