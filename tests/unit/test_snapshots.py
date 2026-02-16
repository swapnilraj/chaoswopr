"""Unit tests for the snapshot/rollback mechanism."""

from __future__ import annotations

import pytest

from chaoswopr.safety.snapshots import (
    DockerSnapshotBackend,
    KubernetesSnapshotBackend,
    Snapshot,
    SnapshotManager,
    SnapshotState,
)


class TestSnapshot:
    """Tests for the Snapshot dataclass."""

    def test_default_snapshot(self) -> None:
        snapshot = Snapshot()
        assert snapshot.id is not None
        assert snapshot.state == SnapshotState.PENDING
        assert snapshot.backend == "docker"
        assert snapshot.node_ids == []

    def test_snapshot_to_dict(self) -> None:
        snapshot = Snapshot(experiment_id="exp-001", node_ids=["node-1", "node-2"])
        d = snapshot.to_dict()
        assert d["experiment_id"] == "exp-001"
        assert len(d["node_ids"]) == 2
        assert d["state"] == "pending"


class TestDockerSnapshotBackend:
    """Tests for DockerSnapshotBackend."""

    @pytest.fixture
    def backend(self) -> DockerSnapshotBackend:
        return DockerSnapshotBackend()

    def test_create_snapshot(self, backend: DockerSnapshotBackend) -> None:
        snapshot = backend.create_snapshot(
            node_ids=["node-1", "node-2"],
            experiment_id="exp-001",
        )
        assert snapshot.state == SnapshotState.READY
        assert snapshot.experiment_id == "exp-001"
        assert len(snapshot.node_ids) == 2

    def test_restore_snapshot(self, backend: DockerSnapshotBackend) -> None:
        snapshot = backend.create_snapshot(["node-1"])
        result = backend.restore_snapshot(snapshot.id)
        assert result is True

    def test_restore_nonexistent_snapshot(self, backend: DockerSnapshotBackend) -> None:
        result = backend.restore_snapshot("nonexistent-id")
        assert result is False

    def test_delete_snapshot(self, backend: DockerSnapshotBackend) -> None:
        snapshot = backend.create_snapshot(["node-1"])
        result = backend.delete_snapshot(snapshot.id)
        assert result is True
        # Should not appear in list
        assert len(backend.list_snapshots()) == 0

    def test_delete_nonexistent_snapshot(self, backend: DockerSnapshotBackend) -> None:
        result = backend.delete_snapshot("nonexistent-id")
        assert result is False

    def test_list_snapshots(self, backend: DockerSnapshotBackend) -> None:
        backend.create_snapshot(["node-1"], experiment_id="exp-001")
        backend.create_snapshot(["node-2"], experiment_id="exp-001")
        backend.create_snapshot(["node-3"], experiment_id="exp-002")

        all_snapshots = backend.list_snapshots()
        assert len(all_snapshots) == 3

        exp1_snapshots = backend.list_snapshots(experiment_id="exp-001")
        assert len(exp1_snapshots) == 2

    def test_list_excludes_deleted(self, backend: DockerSnapshotBackend) -> None:
        s1 = backend.create_snapshot(["node-1"])
        backend.create_snapshot(["node-2"])
        backend.delete_snapshot(s1.id)
        assert len(backend.list_snapshots()) == 1


class TestKubernetesSnapshotBackend:
    """Tests for KubernetesSnapshotBackend."""

    @pytest.fixture
    def backend(self) -> KubernetesSnapshotBackend:
        return KubernetesSnapshotBackend()

    def test_create_snapshot(self, backend: KubernetesSnapshotBackend) -> None:
        snapshot = backend.create_snapshot(
            node_ids=["node-1"],
            experiment_id="exp-001",
        )
        assert snapshot.state == SnapshotState.READY
        assert snapshot.backend == "kubernetes"

    def test_restore_snapshot(self, backend: KubernetesSnapshotBackend) -> None:
        snapshot = backend.create_snapshot(["node-1"])
        result = backend.restore_snapshot(snapshot.id)
        assert result is True

    def test_list_snapshots(self, backend: KubernetesSnapshotBackend) -> None:
        backend.create_snapshot(["node-1"])
        backend.create_snapshot(["node-2"])
        assert len(backend.list_snapshots()) == 2


class TestSnapshotManager:
    """Tests for the SnapshotManager high-level API."""

    @pytest.fixture
    def manager(self) -> SnapshotManager:
        backend = DockerSnapshotBackend()
        return SnapshotManager(backend=backend)

    def test_create_and_restore(self, manager: SnapshotManager) -> None:
        snapshot = manager.create_snapshot(["node-1", "node-2"], experiment_id="exp-001")
        assert snapshot.state == SnapshotState.READY
        result = manager.restore_snapshot(snapshot.id)
        assert result is True

    def test_restore_latest(self, manager: SnapshotManager) -> None:
        import time

        manager.create_snapshot(["node-1"], experiment_id="exp-001")
        # Second snapshot is "latest"
        manager.create_snapshot(["node-1", "node-2"], experiment_id="exp-001")

        result = manager.restore_latest("exp-001")
        assert result is True

    def test_restore_latest_no_snapshots(self, manager: SnapshotManager) -> None:
        result = manager.restore_latest("nonexistent-exp")
        assert result is False

    def test_cleanup_experiment_snapshots(self, manager: SnapshotManager) -> None:
        for i in range(5):
            manager.create_snapshot([f"node-{i}"], experiment_id="exp-001")

        deleted = manager.cleanup_experiment_snapshots("exp-001", keep_latest=2)
        assert deleted == 3
        remaining = manager.list_snapshots("exp-001")
        assert len(remaining) == 2

    def test_cleanup_keeps_all_if_fewer(self, manager: SnapshotManager) -> None:
        manager.create_snapshot(["node-1"], experiment_id="exp-001")
        deleted = manager.cleanup_experiment_snapshots("exp-001", keep_latest=5)
        assert deleted == 0
        assert len(manager.list_snapshots("exp-001")) == 1

    def test_list_snapshots(self, manager: SnapshotManager) -> None:
        manager.create_snapshot(["node-1"])
        manager.create_snapshot(["node-2"])
        assert len(manager.list_snapshots()) == 2
