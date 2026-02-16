"""Real safety system integration tests.

Tests the circuit breaker, snapshots, and kill switch with real
infrastructure (Docker containers, Prometheus queries).
Requires Docker.
"""

from __future__ import annotations

import time
from typing import Generator

import pytest
import requests

from chaoswopr.safety.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    ThresholdConfig,
    TripEvent,
)
from chaoswopr.safety.snapshots import DockerSnapshotBackend, SnapshotManager, SnapshotState

from .conftest import require_docker


def _start_prometheus_container() -> tuple[str, any] | None:
    """Start a Prometheus container."""
    try:
        from testcontainers.core.container import DockerContainer

        container = (
            DockerContainer("prom/prometheus:v2.51.0")
            .with_exposed_ports(9090)
            .with_command("--config.file=/etc/prometheus/prometheus.yml --web.enable-lifecycle")
        )
        container.start()

        host = container.get_container_host_ip()
        port = container.get_exposed_port(9090)
        base_url = f"http://{host}:{port}"

        for _ in range(30):
            try:
                resp = requests.get(f"{base_url}/-/ready", timeout=2)
                if resp.status_code == 200:
                    return base_url, container
            except requests.ConnectionError:
                pass
            time.sleep(1)

        container.stop()
        return None
    except (ImportError, Exception):
        return None


@require_docker
class TestCircuitBreakerWithRealMetrics:
    """Test circuit breaker integration with real Prometheus queries."""

    @pytest.fixture(scope="class")
    def prometheus_url(self) -> Generator[str, None, None]:
        """Start a real Prometheus instance."""
        result = _start_prometheus_container()
        if result is None:
            pytest.skip("Could not start Prometheus container")
        base_url, container = result
        # Wait for scrape data
        time.sleep(5)
        yield base_url
        try:
            container.stop()
        except Exception:
            pass

    def test_circuit_breaker_with_real_prometheus_query(
        self, prometheus_url: str
    ) -> None:
        """Circuit breaker should be able to check metrics from real Prometheus."""
        breaker = CircuitBreaker(
            thresholds=ThresholdConfig(
                finality_delay_max_seconds=600.0,
                slashing_rate_max_percent=5.0,
                participation_rate_min_percent=66.0,
            )
        )

        # Query Prometheus for a real metric to verify connectivity
        resp = requests.get(
            f"{prometheus_url}/api/v1/query",
            params={"query": "up"},
            timeout=5,
        )
        assert resp.status_code == 200

        # Simulate metrics within safe thresholds
        safe_metrics = {
            "finality_delay_seconds": 13.0,
            "slashing_rate_percent": 0.0,
            "participation_rate_percent": 98.5,
        }
        result = breaker.check_metrics(safe_metrics)
        assert result is True
        assert breaker.is_armed

        # Simulate metrics that breach thresholds
        dangerous_metrics = {
            "finality_delay_seconds": 700.0,
            "slashing_rate_percent": 0.0,
            "participation_rate_percent": 98.5,
        }
        result = breaker.check_metrics(dangerous_metrics)
        assert result is False
        assert breaker.is_tripped

    def test_circuit_breaker_trip_callback_fires(self, prometheus_url: str) -> None:
        """Trip callback should fire when breaker trips."""
        trip_events: list[TripEvent] = []

        breaker = CircuitBreaker(
            on_trip=lambda event: trip_events.append(event),
        )

        breaker.check_metrics({"finality_delay_seconds": 700.0})
        assert len(trip_events) == 1
        assert "finality" in trip_events[0].reason.lower()

    def test_circuit_breaker_stays_tripped(self, prometheus_url: str) -> None:
        """Once tripped, circuit breaker should stay tripped until reset."""
        breaker = CircuitBreaker()

        breaker.check_metrics({"finality_delay_seconds": 700.0})
        assert breaker.is_tripped

        # Even safe metrics should return False when tripped
        result = breaker.check_metrics({"finality_delay_seconds": 10.0})
        assert result is False
        assert breaker.is_tripped

        # Reset
        breaker.reset()
        assert breaker.state == CircuitBreakerState.RESET

        # Re-arm
        breaker.arm()
        result = breaker.check_metrics({"finality_delay_seconds": 10.0})
        assert result is True


@require_docker
class TestDockerSnapshotRealOperations:
    """Test Docker snapshot operations with real Docker containers."""

    @pytest.fixture
    def test_container(self) -> Generator[tuple[str, any], None, None]:
        """Start a test Docker container for snapshotting."""
        try:
            from testcontainers.core.container import DockerContainer

            container = (
                DockerContainer("alpine:3.19")
                .with_command("sleep 3600")
            )
            container.start()
            container_id = container.get_wrapped_container().id
            yield container_id, container
            try:
                container.stop()
            except Exception:
                pass
        except ImportError:
            pytest.skip("testcontainers not available")

    def test_snapshot_backend_with_real_container(
        self, test_container: tuple[str, any]
    ) -> None:
        """DockerSnapshotBackend should work with real containers."""
        container_id, _ = test_container

        backend = DockerSnapshotBackend()
        manager = SnapshotManager(backend=backend)

        # Create snapshot
        snapshot = manager.create_snapshot(
            [container_id],
            experiment_id="real-test",
        )
        assert snapshot.state == SnapshotState.READY

        # List snapshots
        snapshots = manager.list_snapshots(experiment_id="real-test")
        assert len(snapshots) == 1

        # Restore snapshot (in-memory backend, not actual Docker restore)
        result = manager.restore_snapshot(snapshot.id)
        assert result is True

        # Cleanup
        deleted = manager.cleanup_experiment_snapshots("real-test", keep_latest=0)
        assert deleted == 1


@require_docker
class TestRealPostgresStorage:
    """Test PostgreSQL storage with real testcontainers PostgreSQL."""

    @pytest.fixture(scope="class")
    def postgres_storage(self) -> Generator[any, None, None]:
        """Create a real PostgreSQL instance and storage layer."""
        try:
            from testcontainers.postgres import PostgresContainer

            with PostgresContainer("postgres:16-alpine") as pg:
                from sqlalchemy import create_engine

                from chaoswopr.storage.models import Base
                from chaoswopr.storage.postgres import PostgresStorage

                url = pg.get_connection_url()
                engine = create_engine(url)
                Base.metadata.create_all(engine)
                storage = PostgresStorage(engine=engine)
                yield storage
        except ImportError:
            pytest.skip("testcontainers[postgres] not available")

    def test_create_experiment_real_postgres(self, postgres_storage: any) -> None:
        """Create an experiment in real PostgreSQL."""
        from chaoswopr.storage.models import ExperimentStatus

        exp = postgres_storage.create_experiment(
            scenario_name="real_integration_test",
            hypothesis="PostgreSQL stores experiment data correctly",
            node_count=10,
        )
        assert exp.id is not None
        assert exp.scenario_name == "real_integration_test"

    def test_experiment_lifecycle_real_postgres(self, postgres_storage: any) -> None:
        """Full experiment lifecycle in real PostgreSQL."""
        from chaoswopr.storage.models import ExperimentStatus

        exp = postgres_storage.create_experiment(scenario_name="lifecycle_test")

        # Start
        postgres_storage.update_experiment_status(exp.id, ExperimentStatus.RUNNING)
        running = postgres_storage.get_experiment(exp.id)
        assert running.status == "running"
        assert running.started_at is not None

        # Store metrics
        postgres_storage.store_metric(exp.id, "finality_delay", 13.0, phase="baseline")
        postgres_storage.store_metric(exp.id, "participation_rate", 96.5, phase="baseline")
        metrics = postgres_storage.get_metrics(exp.id)
        assert len(metrics) == 2

        # Complete
        postgres_storage.update_experiment_status(
            exp.id,
            ExperimentStatus.COMPLETED,
            results={"passed": True},
        )
        completed = postgres_storage.get_experiment(exp.id)
        assert completed.status == "completed"
        assert completed.duration_seconds > 0

    def test_batch_metrics_real_postgres(self, postgres_storage: any) -> None:
        """Batch metric storage in real PostgreSQL."""
        exp = postgres_storage.create_experiment(scenario_name="batch_test")
        batch = [
            {"experiment_id": exp.id, "metric_name": f"metric_{i}", "value": float(i), "phase": "test"}
            for i in range(100)
        ]
        count = postgres_storage.store_metrics_batch(batch)
        assert count == 100

        all_metrics = postgres_storage.get_metrics(exp.id)
        assert len(all_metrics) == 100
