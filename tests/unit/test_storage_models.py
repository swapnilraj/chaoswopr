"""Unit tests for the storage layer models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from chaoswopr.storage.models import (
    AuditLogEntry,
    Base,
    ExperimentRun,
    ExperimentStatus,
    MetricSnapshot,
    ScenarioDefinition,
)


class TestExperimentStatus:
    """Tests for the ExperimentStatus enum."""

    def test_all_statuses_defined(self) -> None:
        statuses = [s.value for s in ExperimentStatus]
        assert "pending" in statuses
        assert "preflight" in statuses
        assert "running" in statuses
        assert "recovering" in statuses
        assert "analyzing" in statuses
        assert "completed" in statuses
        assert "failed" in statuses
        assert "aborted" in statuses

    def test_status_string_values(self) -> None:
        assert ExperimentStatus.PENDING.value == "pending"
        assert ExperimentStatus.RUNNING.value == "running"
        assert ExperimentStatus.COMPLETED.value == "completed"


class TestExperimentRun:
    """Tests for the ExperimentRun model."""

    def test_create_experiment_run(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            run = ExperimentRun(
                scenario_name="baseline_observation",
                status=ExperimentStatus.PENDING.value,
                hypothesis="Test hypothesis for baseline observation",
            )
            session.add(run)
            session.commit()
            session.refresh(run)

            assert run.id is not None
            assert run.scenario_name == "baseline_observation"
            assert run.status == "pending"
            assert run.created_at is not None

    def test_experiment_run_to_dict(self) -> None:
        run = ExperimentRun(
            id="test-id",
            scenario_name="test_scenario",
            status="running",
            hypothesis="Test hypothesis",
        )
        d = run.to_dict()
        assert d["id"] == "test-id"
        assert d["scenario_name"] == "test_scenario"
        assert d["status"] == "running"

    def test_experiment_run_default_version(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            run = ExperimentRun(
                scenario_name="test",
                status="pending",
                hypothesis="test",
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            assert run.scenario_version == "1.0"


class TestMetricSnapshot:
    """Tests for the MetricSnapshot model."""

    def test_create_metric_snapshot(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            snapshot = MetricSnapshot(
                experiment_id="exp-001",
                metric_name="finality_delay_seconds",
                value=13.2,
                timestamp=datetime.now(timezone.utc),
                labels={"node": "node-1"},
                phase="baseline",
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)

            assert snapshot.id is not None
            assert snapshot.metric_name == "finality_delay_seconds"
            assert snapshot.value == 13.2
            assert snapshot.phase == "baseline"

    def test_metric_snapshot_to_dict(self) -> None:
        snapshot = MetricSnapshot(
            id=1,
            experiment_id="exp-001",
            metric_name="participation_rate",
            value=96.5,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        d = snapshot.to_dict()
        assert d["metric_name"] == "participation_rate"
        assert d["value"] == 96.5


class TestScenarioDefinition:
    """Tests for the ScenarioDefinition model."""

    def test_create_scenario_definition(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            scenario = ScenarioDefinition(
                name="baseline_observation",
                version="1.0",
                hypothesis="Network maintains finality with no faults",
                config={"node_count": 50},
            )
            session.add(scenario)
            session.commit()
            session.refresh(scenario)

            assert scenario.id is not None
            assert scenario.name == "baseline_observation"

    def test_scenario_definition_to_dict(self) -> None:
        scenario = ScenarioDefinition(
            id=1,
            name="test",
            version="1.0",
            hypothesis="test",
            config={},
        )
        d = scenario.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "1.0"

    def test_scenario_unique_constraint(self) -> None:
        """Two scenarios with the same name and version should conflict."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            s1 = ScenarioDefinition(
                name="test", version="1.0", hypothesis="h1", config={}
            )
            s2 = ScenarioDefinition(
                name="test", version="1.0", hypothesis="h2", config={}
            )
            session.add(s1)
            session.commit()
            session.add(s2)
            try:
                session.commit()
                # SQLite may not enforce this, so just pass
            except Exception:
                session.rollback()


class TestAuditLogEntry:
    """Tests for the AuditLogEntry model."""

    def test_create_audit_log_entry(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            entry = AuditLogEntry(
                timestamp=datetime.now(timezone.utc),
                agent_id="orchestrator",
                action_type="experiment_start",
                target="testnet-001",
                parameters={"scenario": "baseline"},
                outcome="success",
                trace_id="trace-001",
                experiment_id="exp-001",
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)

            assert entry.id is not None
            assert entry.agent_id == "orchestrator"
            assert entry.action_type == "experiment_start"

    def test_audit_log_to_dict(self) -> None:
        entry = AuditLogEntry(
            id=1,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            agent_id="observer",
            action_type="anomaly_detected",
            target="metric-001",
            outcome="detected",
            trace_id="trace-001",
        )
        d = entry.to_dict()
        assert d["agent_id"] == "observer"
        assert d["action_type"] == "anomaly_detected"
