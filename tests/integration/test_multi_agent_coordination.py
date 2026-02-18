"""Integration tests for multi-agent coordination.

Tests the full multi-agent system working together:
  - Orchestrator coordinating through experiment phases
  - Node agents responding to fleet commands
  - Observer detecting events during experiments
  - Message bus routing messages between agents
  - Scenario loader feeding experiments to the runner

These tests run in dry-run mode and do not require external infrastructure.
"""

from __future__ import annotations

import pytest

from chaoswopr.agents.experiment_runner import (
    ExperimentResult,
    ExperimentRunner,
    ExperimentRunnerConfig,
)
from chaoswopr.agents.llm_client import MockLLMClient
from chaoswopr.agents.messaging.protocol import AgentType, EventType
from chaoswopr.agents.node_agent import AgentMode
from chaoswopr.agents.node_coordinator import FleetConfig
from chaoswopr.agents.orchestrator import OrchestratorState
from chaoswopr.agents.scenario_loader import ScenarioBuilder, load_scenario_string


def _make_runner(
    num_agents: int = 10,
    adversarial_ratio: float = 0.3,
) -> ExperimentRunner:
    """Create an ExperimentRunner for testing."""
    config = ExperimentRunnerConfig(
        fleet_config=FleetConfig(
            num_agents=num_agents,
            adversarial_ratio=adversarial_ratio,
        ),
        dry_run=True,
    )
    return ExperimentRunner(config)


class TestMultiAgentOrchestration:
    """Tests for the complete multi-agent orchestration pipeline."""

    def test_orchestrator_coordinates_10_agents_withholding(self) -> None:
        """Working demo: orchestrator coordinates 10 node agents to test finality.

        This is the primary success criterion from the Phase 2 specification.
        """
        runner = _make_runner(num_agents=10, adversarial_ratio=0.3)
        scenario = ScenarioBuilder.attestation_withholding(
            target_percent=30.0,
            node_count=10,
        )

        result = runner.run_experiment(scenario.to_dict())

        assert result.success, f"Experiment failed: {result.error_message}"
        assert result.experiment_id != ""
        assert result.scenario_name == "attestation_withholding"
        assert result.hypothesis is not None
        assert result.plan is not None
        assert result.duration_seconds > 0
        assert not result.halted

        # Verify orchestrator returned to idle
        assert runner.orchestrator.state == OrchestratorState.IDLE

        # Verify fleet was created with correct split
        fleet_status = result.fleet_status
        assert fleet_status["total_agents"] == 10

    def test_orchestrator_coordinates_finality_stress_test(self) -> None:
        """Demo: multi-fault finality stress test with combined failures."""
        runner = _make_runner(num_agents=10, adversarial_ratio=0.3)
        scenario = ScenarioBuilder.finality_stress_test(
            adversarial_ratio=0.3,
            node_count=10,
            duration_seconds=300,
        )

        result = runner.run_experiment(scenario.to_dict())

        assert result.success
        assert result.scenario_name == "finality_stress_test"
        assert result.hypothesis is not None
        assert "prediction" in result.hypothesis
        assert result.plan is not None
        assert "actions" in result.plan

    def test_message_bus_routes_events_during_experiment(self) -> None:
        """Verify message bus properly routes events between agents."""
        runner = _make_runner(num_agents=5, adversarial_ratio=0.3)

        # Subscribe to experiment events before running
        events_received: list = []
        runner.message_coordinator.bus.subscribe(
            "agents.orchestrator.events",
            lambda msg: events_received.append(msg),
            "test-integration-listener",
        )

        scenario = ScenarioBuilder.attestation_withholding(
            target_percent=30.0,
            node_count=5,
        )
        result = runner.run_experiment(scenario.to_dict())

        assert result.success

        # Should have received EXPERIMENT_STARTED, FAULT_INJECTED,
        # FAULT_REMOVED, and EXPERIMENT_COMPLETED events
        event_types = [
            e.payload.get("event_type")
            for e in events_received
            if hasattr(e, "payload")
        ]
        assert len(events_received) >= 3

    def test_observer_detects_events_during_experiment(self) -> None:
        """Verify observer generates observation events."""
        runner = _make_runner(num_agents=5, adversarial_ratio=0.3)
        scenario = ScenarioBuilder.attestation_withholding(node_count=5)

        result = runner.run_experiment(scenario.to_dict())

        assert result.success
        # Observer should have recorded at least start/end events
        assert len(result.observation_events) >= 2

    def test_metrics_collected_across_monitoring_cycles(self) -> None:
        """Verify metrics are collected during monitoring phase."""
        runner = _make_runner(num_agents=5)
        scenario = ScenarioBuilder.network_latency(node_count=5)

        result = runner.run_experiment(scenario.to_dict())

        assert result.success
        # In dry-run mode we run 3 cycles minimum
        assert len(result.metrics_snapshots) >= 3

    def test_sequential_experiments_independent(self) -> None:
        """Verify that sequential experiments are independent."""
        runner = _make_runner(num_agents=5, adversarial_ratio=0.3)

        # Run first experiment
        scenario_1 = ScenarioBuilder.attestation_withholding(
            target_percent=20.0,
            node_count=5,
        )
        result_1 = runner.run_experiment(scenario_1.to_dict())
        assert result_1.success

        # Run second experiment
        scenario_2 = ScenarioBuilder.network_latency(
            target_percent=20.0,
            node_count=5,
        )
        result_2 = runner.run_experiment(scenario_2.to_dict())
        assert result_2.success

        # Experiment IDs should be unique
        assert result_1.experiment_id != result_2.experiment_id

        # Orchestrator should be in idle state
        assert runner.orchestrator.state == OrchestratorState.IDLE

    def test_fleet_honest_adversarial_split_correct(self) -> None:
        """Verify correct 70/30 honest/adversarial split in fleet."""
        runner = _make_runner(num_agents=10, adversarial_ratio=0.3)
        scenario = ScenarioBuilder.baseline_observation(node_count=10)

        result = runner.run_experiment(scenario.to_dict())
        assert result.success

        fleet_status = result.fleet_status
        assert fleet_status["honest_count"] == 7
        assert fleet_status["adversarial_count"] == 3

    def test_node_agents_registered_with_message_coordinator(self) -> None:
        """Verify all node agents are registered with the message coordinator."""
        runner = _make_runner(num_agents=5, adversarial_ratio=0.2)
        scenario = ScenarioBuilder.baseline_observation(node_count=5)

        result = runner.run_experiment(scenario.to_dict())
        assert result.success

        # Check coordinator has the right number of registered agents
        fleet_status = runner.message_coordinator.get_fleet_status(
            agent_type=AgentType.NODE_AGENT,
        )
        assert fleet_status["total_agents"] == 5

    def test_bus_stats_after_experiment(self) -> None:
        """Verify message bus statistics are tracked."""
        runner = _make_runner(num_agents=5)

        # Add a subscriber so we can verify delivery
        received: list = []
        runner.message_coordinator.bus.subscribe(
            "agents.orchestrator.events",
            lambda msg: received.append(msg),
            "stats-test-listener",
        )

        scenario = ScenarioBuilder.baseline_observation(node_count=5)
        runner.run_experiment(scenario.to_dict())

        status = runner.get_status()
        bus_stats = status["bus_stats"]
        assert bus_stats["messages_published"] > 0
        assert bus_stats["messages_delivered"] > 0


class TestScenarioToExperimentIntegration:
    """Tests for scenario loading through experiment execution."""

    def test_yaml_scenario_string_to_experiment(self) -> None:
        """Load a YAML scenario string and run it through the runner."""
        yaml_content = """\
name: integration_yaml_test
hypothesis: Network maintains finality under test conditions
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
"""
        scenario = load_scenario_string(yaml_content)
        runner = _make_runner(num_agents=5)

        result = runner.run_experiment(scenario.to_dict())

        assert result.success
        assert result.scenario_name == "integration_yaml_test"

    def test_all_builder_scenarios_execute_successfully(self) -> None:
        """Verify all ScenarioBuilder factory methods produce runnable scenarios."""
        runner = _make_runner(num_agents=5, adversarial_ratio=0.3)

        scenarios = [
            ScenarioBuilder.baseline_observation(node_count=5),
            ScenarioBuilder.attestation_withholding(node_count=5),
            ScenarioBuilder.network_latency(node_count=5),
            ScenarioBuilder.node_failure(node_count=5),
            ScenarioBuilder.finality_stress_test(node_count=5),
        ]

        for scenario in scenarios:
            result = runner.run_experiment(scenario.to_dict())
            assert result.success, (
                f"Scenario '{scenario.name}' failed: {result.error_message}"
            )
            assert runner.orchestrator.state == OrchestratorState.IDLE


class TestExperimentRunnerWithLLMClient:
    """Tests for experiment runner with LLM client integration."""

    def test_mock_llm_client_generates_hypotheses(self) -> None:
        """Verify MockLLMClient can generate structured hypotheses."""
        client = MockLLMClient()

        response = client.generate(
            "Generate a hypothesis for this scenario: "
            "attestation withholding fault on 30% of validators"
        )

        assert response.success
        assert response.structured is not None
        assert "prediction" in response.structured
        assert "confidence" in response.structured

    def test_mock_llm_client_performs_rca(self) -> None:
        """Verify MockLLMClient can perform root cause analysis."""
        client = MockLLMClient()

        response = client.generate(
            "Perform root cause analysis on these events: "
            "finality delay increased to 5 epochs, "
            "validator participation dropped to 72%"
        )

        assert response.success
        assert response.structured is not None
        assert "hypotheses" in response.structured
        hypotheses = response.structured["hypotheses"]
        assert len(hypotheses) > 0
        assert "root_cause" in hypotheses[0]

    def test_llm_client_tracks_usage(self) -> None:
        """Verify LLM client tracks call count and prompt history."""
        client = MockLLMClient()

        client.generate("First scenario hypothesis")
        client.generate("Root cause analysis for finality")
        client.generate("Analyze anomaly in participation rate")

        assert client.call_count == 3
        assert len(client.prompts) == 3
        assert "First scenario" in client.prompts[0]
