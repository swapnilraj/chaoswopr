"""Prometheus metrics export to PostgreSQL for chaoswopr.

Sets up remote-write from Prometheus to PostgreSQL for long-term
metric storage and post-experiment analysis.

Uses a pull-based approach: queries Prometheus periodically and
stores results in PostgreSQL via the storage layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ExportConfig:
    """Configuration for metrics export.

    Attributes:
        export_interval_seconds: How often to export metrics.
        batch_size: Number of metrics to export per batch.
        metrics_to_export: List of metric names to export (empty = all).
        retention_days: How long to keep exported metrics in PostgreSQL.
    """

    export_interval_seconds: int = 30
    batch_size: int = 100
    metrics_to_export: list[str] = field(default_factory=list)
    retention_days: int = 30

    def validate(self) -> list[str]:
        """Validate configuration."""
        errors: list[str] = []
        if self.export_interval_seconds < 5:
            errors.append("export_interval_seconds must be >= 5")
        if self.batch_size < 1:
            errors.append("batch_size must be >= 1")
        if self.retention_days < 1:
            errors.append("retention_days must be >= 1")
        return errors


@dataclass
class ExportedMetric:
    """A single exported metric data point."""

    experiment_id: str
    metric_name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)
    phase: str | None = None

    def to_storage_dict(self) -> dict[str, Any]:
        """Convert to storage layer format."""
        return {
            "experiment_id": self.experiment_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "timestamp": self.timestamp,
            "labels": self.labels,
            "phase": self.phase,
        }


class MetricsExporter:
    """Exports metrics from Prometheus to PostgreSQL.

    Periodically queries Prometheus for configured metrics and
    stores them in PostgreSQL via the storage layer. This enables
    long-term metric retention and post-experiment analysis.
    """

    def __init__(
        self,
        prometheus_client: Any | None = None,
        storage: Any | None = None,
        config: ExportConfig | None = None,
    ) -> None:
        """Initialize the metrics exporter.

        Args:
            prometheus_client: Prometheus query client.
            storage: PostgreSQL storage client.
            config: Export configuration.
        """
        self._prometheus = prometheus_client
        self._storage = storage
        self._config = config or ExportConfig()
        self._export_count = 0
        self._last_export: datetime | None = None
        self._errors: list[str] = []

    @property
    def config(self) -> ExportConfig:
        """Get the export configuration."""
        return self._config

    @property
    def export_count(self) -> int:
        """Get total number of metrics exported."""
        return self._export_count

    @property
    def last_export(self) -> datetime | None:
        """Get timestamp of last export."""
        return self._last_export

    def export_metrics(
        self,
        experiment_id: str,
        metric_names: list[str] | None = None,
        phase: str | None = None,
    ) -> int:
        """Export current metrics from Prometheus to PostgreSQL.

        Args:
            experiment_id: Current experiment ID.
            metric_names: Specific metrics to export (None = use config).
            phase: Current experiment phase (baseline, chaos, recovery).

        Returns:
            Number of metrics exported.
        """
        names = metric_names or self._config.metrics_to_export

        if not self._prometheus or not self._storage:
            return 0

        exported = 0
        batch: list[dict[str, Any]] = []

        for name in names:
            try:
                result = self._prometheus.query(name)
                if result.success and result.data:
                    for data_point in result.data:
                        metric = ExportedMetric(
                            experiment_id=experiment_id,
                            metric_name=name,
                            value=float(data_point.get("value", [0, 0])[1]),
                            timestamp=datetime.now(timezone.utc),
                            labels=data_point.get("metric", {}),
                            phase=phase,
                        )
                        batch.append(metric.to_storage_dict())

                        if len(batch) >= self._config.batch_size:
                            self._storage.store_metrics_batch(batch)
                            exported += len(batch)
                            batch = []
            except Exception as e:
                self._errors.append(f"Failed to export {name}: {e}")

        # Flush remaining batch
        if batch:
            try:
                self._storage.store_metrics_batch(batch)
                exported += len(batch)
            except Exception as e:
                self._errors.append(f"Failed to flush batch: {e}")

        self._export_count += exported
        self._last_export = datetime.now(timezone.utc)
        return exported

    def get_status(self) -> dict[str, Any]:
        """Get exporter status."""
        return {
            "export_count": self._export_count,
            "last_export": self._last_export.isoformat() if self._last_export else None,
            "config": {
                "export_interval_seconds": self._config.export_interval_seconds,
                "batch_size": self._config.batch_size,
                "metrics_count": len(self._config.metrics_to_export),
            },
            "errors": self._errors[-10:],  # Last 10 errors
        }
