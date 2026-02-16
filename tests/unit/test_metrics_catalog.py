"""Unit tests for the core metrics catalog."""

from __future__ import annotations

import pytest

from chaoswopr.infrastructure.monitoring.metrics_catalog import (
    METRICS_CATALOG,
    MetricCategory,
    MetricDefinition,
    MetricSource,
    MetricsCatalog,
)


class TestMetricDefinition:
    """Tests for MetricDefinition."""

    def test_create_metric(self) -> None:
        metric = MetricDefinition(
            name="test_metric",
            description="A test metric",
            category=MetricCategory.CONSENSUS,
            source=MetricSource.BEACON_API,
            promql='test_metric{job="test"}',
            unit="count",
        )
        assert metric.name == "test_metric"
        assert metric.critical is False

    def test_critical_metric(self) -> None:
        metric = MetricDefinition(
            name="critical_test",
            description="A critical metric",
            category=MetricCategory.SAFETY,
            source=MetricSource.BEACON_API,
            promql="test",
            critical=True,
            alert_threshold=5.0,
        )
        assert metric.critical is True
        assert metric.alert_threshold == 5.0

    def test_to_dict(self) -> None:
        metric = MetricDefinition(
            name="test",
            description="test",
            category=MetricCategory.CONSENSUS,
            source=MetricSource.BEACON_API,
            promql="test",
        )
        d = metric.to_dict()
        assert d["name"] == "test"
        assert d["category"] == "consensus"
        assert d["source"] == "beacon_api"


class TestMetricsCatalog:
    """Tests for the MetricsCatalog."""

    @pytest.fixture
    def catalog(self) -> MetricsCatalog:
        return MetricsCatalog()

    def test_default_catalog_count(self, catalog: MetricsCatalog) -> None:
        """The default catalog must have >= 50 metrics as per spec."""
        assert catalog.count >= 50

    def test_catalog_validates(self, catalog: MetricsCatalog) -> None:
        """The default catalog must pass validation."""
        errors = catalog.validate()
        assert errors == [], f"Catalog validation errors: {errors}"

    def test_no_duplicate_names(self, catalog: MetricsCatalog) -> None:
        """All metric names must be unique."""
        names = [m.name for m in catalog.metrics]
        assert len(names) == len(set(names))

    def test_has_consensus_metrics(self, catalog: MetricsCatalog) -> None:
        consensus = catalog.get_by_category(MetricCategory.CONSENSUS)
        assert len(consensus) >= 5

    def test_has_network_metrics(self, catalog: MetricsCatalog) -> None:
        network = catalog.get_by_category(MetricCategory.NETWORK)
        assert len(network) >= 5

    def test_has_resource_metrics(self, catalog: MetricsCatalog) -> None:
        resource = catalog.get_by_category(MetricCategory.RESOURCE)
        assert len(resource) >= 5

    def test_has_safety_metrics(self, catalog: MetricsCatalog) -> None:
        safety = catalog.get_by_category(MetricCategory.SAFETY)
        assert len(safety) >= 2

    def test_has_critical_metrics(self, catalog: MetricsCatalog) -> None:
        """There must be critical metrics for circuit breaker integration."""
        critical = catalog.get_critical_metrics()
        assert len(critical) >= 3

    def test_has_alert_metrics(self, catalog: MetricsCatalog) -> None:
        """There must be metrics with alert thresholds."""
        alerts = catalog.get_alert_metrics()
        assert len(alerts) >= 3

    def test_get_by_name(self, catalog: MetricsCatalog) -> None:
        metric = catalog.get_by_name("beacon_finality_delay_epochs")
        assert metric is not None
        assert metric.critical is True

    def test_get_by_name_nonexistent(self, catalog: MetricsCatalog) -> None:
        metric = catalog.get_by_name("nonexistent_metric")
        assert metric is None

    def test_get_by_source(self, catalog: MetricsCatalog) -> None:
        beacon_metrics = catalog.get_by_source(MetricSource.BEACON_API)
        assert len(beacon_metrics) > 0

    def test_finality_metric_exists(self, catalog: MetricsCatalog) -> None:
        """Finality delay metric must exist and be critical."""
        metric = catalog.get_by_name("beacon_finality_delay_epochs")
        assert metric is not None
        assert metric.critical is True
        assert metric.category == MetricCategory.CONSENSUS

    def test_participation_metric_exists(self, catalog: MetricsCatalog) -> None:
        """Participation rate metric must exist and be critical."""
        metric = catalog.get_by_name("beacon_participation_rate")
        assert metric is not None
        assert metric.critical is True

    def test_slashing_metric_exists(self, catalog: MetricsCatalog) -> None:
        """Slashing rate metric must exist and be critical."""
        metric = catalog.get_by_name("beacon_slashing_rate")
        assert metric is not None
        assert metric.critical is True

    def test_peer_count_metric_exists(self, catalog: MetricsCatalog) -> None:
        metric = catalog.get_by_name("p2p_peer_count")
        assert metric is not None

    def test_mempool_metric_exists(self, catalog: MetricsCatalog) -> None:
        metric = catalog.get_by_name("el_mempool_depth")
        assert metric is not None

    def test_cpu_metric_exists(self, catalog: MetricsCatalog) -> None:
        metric = catalog.get_by_name("node_cpu_usage")
        assert metric is not None

    def test_memory_metric_exists(self, catalog: MetricsCatalog) -> None:
        metric = catalog.get_by_name("node_memory_usage")
        assert metric is not None

    def test_to_dict(self, catalog: MetricsCatalog) -> None:
        data = catalog.to_dict()
        assert isinstance(data, list)
        assert len(data) >= 50

    def test_custom_catalog(self) -> None:
        custom_metrics = [
            MetricDefinition(
                name="custom1",
                description="test",
                category=MetricCategory.CUSTOM,
                source=MetricSource.CUSTOM_EXPORTER,
                promql="custom1",
            )
        ]
        catalog = MetricsCatalog(metrics=custom_metrics)
        assert catalog.count == 1

    def test_validate_insufficient_metrics(self) -> None:
        catalog = MetricsCatalog(metrics=[])
        errors = catalog.validate()
        assert any("50" in e for e in errors)
