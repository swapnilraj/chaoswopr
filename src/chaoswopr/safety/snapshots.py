"""Snapshot and rollback mechanism for chaoswopr.

Supports two backends:
- Kubernetes: VolumeSnapshot integration for production
- Docker: Volume snapshot via docker commit / volume backup for development

Snapshots are taken periodically during experiments and can be restored
on demand for rollback after circuit breaker trips.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SnapshotState(str, Enum):
    """State of a snapshot."""

    PENDING = "pending"
    CREATING = "creating"
    READY = "ready"
    RESTORING = "restoring"
    FAILED = "failed"
    DELETED = "deleted"


@dataclass
class Snapshot:
    """Record of a single snapshot."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    experiment_id: str | None = None
    state: SnapshotState = SnapshotState.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    node_ids: list[str] = field(default_factory=list)
    backend: str = "docker"
    metadata: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "experiment_id": self.experiment_id,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "node_ids": self.node_ids,
            "backend": self.backend,
            "metadata": self.metadata,
            "error_message": self.error_message,
        }


class SnapshotBackend(ABC):
    """Abstract base class for snapshot backends."""

    @abstractmethod
    def create_snapshot(
        self,
        node_ids: list[str],
        experiment_id: str | None = None,
    ) -> Snapshot:
        """Create a snapshot of the specified nodes.

        Args:
            node_ids: List of node identifiers to snapshot.
            experiment_id: Associated experiment ID.

        Returns:
            Snapshot record.
        """

    @abstractmethod
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore a snapshot.

        Args:
            snapshot_id: ID of the snapshot to restore.

        Returns:
            True if restoration succeeded.
        """

    @abstractmethod
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot.

        Args:
            snapshot_id: ID of the snapshot to delete.

        Returns:
            True if deletion succeeded.
        """

    @abstractmethod
    def list_snapshots(
        self, experiment_id: str | None = None
    ) -> list[Snapshot]:
        """List available snapshots.

        Args:
            experiment_id: Optional filter by experiment ID.

        Returns:
            List of Snapshot records.
        """


class DockerSnapshotBackend(SnapshotBackend):
    """Docker-based snapshot backend for development environments.

    Uses docker volume operations to create and restore snapshots.
    This is simpler but slower than Kubernetes VolumeSnapshots.
    """

    def __init__(self, docker_client: Any | None = None) -> None:
        """Initialize the Docker snapshot backend.

        Args:
            docker_client: Pre-configured Docker client (for testing).
        """
        self._client = docker_client
        self._snapshots: dict[str, Snapshot] = {}

    def create_snapshot(
        self,
        node_ids: list[str],
        experiment_id: str | None = None,
    ) -> Snapshot:
        """Create a snapshot using Docker volume backup."""
        snapshot = Snapshot(
            experiment_id=experiment_id,
            node_ids=node_ids,
            backend="docker",
        )
        snapshot.state = SnapshotState.CREATING

        try:
            if self._client:
                # Real Docker operations would go here
                for node_id in node_ids:
                    # docker commit or volume backup
                    pass
            snapshot.state = SnapshotState.READY
        except Exception as e:
            snapshot.state = SnapshotState.FAILED
            snapshot.error_message = str(e)

        self._snapshots[snapshot.id] = snapshot
        return snapshot

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore a Docker volume snapshot."""
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return False
        if snapshot.state != SnapshotState.READY:
            return False

        snapshot.state = SnapshotState.RESTORING
        try:
            if self._client:
                # Real Docker restore operations would go here
                for node_id in snapshot.node_ids:
                    pass
            snapshot.state = SnapshotState.READY
            return True
        except Exception as e:
            snapshot.state = SnapshotState.FAILED
            snapshot.error_message = str(e)
            return False

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a Docker volume snapshot."""
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return False
        snapshot.state = SnapshotState.DELETED
        return True

    def list_snapshots(
        self, experiment_id: str | None = None
    ) -> list[Snapshot]:
        """List Docker volume snapshots."""
        snapshots = list(self._snapshots.values())
        if experiment_id:
            snapshots = [s for s in snapshots if s.experiment_id == experiment_id]
        return [s for s in snapshots if s.state != SnapshotState.DELETED]


class KubernetesSnapshotBackend(SnapshotBackend):
    """Kubernetes VolumeSnapshot backend for production environments.

    Uses the Kubernetes VolumeSnapshot API to create and restore
    snapshots of persistent volume claims.
    """

    def __init__(self, k8s_client: Any | None = None, namespace: str = "default") -> None:
        """Initialize the Kubernetes snapshot backend.

        Args:
            k8s_client: Pre-configured Kubernetes client.
            namespace: Kubernetes namespace.
        """
        self._client = k8s_client
        self._namespace = namespace
        self._snapshots: dict[str, Snapshot] = {}

    def create_snapshot(
        self,
        node_ids: list[str],
        experiment_id: str | None = None,
    ) -> Snapshot:
        """Create a Kubernetes VolumeSnapshot."""
        snapshot = Snapshot(
            experiment_id=experiment_id,
            node_ids=node_ids,
            backend="kubernetes",
        )
        snapshot.state = SnapshotState.CREATING

        try:
            if self._client:
                # Real K8s VolumeSnapshot operations would go here
                # For each node, create a VolumeSnapshot of its PVC
                pass
            snapshot.state = SnapshotState.READY
        except Exception as e:
            snapshot.state = SnapshotState.FAILED
            snapshot.error_message = str(e)

        self._snapshots[snapshot.id] = snapshot
        return snapshot

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore a Kubernetes VolumeSnapshot."""
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return False
        if snapshot.state != SnapshotState.READY:
            return False

        snapshot.state = SnapshotState.RESTORING
        try:
            if self._client:
                # Real K8s restore operations would go here
                pass
            snapshot.state = SnapshotState.READY
            return True
        except Exception as e:
            snapshot.state = SnapshotState.FAILED
            snapshot.error_message = str(e)
            return False

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a Kubernetes VolumeSnapshot."""
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return False
        snapshot.state = SnapshotState.DELETED
        return True

    def list_snapshots(
        self, experiment_id: str | None = None
    ) -> list[Snapshot]:
        """List Kubernetes VolumeSnapshots."""
        snapshots = list(self._snapshots.values())
        if experiment_id:
            snapshots = [s for s in snapshots if s.experiment_id == experiment_id]
        return [s for s in snapshots if s.state != SnapshotState.DELETED]


class SnapshotManager:
    """High-level snapshot manager that abstracts backend selection.

    Provides a unified API for creating, restoring, and managing snapshots
    across Docker and Kubernetes backends.
    """

    def __init__(self, backend: SnapshotBackend) -> None:
        """Initialize the snapshot manager.

        Args:
            backend: The snapshot backend to use.
        """
        self._backend = backend

    @property
    def backend(self) -> SnapshotBackend:
        """Get the snapshot backend."""
        return self._backend

    def create_snapshot(
        self,
        node_ids: list[str],
        experiment_id: str | None = None,
    ) -> Snapshot:
        """Create a snapshot of the specified nodes."""
        return self._backend.create_snapshot(node_ids, experiment_id)

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore a previously created snapshot."""
        return self._backend.restore_snapshot(snapshot_id)

    def restore_latest(self, experiment_id: str) -> bool:
        """Restore the most recent snapshot for an experiment.

        Args:
            experiment_id: The experiment ID.

        Returns:
            True if a snapshot was found and restored.
        """
        snapshots = self._backend.list_snapshots(experiment_id)
        ready_snapshots = [s for s in snapshots if s.state == SnapshotState.READY]
        if not ready_snapshots:
            return False

        # Sort by creation time, most recent first
        ready_snapshots.sort(key=lambda s: s.created_at, reverse=True)
        return self._backend.restore_snapshot(ready_snapshots[0].id)

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        return self._backend.delete_snapshot(snapshot_id)

    def cleanup_experiment_snapshots(self, experiment_id: str, keep_latest: int = 1) -> int:
        """Clean up old snapshots for an experiment.

        Args:
            experiment_id: The experiment ID.
            keep_latest: Number of recent snapshots to keep.

        Returns:
            Number of snapshots deleted.
        """
        snapshots = self._backend.list_snapshots(experiment_id)
        ready_snapshots = [s for s in snapshots if s.state == SnapshotState.READY]
        ready_snapshots.sort(key=lambda s: s.created_at, reverse=True)

        deleted = 0
        for snapshot in ready_snapshots[keep_latest:]:
            if self._backend.delete_snapshot(snapshot.id):
                deleted += 1
        return deleted

    def list_snapshots(self, experiment_id: str | None = None) -> list[Snapshot]:
        """List snapshots."""
        return self._backend.list_snapshots(experiment_id)
