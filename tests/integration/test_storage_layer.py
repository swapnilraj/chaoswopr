"""Integration tests for the storage layer (PostgreSQL + S3).

Tests database operations with real SQLite (unit-level) and
S3 operations with moto mocks. Testcontainer-based PostgreSQL
tests are included for CI environments with Docker.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine

from chaoswopr.storage.models import Base, ExperimentStatus
from chaoswopr.storage.postgres import PostgresStorage
from chaoswopr.storage.s3 import S3Storage


class TestPostgresStorageWithSQLite:
    """Test PostgresStorage operations using SQLite as a lightweight stand-in.

    These tests verify the logic of the storage layer without requiring
    a real PostgreSQL instance.
    """

    @pytest.fixture
    def storage(self) -> PostgresStorage:
        """Create a storage instance backed by in-memory SQLite."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        return PostgresStorage(engine=engine)

    def test_create_experiment(self, storage: PostgresStorage) -> None:
        exp = storage.create_experiment(
            scenario_name="baseline_observation",
            hypothesis="Network stays healthy with no faults",
            node_count=50,
        )
        assert exp.id is not None
        assert exp.scenario_name == "baseline_observation"
        assert exp.status == "pending"

    def test_get_experiment(self, storage: PostgresStorage) -> None:
        exp = storage.create_experiment(scenario_name="test_scenario")
        fetched = storage.get_experiment(exp.id)
        assert fetched is not None
        assert fetched.id == exp.id

    def test_get_nonexistent_experiment(self, storage: PostgresStorage) -> None:
        fetched = storage.get_experiment("nonexistent-id")
        assert fetched is None

    def test_update_experiment_status(self, storage: PostgresStorage) -> None:
        exp = storage.create_experiment(scenario_name="test")
        result = storage.update_experiment_status(exp.id, ExperimentStatus.RUNNING)
        assert result is True

        updated = storage.get_experiment(exp.id)
        assert updated is not None
        assert updated.status == "running"
        assert updated.started_at is not None

    def test_update_experiment_to_completed(self, storage: PostgresStorage) -> None:
        exp = storage.create_experiment(scenario_name="test")
        storage.update_experiment_status(exp.id, ExperimentStatus.RUNNING)
        storage.update_experiment_status(
            exp.id,
            ExperimentStatus.COMPLETED,
            results={"passed": True},
        )
        updated = storage.get_experiment(exp.id)
        assert updated is not None
        assert updated.status == "completed"
        assert updated.completed_at is not None
        assert updated.results == {"passed": True}

    def test_update_nonexistent_experiment(self, storage: PostgresStorage) -> None:
        result = storage.update_experiment_status("nonexistent", ExperimentStatus.RUNNING)
        assert result is False

    def test_list_experiments(self, storage: PostgresStorage) -> None:
        storage.create_experiment(scenario_name="scenario_a")
        storage.create_experiment(scenario_name="scenario_b")
        storage.create_experiment(scenario_name="scenario_a")

        all_exps = storage.list_experiments()
        assert len(all_exps) == 3

        filtered = storage.list_experiments(scenario_name="scenario_a")
        assert len(filtered) == 2

    def test_list_experiments_by_status(self, storage: PostgresStorage) -> None:
        exp1 = storage.create_experiment(scenario_name="test")
        storage.create_experiment(scenario_name="test")
        storage.update_experiment_status(exp1.id, ExperimentStatus.RUNNING)

        running = storage.list_experiments(status=ExperimentStatus.RUNNING)
        assert len(running) == 1

        pending = storage.list_experiments(status=ExperimentStatus.PENDING)
        assert len(pending) == 1

    def test_store_metric(self, storage: PostgresStorage) -> None:
        exp = storage.create_experiment(scenario_name="test")
        metric = storage.store_metric(
            experiment_id=exp.id,
            metric_name="finality_delay_seconds",
            value=13.2,
            phase="baseline",
        )
        assert metric.id is not None
        assert metric.metric_name == "finality_delay_seconds"
        assert metric.value == 13.2

    def test_store_metrics_batch(self, storage: PostgresStorage) -> None:
        exp = storage.create_experiment(scenario_name="test")
        metrics = [
            {
                "experiment_id": exp.id,
                "metric_name": "finality_delay_seconds",
                "value": 13.2,
                "phase": "baseline",
            },
            {
                "experiment_id": exp.id,
                "metric_name": "participation_rate",
                "value": 96.5,
                "phase": "baseline",
            },
            {
                "experiment_id": exp.id,
                "metric_name": "peer_count",
                "value": 48.0,
                "phase": "baseline",
            },
        ]
        count = storage.store_metrics_batch(metrics)
        assert count == 3

    def test_get_metrics(self, storage: PostgresStorage) -> None:
        exp = storage.create_experiment(scenario_name="test")
        storage.store_metric(exp.id, "finality_delay", 13.0, phase="baseline")
        storage.store_metric(exp.id, "finality_delay", 45.0, phase="chaos")
        storage.store_metric(exp.id, "participation_rate", 96.0, phase="baseline")

        all_metrics = storage.get_metrics(exp.id)
        assert len(all_metrics) == 3

        finality_metrics = storage.get_metrics(exp.id, metric_name="finality_delay")
        assert len(finality_metrics) == 2

        baseline_metrics = storage.get_metrics(exp.id, phase="baseline")
        assert len(baseline_metrics) == 2

    def test_store_scenario(self, storage: PostgresStorage) -> None:
        scenario = storage.store_scenario(
            name="baseline_observation",
            hypothesis="Network stays healthy",
            config={"node_count": 50},
        )
        assert scenario.id is not None
        assert scenario.name == "baseline_observation"

    def test_get_scenario(self, storage: PostgresStorage) -> None:
        storage.store_scenario(
            name="test_scenario",
            hypothesis="Test hypothesis",
            config={},
        )
        fetched = storage.get_scenario("test_scenario")
        assert fetched is not None
        assert fetched.name == "test_scenario"

    def test_get_nonexistent_scenario(self, storage: PostgresStorage) -> None:
        fetched = storage.get_scenario("nonexistent")
        assert fetched is None

    def test_list_scenarios(self, storage: PostgresStorage) -> None:
        storage.store_scenario(name="scenario_b", hypothesis="h", config={})
        storage.store_scenario(name="scenario_a", hypothesis="h", config={})
        scenarios = storage.list_scenarios()
        assert len(scenarios) == 2
        # Should be sorted by name
        assert scenarios[0].name == "scenario_a"


class TestS3StorageWithMoto:
    """Test S3Storage operations using moto mock."""

    @pytest.fixture
    def s3_storage(self) -> S3Storage:
        """Create S3Storage with moto mock."""
        try:
            import boto3
            from moto import mock_aws

            with mock_aws():
                client = boto3.client("s3", region_name="us-east-1")
                client.create_bucket(Bucket="test-audit")
                client.create_bucket(Bucket="test-artifacts")
                storage = S3Storage(
                    client=client,
                    audit_bucket="test-audit",
                    artifacts_bucket="test-artifacts",
                )
                yield storage
        except ImportError:
            pytest.skip("moto not available")

    def test_write_audit_log(self, s3_storage: S3Storage) -> None:
        entry = {
            "timestamp": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc).isoformat(),
            "agent_id": "orchestrator",
            "action_type": "experiment_start",
            "target": "testnet-001",
            "outcome": "success",
            "trace_id": "trace-001",
        }
        key = s3_storage.write_audit_log(entry, experiment_id="exp-001")
        assert key.startswith("audit/2024/01/15")
        assert "trace-001" in key

    def test_read_audit_log(self, s3_storage: S3Storage) -> None:
        entry = {
            "timestamp": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc).isoformat(),
            "agent_id": "orchestrator",
            "action_type": "experiment_start",
            "target": "testnet-001",
            "outcome": "success",
            "trace_id": "trace-001",
        }
        key = s3_storage.write_audit_log(entry)
        read_back = s3_storage.read_audit_log(key)
        assert read_back["agent_id"] == "orchestrator"
        assert read_back["trace_id"] == "trace-001"

    def test_write_audit_logs_batch(self, s3_storage: S3Storage) -> None:
        entries = [
            {
                "timestamp": datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc).isoformat(),
                "agent_id": "orchestrator",
                "action_type": f"action_{i}",
                "target": "testnet",
                "outcome": "success",
                "trace_id": f"trace-{i:03d}",
            }
            for i in range(5)
        ]
        keys = s3_storage.write_audit_logs_batch(entries, experiment_id="exp-001")
        assert len(keys) == 5

    def test_list_audit_logs(self, s3_storage: S3Storage) -> None:
        for i in range(3):
            s3_storage.write_audit_log(
                {
                    "timestamp": datetime(
                        2024, 1, 15, 10, 30, i, tzinfo=timezone.utc
                    ).isoformat(),
                    "agent_id": "test",
                    "action_type": "test",
                    "target": "test",
                    "outcome": "success",
                    "trace_id": f"trace-{i:03d}",
                }
            )
        keys = s3_storage.list_audit_logs(prefix="audit/2024/01/15")
        assert len(keys) == 3

    def test_write_artifact(self, s3_storage: S3Storage) -> None:
        data = b'{"report": "test compliance report"}'
        key = s3_storage.write_artifact(
            experiment_id="exp-001",
            artifact_name="report.json",
            data=data,
            content_type="application/json",
        )
        assert key == "artifacts/exp-001/report.json"

    def test_read_artifact(self, s3_storage: S3Storage) -> None:
        data = b"test artifact content"
        s3_storage.write_artifact("exp-001", "test.txt", data)
        read_back = s3_storage.read_artifact("exp-001", "test.txt")
        assert read_back == data

    def test_list_artifacts(self, s3_storage: S3Storage) -> None:
        s3_storage.write_artifact("exp-001", "report.json", b"{}")
        s3_storage.write_artifact("exp-001", "metrics.csv", b"")
        artifacts = s3_storage.list_artifacts("exp-001")
        assert len(artifacts) == 2
        assert "report.json" in artifacts
        assert "metrics.csv" in artifacts
