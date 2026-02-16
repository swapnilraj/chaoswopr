"""Cross-track integration tests validating interactions between components.

Tests that components from different tracks work together:
- Safety (Track C) + Monitoring (Track B): Circuit breakers use alert rules
- Schema (Track D) + Storage (Track D): Scenarios stored in PostgreSQL
- Testnet (Track A) + Safety (Track C): Blast radius limits on deployments
- Monitoring (Track B) + Safety (Track C): Metrics drive circuit breaker decisions
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine

from chaoswopr.infrastructure.monitoring.alerting import AlertRuleSet
from chaoswopr.infrastructure.monitoring.metrics_catalog import (
    MetricCategory,
    MetricsCatalog,
)
from chaoswopr.infrastructure.testnet.client_config import ClientConfig
from chaoswopr.infrastructure.testnet.ethereum_package import EthereumPackageConfig
from chaoswopr.safety.audit import ActionType, AuditLogger, Outcome
from chaoswopr.safety.blast_radius import BlastRadiusConfig, validate_blast_radius
from chaoswopr.safety.circuit_breaker import CircuitBreaker, ThresholdConfig
from chaoswopr.safety.kill_switch import KillSwitch
from chaoswopr.safety.snapshots import DockerSnapshotBackend, SnapshotManager
from chaoswopr.scenarios.validator import validate_scenario
from chaoswopr.storage.models import Base, ExperimentStatus
from chaoswopr.storage.postgres import PostgresStorage


class TestSafetyMonitoringIntegration:
    """Tests for Safety (Track C) + Monitoring (Track B) integration."""

    def test_alert_rules_match_circuit_breaker_thresholds(self) -> None:
        """Alert rules and circuit breaker thresholds should be aligned."""
        ruleset = AlertRuleSet()
        thresholds = ThresholdConfig()

        # Circuit breaker has finality, slashing, participation checks
        # Alert rules should have corresponding rules
        cb_rules = ruleset.get_circuit_breaker_rules()
        rule_names = [r.name for r in cb_rules]

        assert any("Finality" in n for n in rule_names), "No finality alert rule"
        assert any("Slashing" in n for n in rule_names), "No slashing alert rule"
        assert any("Participation" in n for n in rule_names), "No participation alert rule"

    def test_critical_metrics_have_circuit_breaker_coverage(self) -> None:
        """Critical metrics in the catalog should be covered by circuit breaker."""
        catalog = MetricsCatalog()
        critical = catalog.get_critical_metrics()

        # At minimum: finality, participation, slashing must be critical
        critical_names = [m.name for m in critical]
        assert any("finality" in n for n in critical_names)
        assert any("participation" in n for n in critical_names)
        assert any("slashing" in n for n in critical_names)

    def test_circuit_breaker_trips_on_metric_values(self) -> None:
        """Circuit breaker should trip when metrics indicate danger."""
        breaker = CircuitBreaker()
        audit = AuditLogger(default_agent_id="circuit_breaker")

        # Simulate dangerous metrics
        result = breaker.check_metrics({
            "finality_delay_seconds": 700.0,
        })
        assert not result
        assert breaker.is_tripped

        # Log the trip
        audit.log(
            ActionType.CIRCUIT_BREAKER_TRIP,
            "experiment",
            Outcome.SUCCESS,
            parameters={"reason": breaker.trip_events[0].reason},
        )
        entries = audit.get_entries(action_type=ActionType.CIRCUIT_BREAKER_TRIP.value)
        assert len(entries) == 1


class TestSchemaStorageIntegration:
    """Tests for Schema (Track D) + Storage (Track D) integration."""

    @pytest.fixture
    def storage(self) -> PostgresStorage:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        return PostgresStorage(engine=engine)

    def test_validated_scenario_can_be_stored(
        self,
        storage: PostgresStorage,
        valid_scenario_yaml: dict[str, Any],
    ) -> None:
        """A validated scenario should be storable in the database."""
        result = validate_scenario(valid_scenario_yaml)
        assert result.valid

        stored = storage.store_scenario(
            name=valid_scenario_yaml["name"],
            hypothesis=valid_scenario_yaml["hypothesis"],
            config=valid_scenario_yaml,
        )
        assert stored.id is not None

        retrieved = storage.get_scenario(valid_scenario_yaml["name"])
        assert retrieved is not None
        assert retrieved.config["hypothesis"] == valid_scenario_yaml["hypothesis"]

    def test_experiment_run_lifecycle(
        self,
        storage: PostgresStorage,
    ) -> None:
        """An experiment run should track full lifecycle in the database."""
        # Create
        exp = storage.create_experiment(
            scenario_name="baseline_observation",
            hypothesis="Network stays healthy",
            node_count=50,
        )
        assert exp.status == "pending"

        # Start
        storage.update_experiment_status(exp.id, ExperimentStatus.RUNNING)
        running = storage.get_experiment(exp.id)
        assert running is not None
        assert running.status == "running"
        assert running.started_at is not None

        # Store metrics
        storage.store_metric(exp.id, "finality_delay", 13.0, phase="baseline")
        storage.store_metric(exp.id, "participation_rate", 96.5, phase="baseline")
        metrics = storage.get_metrics(exp.id, phase="baseline")
        assert len(metrics) == 2

        # Complete
        storage.update_experiment_status(
            exp.id,
            ExperimentStatus.COMPLETED,
            results={"passed": True, "metric_count": 2},
        )
        completed = storage.get_experiment(exp.id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.results["passed"] is True


class TestTestnetSafetyIntegration:
    """Tests for Testnet (Track A) + Safety (Track C) integration."""

    def test_deployment_config_respects_blast_radius(self) -> None:
        """Deployment config should be compatible with blast radius limits."""
        config = EthereumPackageConfig()
        blast = BlastRadiusConfig()

        node_count = config.client_config.node_count
        max_affected = int(node_count * blast.max_affected_percent / 100)

        # Must never exceed 33% of nodes
        assert max_affected <= int(node_count * 0.33) + 1

    def test_blast_radius_validates_against_client_config(self) -> None:
        """Blast radius validation should work with real client configs."""
        client_config = ClientConfig(node_count=100)
        blast_config = BlastRadiusConfig(max_affected_percent=20.0)

        el_counts = client_config.get_execution_counts()
        is_valid, violations = validate_blast_radius(
            blast_config,
            total_nodes=100,
            requested_nodes=20,
            client_counts=el_counts,
            requested_by_client={"nethermind": 10},
        )
        assert is_valid, f"Violations: {violations}"

    def test_blast_radius_blocks_excessive_request(self) -> None:
        """Blast radius must block requests that affect too many nodes."""
        blast_config = BlastRadiusConfig(max_affected_percent=20.0)

        is_valid, violations = validate_blast_radius(
            blast_config,
            total_nodes=100,
            requested_nodes=50,
        )
        assert not is_valid
        assert len(violations) > 0


class TestFullExperimentPipeline:
    """End-to-end pipeline test combining all tracks."""

    def test_experiment_pipeline_with_audit(self) -> None:
        """Full experiment pipeline from scenario to audit log."""
        # Track D: Validate scenario
        from chaoswopr.scenarios.validator import validate_scenario

        scenario = {
            "version": "1.0",
            "name": "integration_test",
            "description": "Integration test scenario",
            "hypothesis": "The system components integrate correctly across all tracks",
            "network_config": {
                "node_count": 50,
                "client_distribution": {
                    "execution": {"nethermind": 0.5, "geth": 0.5},
                    "consensus": {"prysm": 0.5, "lighthouse": 0.5},
                },
            },
            "fault_sequence": [
                {"time": "0s", "action": "baseline", "description": "Start"},
                {"time": "60s", "action": "complete", "description": "End"},
            ],
            "slo_thresholds": {
                "finality_delay_max_epochs": 5,
                "slashing_rate_max_percent": 5.0,
                "participation_rate_min_percent": 66.0,
            },
            "blast_radius": {"max_affected_percent": 0.0, "phased_rollout": []},
            "success_criteria": "All components work together in the full pipeline test",
            "tags": ["integration"],
        }
        result = validate_scenario(scenario)
        assert result.valid

        # Track C: Set up safety
        breaker = CircuitBreaker()
        snapshot_mgr = SnapshotManager(DockerSnapshotBackend())
        audit = AuditLogger(default_agent_id="orchestrator")

        # Track A: Deploy testnet (dry-run)
        config = EthereumPackageConfig.from_dict(scenario)
        from chaoswopr.infrastructure.testnet.deployer import TestnetDeployer
        from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient

        deployer = TestnetDeployer(
            kurtosis_client=KurtosisClient(dry_run=True),
            package_config=config,
        )
        deploy_result = deployer.deploy(wait_for_finality=False)
        assert deploy_result.success

        audit.log(ActionType.EXPERIMENT_START, "integration_test", Outcome.SUCCESS)

        # Track C: Create snapshot
        snapshot = snapshot_mgr.create_snapshot(["node-1"], experiment_id="integration-test")
        audit.log(ActionType.SNAPSHOT_CREATE, "integration-test", Outcome.SUCCESS)

        # Track B: Check metrics via circuit breaker
        metrics_ok = breaker.check_metrics({
            "finality_delay_seconds": 13.0,
            "slashing_rate_percent": 0.0,
            "participation_rate_percent": 96.5,
        })
        assert metrics_ok
        audit.log(ActionType.CIRCUIT_BREAKER_CHECK, "integration-test", Outcome.SUCCESS)

        # Complete
        audit.log(ActionType.EXPERIMENT_COMPLETE, "integration_test", Outcome.SUCCESS)

        # Verify audit trail
        all_entries = audit.get_entries()
        assert len(all_entries) == 4
        action_types = [e.action_type for e in all_entries]
        assert "experiment_start" in action_types
        assert "snapshot_create" in action_types
        assert "circuit_breaker_check" in action_types
        assert "experiment_complete" in action_types

        # Cleanup
        assert deployer.destroy()
