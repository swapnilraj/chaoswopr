"""Unit tests for metrics export to PostgreSQL."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chaoswopr.infrastructure.monitoring.metrics_export import (
    ExportConfig,
    ExportedMetric,
    MetricsExporter,
)


class TestExportConfig:
    """Tests for ExportConfig."""

    def test_default_config(self) -> None:
        config = ExportConfig()
        assert config.export_interval_seconds == 30
        assert config.batch_size == 100

    def test_validate_valid(self) -> None:
        config = ExportConfig()
        assert config.validate() == []

    def test_validate_low_interval(self) -> None:
        config = ExportConfig(export_interval_seconds=1)
        errors = config.validate()
        assert any("export_interval" in e for e in errors)

    def test_validate_zero_batch(self) -> None:
        config = ExportConfig(batch_size=0)
        errors = config.validate()
        assert any("batch_size" in e for e in errors)


class TestExportedMetric:
    """Tests for ExportedMetric."""

    def test_to_storage_dict(self) -> None:
        from datetime import datetime, timezone

        metric = ExportedMetric(
            experiment_id="exp-001",
            metric_name="finality_delay",
            value=13.2,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            phase="baseline",
        )
        d = metric.to_storage_dict()
        assert d["experiment_id"] == "exp-001"
        assert d["metric_name"] == "finality_delay"
        assert d["value"] == 13.2
        assert d["phase"] == "baseline"


class TestMetricsExporter:
    """Tests for MetricsExporter."""

    def test_create_exporter(self) -> None:
        exporter = MetricsExporter()
        assert exporter.export_count == 0
        assert exporter.last_export is None

    def test_export_no_clients(self) -> None:
        exporter = MetricsExporter()
        count = exporter.export_metrics("exp-001", metric_names=["test"])
        assert count == 0

    def test_export_with_mocks(self) -> None:
        prom = MagicMock()
        storage = MagicMock()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = [{"value": [1234567890, "42.0"], "metric": {"instance": "node-1"}}]
        prom.query.return_value = mock_result

        exporter = MetricsExporter(
            prometheus_client=prom,
            storage=storage,
            config=ExportConfig(metrics_to_export=["test_metric"]),
        )
        count = exporter.export_metrics("exp-001", phase="baseline")
        assert count > 0
        assert storage.store_metrics_batch.called

    def test_export_count_tracks(self) -> None:
        prom = MagicMock()
        storage = MagicMock()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = [{"value": [0, "1.0"], "metric": {}}]
        prom.query.return_value = mock_result

        exporter = MetricsExporter(
            prometheus_client=prom,
            storage=storage,
            config=ExportConfig(metrics_to_export=["m1", "m2"]),
        )
        exporter.export_metrics("exp-001")
        assert exporter.export_count == 2
        assert exporter.last_export is not None

    def test_get_status(self) -> None:
        exporter = MetricsExporter()
        status = exporter.get_status()
        assert status["export_count"] == 0
        assert "config" in status
        assert "errors" in status

    def test_export_handles_errors(self) -> None:
        prom = MagicMock()
        storage = MagicMock()
        prom.query.side_effect = RuntimeError("connection failed")

        exporter = MetricsExporter(
            prometheus_client=prom,
            storage=storage,
            config=ExportConfig(metrics_to_export=["bad_metric"]),
        )
        count = exporter.export_metrics("exp-001")
        assert count == 0
