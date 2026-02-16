"""Database models for chaoswopr storage layer.

Defines SQLAlchemy models for:
- ExperimentRun: experiment execution records
- MetricSnapshot: time-series metric snapshots
- ScenarioDefinition: stored scenario configurations
- AuditLogEntry: audit trail records (also stored in S3)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class ExperimentStatus(str, Enum):
    """Status of an experiment run."""

    PENDING = "pending"
    PREFLIGHT = "preflight"
    RUNNING = "running"
    RECOVERING = "recovering"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class ExperimentRun(Base):
    """Record of a single experiment execution."""

    __tablename__ = "experiment_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_name = Column(String(100), nullable=False, index=True)
    scenario_version = Column(String(10), nullable=False, default="1.0")
    status = Column(String(20), nullable=False, default=ExperimentStatus.PENDING.value)
    hypothesis = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    config = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    # Experiment metadata
    node_count = Column(Integer, nullable=True)
    blast_radius_percent = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_experiment_status", "status"),
        Index("idx_experiment_created", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "scenario_name": self.scenario_name,
            "scenario_version": self.scenario_version,
            "status": self.status,
            "hypothesis": self.hypothesis,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "config": self.config,
            "results": self.results,
            "error_message": self.error_message,
            "node_count": self.node_count,
            "blast_radius_percent": self.blast_radius_percent,
            "duration_seconds": self.duration_seconds,
        }


class MetricSnapshot(Base):
    """Time-series metric snapshot from an experiment."""

    __tablename__ = "metric_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(String(36), nullable=False, index=True)
    metric_name = Column(String(200), nullable=False, index=True)
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    labels = Column(JSON, nullable=True)
    phase = Column(String(20), nullable=True)  # baseline, chaos, recovery

    __table_args__ = (
        Index("idx_metric_experiment_name", "experiment_id", "metric_name"),
        Index("idx_metric_timestamp", "timestamp"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "experiment_id": self.experiment_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "labels": self.labels,
            "phase": self.phase,
        }


class ScenarioDefinition(Base):
    """Stored scenario configuration."""

    __tablename__ = "scenario_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    version = Column(String(10), nullable=False, default="1.0")
    description = Column(Text, nullable=True)
    hypothesis = Column(Text, nullable=False)
    config = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_scenario_name_version"),
        Index("idx_scenario_name", "name"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "hypothesis": self.hypothesis,
            "config": self.config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AuditLogEntry(Base):
    """Audit trail record for all agent actions.

    Note: These are also written to S3 for tamper-evident storage.
    The database copy is for querying; the S3 copy is the audit source of truth.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    agent_id = Column(String(100), nullable=False, index=True)
    action_type = Column(String(100), nullable=False, index=True)
    target = Column(String(200), nullable=False)
    parameters = Column(JSON, nullable=True)
    outcome = Column(String(50), nullable=False)
    trace_id = Column(String(36), nullable=False, index=True)
    experiment_id = Column(String(36), nullable=True, index=True)
    s3_key = Column(String(500), nullable=True)

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_experiment", "experiment_id"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "agent_id": self.agent_id,
            "action_type": self.action_type,
            "target": self.target,
            "parameters": self.parameters,
            "outcome": self.outcome,
            "trace_id": self.trace_id,
            "experiment_id": self.experiment_id,
            "s3_key": self.s3_key,
        }
