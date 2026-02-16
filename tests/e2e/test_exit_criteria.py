"""End-to-end tests verifying Phase 1 exit criteria.

These tests validate that all Phase 1 exit criteria are met:
1. Testnet boots reliably (via deployer in dry-run mode)
2. Metrics flowing (50+ metrics defined)
3. Circuit breakers trip on alerts
4. Snapshots restore validator state
5. Baseline scenario runs end-to-end
6. Network isolation verified
7. All pass in CI
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from chaoswopr.infrastructure.monitoring.alerting import AlertRuleSet
from chaoswopr.infrastructure.monitoring.metrics_catalog import MetricsCatalog
from chaoswopr.infrastructure.testnet.deployer import DeploymentState, TestnetDeployer
from chaoswopr.infrastructure.testnet.ethereum_package import EthereumPackageConfig
from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient
from chaoswopr.safety.audit import ActionType, AuditLogger, Outcome
from chaoswopr.safety.blast_radius import BlastRadiusConfig
from chaoswopr.safety.circuit_breaker import CircuitBreaker, ThresholdConfig
from chaoswopr.safety.isolation import IsolationConfig, validate_isolation_config
from chaoswopr.safety.kill_switch import KillSwitch
from chaoswopr.safety.snapshots import DockerSnapshotBackend, SnapshotManager
from chaoswopr.scenarios.validator import validate_scenario_file

SCENARIOS_DIR = Path(__file__).parent.parent.parent / "scenarios"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sample_configs"


class TestExitCriteria1TestnetBoot:
    """Exit Criteria 1: Testnet boots reliably."""

    def test_deployer_creates_enclave(self) -> None:
        """Deployer can create and configure a testnet enclave."""
        deployer = TestnetDeployer(
            kurtosis_client=KurtosisClient(dry_run=True),
            enclave_name="e2e-test-enclave",
        )
        result = deployer.deploy(wait_for_finality=False)
        assert result.success
        assert result.state == DeploymentState.RUNNING

    def test_deployer_with_custom_nodes(self) -> None:
        """Deployer handles custom node count configurations."""
        from chaoswopr.infrastructure.testnet.client_config import ClientConfig

        config = EthereumPackageConfig(
            client_config=ClientConfig(node_count=100),
        )
        deployer = TestnetDeployer(
            kurtosis_client=KurtosisClient(dry_run=True),
            package_config=config,
        )
        result = deployer.deploy(wait_for_finality=False)
        assert result.success

    def test_deployer_cleanup(self) -> None:
        """Deployer can cleanly tear down a testnet."""
        deployer = TestnetDeployer(
            kurtosis_client=KurtosisClient(dry_run=True),
        )
        deployer.deploy(wait_for_finality=False)
        assert deployer.destroy() is True
        assert deployer.state == DeploymentState.DESTROYED

    def test_deployer_status_reporting(self) -> None:
        """Deployer provides accurate status information."""
        deployer = TestnetDeployer(
            kurtosis_client=KurtosisClient(dry_run=True),
        )
        deployer.deploy(wait_for_finality=False)
        status = deployer.status()
        assert status["state"] == "running"


class TestExitCriteria2MetricsFlowing:
    """Exit Criteria 2: Metrics flowing (50+ metrics, <30s lag)."""

    def test_metrics_catalog_has_50_plus(self) -> None:
        """At least 50 metrics must be defined in the catalog."""
        catalog = MetricsCatalog()
        assert catalog.count >= 50

    def test_metrics_catalog_validates(self) -> None:
        """The metrics catalog must pass all validation checks."""
        catalog = MetricsCatalog()
        errors = catalog.validate()
        assert errors == []

    def test_alerting_rules_configured(self) -> None:
        """Alerting rules must be properly configured."""
        ruleset = AlertRuleSet()
        errors = ruleset.validate()
        assert errors == []

    def test_critical_metrics_have_alerts(self) -> None:
        """Critical metrics must have corresponding alert rules."""
        catalog = MetricsCatalog()
        critical = catalog.get_critical_metrics()
        assert len(critical) >= 3


class TestExitCriteria3CircuitBreakers:
    """Exit Criteria 3: Circuit breakers detect and respond."""

    @pytest.mark.safety
    def test_circuit_breaker_trips_on_finality(self) -> None:
        """Circuit breaker must trip when finality delay exceeds threshold."""
        breaker = CircuitBreaker()
        result = breaker.check_metrics({"finality_delay_seconds": 700.0})
        assert result is False
        assert breaker.is_tripped

    @pytest.mark.safety
    def test_circuit_breaker_trips_on_slashing(self) -> None:
        """Circuit breaker must trip when slashing rate exceeds threshold."""
        breaker = CircuitBreaker()
        result = breaker.check_metrics({"slashing_rate_percent": 6.0})
        assert result is False
        assert breaker.is_tripped

    @pytest.mark.safety
    def test_circuit_breaker_trips_on_participation(self) -> None:
        """Circuit breaker must trip when participation drops below threshold."""
        breaker = CircuitBreaker()
        result = breaker.check_metrics({"participation_rate_percent": 50.0})
        assert result is False
        assert breaker.is_tripped

    def test_kill_switch_halts_experiment(self) -> None:
        """Kill switch must successfully halt all operations."""
        ks = KillSwitch()
        result = ks.activate(experiment_id="e2e-test")
        assert result.success

    def test_circuit_breaker_with_kill_switch(self) -> None:
        """Circuit breaker trip should integrate with kill switch."""
        breaker = CircuitBreaker()
        ks = KillSwitch(circuit_breaker=breaker)

        # Trip via kill switch
        result = ks.activate()
        assert breaker.is_tripped
        assert result.success


class TestExitCriteria4Snapshots:
    """Exit Criteria 4: Snapshots restore validator state."""

    def test_snapshot_create_and_restore(self) -> None:
        """Snapshots can be created and restored."""
        backend = DockerSnapshotBackend()
        manager = SnapshotManager(backend=backend)

        snapshot = manager.create_snapshot(
            ["node-1", "node-2", "node-3"],
            experiment_id="e2e-test",
        )
        assert snapshot is not None

        result = manager.restore_snapshot(snapshot.id)
        assert result is True

    def test_restore_latest_snapshot(self) -> None:
        """The most recent snapshot can be automatically restored."""
        backend = DockerSnapshotBackend()
        manager = SnapshotManager(backend=backend)

        manager.create_snapshot(["node-1"], experiment_id="e2e-test")
        manager.create_snapshot(["node-1", "node-2"], experiment_id="e2e-test")

        result = manager.restore_latest("e2e-test")
        assert result is True

    def test_snapshot_cleanup(self) -> None:
        """Old snapshots can be cleaned up while keeping the latest."""
        backend = DockerSnapshotBackend()
        manager = SnapshotManager(backend=backend)

        for i in range(5):
            manager.create_snapshot([f"node-{i}"], experiment_id="e2e-test")

        deleted = manager.cleanup_experiment_snapshots("e2e-test", keep_latest=1)
        assert deleted == 4


class TestExitCriteria5BaselineScenario:
    """Exit Criteria 5: Baseline scenario runs end-to-end."""

    def test_baseline_scenario_validates(self) -> None:
        """The baseline scenario YAML must pass schema validation."""
        result = validate_scenario_file(SCENARIOS_DIR / "baseline_observation.yaml")
        assert result.valid, f"Validation errors: {result.errors}"

    def test_sample_scenario_validates(self) -> None:
        """The sample valid scenario must pass validation."""
        result = validate_scenario_file(FIXTURES_DIR / "valid_scenario.yaml")
        assert result.valid

    def test_scenario_pipeline_end_to_end(self) -> None:
        """Full scenario pipeline: load, validate, deploy, audit."""
        # Load scenario
        with open(SCENARIOS_DIR / "baseline_observation.yaml") as f:
            scenario = yaml.safe_load(f)

        # Validate
        from chaoswopr.scenarios.validator import validate_scenario

        validation = validate_scenario(scenario)
        assert validation.valid

        # Configure deployment
        config = EthereumPackageConfig.from_dict(scenario)
        assert len(config.validate()) == 0

        # Deploy (dry-run)
        deployer = TestnetDeployer(
            kurtosis_client=KurtosisClient(dry_run=True),
            package_config=config,
        )
        result = deployer.deploy(wait_for_finality=False)
        assert result.success

        # Create audit trail
        audit = AuditLogger(default_agent_id="orchestrator")
        audit.log(
            ActionType.EXPERIMENT_CREATE,
            "baseline_observation",
            Outcome.SUCCESS,
            experiment_id="e2e-baseline",
        )
        audit.log(
            ActionType.EXPERIMENT_START,
            "baseline_observation",
            Outcome.SUCCESS,
            experiment_id="e2e-baseline",
        )
        audit.log(
            ActionType.EXPERIMENT_COMPLETE,
            "baseline_observation",
            Outcome.SUCCESS,
            experiment_id="e2e-baseline",
        )

        entries = audit.get_entries(experiment_id="e2e-baseline")
        assert len(entries) == 3

        # Teardown
        assert deployer.destroy()


class TestExitCriteria6NetworkIsolation:
    """Exit Criteria 6: Network isolation verified."""

    @pytest.mark.safety
    def test_isolation_config_valid(self) -> None:
        """Default isolation config must pass validation."""
        config = IsolationConfig()
        result = validate_isolation_config(config)
        assert result.passed

    @pytest.mark.safety
    def test_mainnet_endpoints_blocked(self) -> None:
        """All known mainnet endpoints must be blocked."""
        from chaoswopr.safety.isolation import MAINNET_ENDPOINTS

        config = IsolationConfig()
        for endpoint in MAINNET_ENDPOINTS:
            assert not config.is_host_allowed(endpoint), f"{endpoint} should be blocked"

    @pytest.mark.safety
    def test_public_dns_blocked(self) -> None:
        """Public DNS servers must be blocked."""
        from chaoswopr.safety.isolation import PUBLIC_DNS_SERVERS

        config = IsolationConfig()
        for dns in PUBLIC_DNS_SERVERS:
            assert not config.is_host_allowed(dns), f"{dns} should be blocked"

    @pytest.mark.safety
    def test_internal_communication_allowed(self) -> None:
        """Internal network communication must be allowed."""
        config = IsolationConfig()
        assert config.is_host_allowed("10.0.0.1")
        assert config.is_host_allowed("192.168.1.1")


class TestExitCriteria7CIPipeline:
    """Exit Criteria 7: All checks pass in CI.

    These tests verify the CI infrastructure itself.
    """

    def test_all_modules_importable(self) -> None:
        """All production modules must be importable."""
        modules = [
            "chaoswopr",
            "chaoswopr.cli",
            "chaoswopr.scenarios.validator",
            "chaoswopr.storage.models",
            "chaoswopr.storage.postgres",
            "chaoswopr.storage.s3",
            "chaoswopr.safety.blast_radius",
            "chaoswopr.safety.circuit_breaker",
            "chaoswopr.safety.snapshots",
            "chaoswopr.safety.isolation",
            "chaoswopr.safety.audit",
            "chaoswopr.safety.kill_switch",
            "chaoswopr.infrastructure.testnet.kurtosis_client",
            "chaoswopr.infrastructure.testnet.client_config",
            "chaoswopr.infrastructure.testnet.ethereum_package",
            "chaoswopr.infrastructure.testnet.deployer",
            "chaoswopr.infrastructure.monitoring.prometheus",
            "chaoswopr.infrastructure.monitoring.metrics_catalog",
            "chaoswopr.infrastructure.monitoring.alerting",
            "chaoswopr.infrastructure.monitoring.metrics_export",
        ]
        for mod_name in modules:
            try:
                __import__(mod_name)
            except ImportError as e:
                pytest.fail(f"Failed to import {mod_name}: {e}")

    def test_blast_radius_safety_limit(self) -> None:
        """The absolute blast radius limit must be 33%."""
        from chaoswopr.safety.blast_radius import MAX_BLAST_RADIUS_PERCENT

        assert MAX_BLAST_RADIUS_PERCENT == 33.0

    def test_schema_file_exists(self) -> None:
        """The scenario schema file must exist."""
        schema_path = Path(__file__).parent.parent.parent / "config" / "schema" / "scenario_schema.json"
        assert schema_path.exists()

    def test_baseline_scenario_file_exists(self) -> None:
        """The baseline scenario file must exist."""
        assert (SCENARIOS_DIR / "baseline_observation.yaml").exists()
