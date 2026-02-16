"""PostgreSQL storage client for chaoswopr.

Provides database operations for experiment runs, metric snapshots,
scenario definitions, and audit log entries.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from chaoswopr.storage.models import (
    AuditLogEntry,
    Base,
    ExperimentRun,
    ExperimentStatus,
    MetricSnapshot,
    ScenarioDefinition,
)


def get_database_url() -> str:
    """Build the database URL from environment variables.

    Returns:
        PostgreSQL connection URL.
    """
    host = os.environ.get("CHAOSWOPR_DB_HOST", "localhost")
    port = os.environ.get("CHAOSWOPR_DB_PORT", "5432")
    name = os.environ.get("CHAOSWOPR_DB_NAME", "chaoswopr")
    user = os.environ.get("CHAOSWOPR_DB_USER", "chaoswopr")
    password = os.environ.get("CHAOSWOPR_DB_PASSWORD", "chaoswopr")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def create_db_engine(url: str | None = None, echo: bool = False) -> Engine:
    """Create a SQLAlchemy database engine.

    Args:
        url: Database URL. Defaults to environment-based URL.
        echo: Whether to echo SQL statements.

    Returns:
        SQLAlchemy Engine instance.
    """
    db_url = url or get_database_url()
    return create_engine(db_url, echo=echo, pool_pre_ping=True)


def create_tables(engine: Engine) -> None:
    """Create all database tables.

    Args:
        engine: SQLAlchemy Engine instance.
    """
    Base.metadata.create_all(engine)


def drop_tables(engine: Engine) -> None:
    """Drop all database tables.

    Args:
        engine: SQLAlchemy Engine instance.
    """
    Base.metadata.drop_all(engine)


class PostgresStorage:
    """PostgreSQL storage client for chaoswopr.

    Provides CRUD operations for all database models with
    proper session management and error handling.
    """

    def __init__(self, engine: Engine | None = None, url: str | None = None) -> None:
        """Initialize the storage client.

        Args:
            engine: Pre-configured SQLAlchemy Engine. Takes priority over url.
            url: Database URL. Used to create engine if engine is not provided.
        """
        self._engine = engine or create_db_engine(url)
        self._session_factory = sessionmaker(bind=self._engine)

    @property
    def engine(self) -> Engine:
        """Get the database engine."""
        return self._engine

    def get_session(self) -> Session:
        """Create a new database session.

        Returns:
            New SQLAlchemy Session.
        """
        return self._session_factory()

    def initialize(self) -> None:
        """Create all tables if they do not exist."""
        create_tables(self._engine)

    def health_check(self) -> bool:
        """Check database connectivity.

        Returns:
            True if the database is reachable.
        """
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------
    # Experiment Run operations
    # -------------------------------------------------------------------

    def create_experiment(
        self,
        scenario_name: str,
        config: dict[str, Any] | None = None,
        hypothesis: str | None = None,
        node_count: int | None = None,
        blast_radius_percent: float | None = None,
    ) -> ExperimentRun:
        """Create a new experiment run record.

        Args:
            scenario_name: Name of the scenario being run.
            config: Full experiment configuration.
            hypothesis: The hypothesis being tested.
            node_count: Number of nodes in the testnet.
            blast_radius_percent: Maximum blast radius for this experiment.

        Returns:
            The created ExperimentRun instance.
        """
        with self.get_session() as session:
            experiment = ExperimentRun(
                scenario_name=scenario_name,
                config=config,
                hypothesis=hypothesis,
                node_count=node_count,
                blast_radius_percent=blast_radius_percent,
            )
            session.add(experiment)
            session.commit()
            session.refresh(experiment)
            return experiment

    def get_experiment(self, experiment_id: str) -> ExperimentRun | None:
        """Get an experiment run by ID.

        Args:
            experiment_id: The experiment UUID.

        Returns:
            ExperimentRun or None if not found.
        """
        with self.get_session() as session:
            return session.query(ExperimentRun).filter_by(id=experiment_id).first()

    def update_experiment_status(
        self,
        experiment_id: str,
        status: ExperimentStatus,
        error_message: str | None = None,
        results: dict[str, Any] | None = None,
    ) -> bool:
        """Update the status of an experiment run.

        Args:
            experiment_id: The experiment UUID.
            status: New status value.
            error_message: Error message if status is FAILED.
            results: Experiment results if status is COMPLETED.

        Returns:
            True if the experiment was found and updated.
        """
        with self.get_session() as session:
            experiment = session.query(ExperimentRun).filter_by(id=experiment_id).first()
            if not experiment:
                return False

            experiment.status = status.value
            now = datetime.now(timezone.utc)

            if status == ExperimentStatus.RUNNING and not experiment.started_at:
                experiment.started_at = now

            if status in (
                ExperimentStatus.COMPLETED,
                ExperimentStatus.FAILED,
                ExperimentStatus.ABORTED,
            ):
                experiment.completed_at = now
                if experiment.started_at:
                    started = experiment.started_at
                    # Ensure timezone-aware comparison (SQLite stores naive datetimes)
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    experiment.duration_seconds = (now - started).total_seconds()

            if error_message:
                experiment.error_message = error_message
            if results:
                experiment.results = results

            session.commit()
            return True

    def list_experiments(
        self,
        status: ExperimentStatus | None = None,
        scenario_name: str | None = None,
        limit: int = 50,
    ) -> list[ExperimentRun]:
        """List experiment runs with optional filtering.

        Args:
            status: Filter by status.
            scenario_name: Filter by scenario name.
            limit: Maximum number of results.

        Returns:
            List of ExperimentRun instances.
        """
        with self.get_session() as session:
            query = session.query(ExperimentRun)
            if status:
                query = query.filter_by(status=status.value)
            if scenario_name:
                query = query.filter_by(scenario_name=scenario_name)
            return query.order_by(ExperimentRun.created_at.desc()).limit(limit).all()

    # -------------------------------------------------------------------
    # Metric Snapshot operations
    # -------------------------------------------------------------------

    def store_metric(
        self,
        experiment_id: str,
        metric_name: str,
        value: float,
        timestamp: datetime | None = None,
        labels: dict[str, str] | None = None,
        phase: str | None = None,
    ) -> MetricSnapshot:
        """Store a metric snapshot.

        Args:
            experiment_id: ID of the associated experiment.
            metric_name: Name of the metric.
            value: Metric value.
            timestamp: Metric timestamp (defaults to now).
            labels: Additional metric labels.
            phase: Experiment phase (baseline, chaos, recovery).

        Returns:
            The created MetricSnapshot instance.
        """
        with self.get_session() as session:
            snapshot = MetricSnapshot(
                experiment_id=experiment_id,
                metric_name=metric_name,
                value=value,
                timestamp=timestamp or datetime.now(timezone.utc),
                labels=labels,
                phase=phase,
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            return snapshot

    def store_metrics_batch(
        self, metrics: list[dict[str, Any]]
    ) -> int:
        """Store multiple metric snapshots in a single transaction.

        Args:
            metrics: List of metric dictionaries with keys:
                experiment_id, metric_name, value, timestamp, labels, phase.

        Returns:
            Number of metrics stored.
        """
        with self.get_session() as session:
            snapshots = [
                MetricSnapshot(
                    experiment_id=m["experiment_id"],
                    metric_name=m["metric_name"],
                    value=m["value"],
                    timestamp=m.get("timestamp", datetime.now(timezone.utc)),
                    labels=m.get("labels"),
                    phase=m.get("phase"),
                )
                for m in metrics
            ]
            session.add_all(snapshots)
            session.commit()
            return len(snapshots)

    def get_metrics(
        self,
        experiment_id: str,
        metric_name: str | None = None,
        phase: str | None = None,
    ) -> list[MetricSnapshot]:
        """Query metrics for an experiment.

        Args:
            experiment_id: ID of the experiment.
            metric_name: Optional filter by metric name.
            phase: Optional filter by experiment phase.

        Returns:
            List of MetricSnapshot instances.
        """
        with self.get_session() as session:
            query = session.query(MetricSnapshot).filter_by(experiment_id=experiment_id)
            if metric_name:
                query = query.filter_by(metric_name=metric_name)
            if phase:
                query = query.filter_by(phase=phase)
            return query.order_by(MetricSnapshot.timestamp).all()

    # -------------------------------------------------------------------
    # Scenario Definition operations
    # -------------------------------------------------------------------

    def store_scenario(
        self,
        name: str,
        hypothesis: str,
        config: dict[str, Any],
        version: str = "1.0",
        description: str | None = None,
    ) -> ScenarioDefinition:
        """Store a scenario definition.

        Args:
            name: Scenario name.
            hypothesis: Scenario hypothesis.
            config: Full scenario configuration.
            version: Scenario version.
            description: Optional description.

        Returns:
            The created ScenarioDefinition instance.
        """
        with self.get_session() as session:
            scenario = ScenarioDefinition(
                name=name,
                version=version,
                description=description,
                hypothesis=hypothesis,
                config=config,
            )
            session.add(scenario)
            session.commit()
            session.refresh(scenario)
            return scenario

    def get_scenario(self, name: str, version: str = "1.0") -> ScenarioDefinition | None:
        """Get a scenario definition by name and version.

        Args:
            name: Scenario name.
            version: Scenario version.

        Returns:
            ScenarioDefinition or None if not found.
        """
        with self.get_session() as session:
            return (
                session.query(ScenarioDefinition)
                .filter_by(name=name, version=version)
                .first()
            )

    def list_scenarios(self) -> list[ScenarioDefinition]:
        """List all scenario definitions.

        Returns:
            List of ScenarioDefinition instances.
        """
        with self.get_session() as session:
            return session.query(ScenarioDefinition).order_by(ScenarioDefinition.name).all()
