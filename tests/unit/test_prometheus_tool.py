"""Unit tests for the Prometheus query tool.

Tests the PrometheusQueryTool's metric querying, pre-flight health checks,
baseline collection, statistical summaries, and comparison functionality.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chaoswopr.agents.prometheus_tool import (
    CONSENSUS_QUERIES,
    HealthCheckResult,
    MetricSample,
    MetricSummary,
    PrometheusQueryTool,
)
from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient, QueryResult


class TestMetricSample:
    """Tests for MetricSample data class."""

    def test_creation(self) -> None:
        """MetricSample should be created with values."""
        sample = MetricSample(metric_name="test_metric", value=42.0)
        assert sample.metric_name == "test_metric"
        assert sample.value == 42.0
        assert sample.timestamp is not None

    def test_to_dict(self) -> None:
        """MetricSample should serialize to dictionary."""
        sample = MetricSample(metric_name="test", value=1.0, labels={"job": "test"})
        d = sample.to_dict()
        assert d["metric_name"] == "test"
        assert d["value"] == 1.0
        assert d["labels"]["job"] == "test"


class TestMetricSummary:
    """Tests for MetricSummary data class."""

    def test_creation(self) -> None:
        """MetricSummary should be created with statistics."""
        summary = MetricSummary(
            metric_name="test",
            count=10,
            mean=50.0,
            min_val=40.0,
            max_val=60.0,
            std_dev=5.0,
            latest=55.0,
        )
        assert summary.count == 10
        assert summary.mean == 50.0

    def test_to_dict(self) -> None:
        """MetricSummary should serialize to dictionary."""
        summary = MetricSummary(metric_name="test", count=1, mean=10.0)
        d = summary.to_dict()
        assert d["metric_name"] == "test"
        assert d["count"] == 1
        assert d["mean"] == 10.0


class TestHealthCheckResult:
    """Tests for HealthCheckResult data class."""

    def test_healthy_result(self) -> None:
        """Healthy result should have healthy=True."""
        result = HealthCheckResult(healthy=True, summary="All checks passed")
        assert result.healthy is True

    def test_to_dict(self) -> None:
        """HealthCheckResult should serialize to dictionary."""
        result = HealthCheckResult(
            healthy=True,
            checks=[{"check": "test", "passed": True}],
            summary="OK",
            metrics={"test": 1.0},
        )
        d = result.to_dict()
        assert d["healthy"] is True
        assert len(d["checks"]) == 1
        assert d["metrics"]["test"] == 1.0


class TestPrometheusQueryTool:
    """Tests for the PrometheusQueryTool."""

    def _make_tool(self, dry_run: bool = True) -> PrometheusQueryTool:
        """Helper to create a tool instance."""
        prom = PrometheusClient(base_url="http://localhost:9090")
        return PrometheusQueryTool(prometheus_client=prom, dry_run=dry_run)

    def test_initialization(self) -> None:
        """Tool should initialize with default queries."""
        tool = self._make_tool()
        assert len(tool.available_metrics) > 0
        assert "finality_delay_seconds" in tool.available_metrics
        assert "participation_rate_percent" in tool.available_metrics

    def test_custom_queries(self) -> None:
        """Tool should accept custom queries."""
        prom = PrometheusClient(base_url="http://localhost:9090")
        tool = PrometheusQueryTool(
            prometheus_client=prom,
            custom_queries={"custom_metric": "custom_promql"},
            dry_run=True,
        )
        assert "custom_metric" in tool.available_metrics

    def test_query_metric_dry_run(self) -> None:
        """Dry-run query should return mock data."""
        tool = self._make_tool()
        sample = tool.query_metric("finality_delay_seconds")
        assert sample is not None
        assert sample.metric_name == "finality_delay_seconds"
        assert sample.value == 13.2  # Mock value

    def test_query_metric_returns_none_for_unknown_in_dry_run(self) -> None:
        """Unknown metric in dry-run should return sample with 0.0."""
        tool = self._make_tool()
        sample = tool.query_metric("unknown_metric")
        assert sample is not None
        assert sample.value == 0.0

    def test_query_multiple(self) -> None:
        """query_multiple should return values for all metrics."""
        tool = self._make_tool()
        results = tool.query_multiple([
            "finality_delay_seconds",
            "participation_rate_percent",
        ])
        assert "finality_delay_seconds" in results
        assert "participation_rate_percent" in results
        assert results["finality_delay_seconds"] == 13.2
        assert results["participation_rate_percent"] == 96.5

    def test_query_all(self) -> None:
        """query_all should return all registered metrics."""
        tool = self._make_tool()
        results = tool.query_all()
        assert len(results) >= len(CONSENSUS_QUERIES)

    def test_pre_flight_health_check_dry_run(self) -> None:
        """Pre-flight health check should pass in dry-run mode."""
        tool = self._make_tool()
        result = tool.pre_flight_health_check()

        assert result.healthy is True
        assert len(result.checks) == 3  # finality, participation, peer_count

    def test_pre_flight_health_check_with_thresholds(self) -> None:
        """Health check should respect custom thresholds."""
        tool = self._make_tool()
        result = tool.pre_flight_health_check(
            min_peer_count=100,  # Higher than mock value (48)
        )
        # Should fail because mock peer count (48) < 100
        assert result.healthy is False
        peer_check = [c for c in result.checks if c["check"] == "peer_count"][0]
        assert peer_check["passed"] is False

    def test_pre_flight_health_check_finality_threshold(self) -> None:
        """Health check should fail on high finality delay threshold."""
        tool = self._make_tool()
        result = tool.pre_flight_health_check(
            max_finality_delay=5.0,  # Lower than mock value (13.2)
        )
        assert result.healthy is False

    def test_collect_baseline(self) -> None:
        """collect_baseline should return MetricSummary for each metric."""
        tool = self._make_tool()
        baseline = tool.collect_baseline(
            metric_names=["finality_delay_seconds", "participation_rate_percent"]
        )
        assert "finality_delay_seconds" in baseline
        assert "participation_rate_percent" in baseline
        assert baseline["finality_delay_seconds"].count == 1
        assert baseline["finality_delay_seconds"].mean == 13.2

    def test_collect_baseline_all(self) -> None:
        """collect_baseline with no args should collect all metrics."""
        tool = self._make_tool()
        baseline = tool.collect_baseline()
        assert len(baseline) >= len(CONSENSUS_QUERIES)

    def test_get_metric_summary_no_history(self) -> None:
        """get_metric_summary should return None with no history."""
        tool = self._make_tool()
        summary = tool.get_metric_summary("nonexistent")
        assert summary is None

    def test_get_metric_summary_with_history(self) -> None:
        """get_metric_summary should compute statistics from history."""
        tool = self._make_tool()
        # Query metric multiple times to build history
        tool.query_metric("finality_delay_seconds")
        tool.query_metric("finality_delay_seconds")
        tool.query_metric("finality_delay_seconds")

        summary = tool.get_metric_summary("finality_delay_seconds")
        assert summary is not None
        assert summary.count == 3
        assert summary.mean == pytest.approx(13.2)
        assert summary.min_val == pytest.approx(13.2)
        assert summary.max_val == pytest.approx(13.2)

    def test_compare_with_baseline(self) -> None:
        """compare_with_baseline should compute deviations."""
        tool = self._make_tool()
        baseline = tool.collect_baseline(
            metric_names=["finality_delay_seconds"]
        )
        current = {"finality_delay_seconds": 26.4}  # 2x baseline

        comparison = tool.compare_with_baseline(baseline, current)
        assert "finality_delay_seconds" in comparison
        assert comparison["finality_delay_seconds"]["deviation_percent"] == pytest.approx(100.0)
        assert comparison["finality_delay_seconds"]["current_value"] == 26.4

    def test_compare_with_baseline_significant(self) -> None:
        """compare should flag significant deviations."""
        tool = self._make_tool()

        # Create baseline with some variance
        baseline = {
            "test_metric": MetricSummary(
                metric_name="test_metric",
                count=10,
                mean=50.0,
                min_val=45.0,
                max_val=55.0,
                std_dev=3.0,
                latest=50.0,
            )
        }
        current = {"test_metric": 60.0}  # z-score = (60-50)/3 = 3.33

        comparison = tool.compare_with_baseline(baseline, current)
        assert comparison["test_metric"]["significant"] is True
        assert comparison["test_metric"]["z_score"] == pytest.approx(3.33, abs=0.01)

    def test_clear_history(self) -> None:
        """clear_history should reset all metric history."""
        tool = self._make_tool()
        tool.query_metric("finality_delay_seconds")
        tool.clear_history()

        summary = tool.get_metric_summary("finality_delay_seconds")
        assert summary is None

    def test_query_with_real_prometheus_client(self) -> None:
        """Test with a mocked PrometheusClient (not dry-run)."""
        prom = MagicMock(spec=PrometheusClient)
        prom.query.return_value = QueryResult(
            status="success",
            result_type="vector",
            data=[{"value": [0, "42.5"]}],
        )

        tool = PrometheusQueryTool(prometheus_client=prom, dry_run=False)
        sample = tool.query_metric("finality_delay_seconds")

        assert sample is not None
        assert sample.value == 42.5
        prom.query.assert_called_once()

    def test_query_failure_returns_none(self) -> None:
        """Failed query should return None."""
        prom = MagicMock(spec=PrometheusClient)
        prom.query.return_value = QueryResult(
            status="error",
            result_type="vector",
            error="connection refused",
        )

        tool = PrometheusQueryTool(prometheus_client=prom, dry_run=False)
        sample = tool.query_metric("finality_delay_seconds")

        assert sample is None
