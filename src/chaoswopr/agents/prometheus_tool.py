"""Prometheus query tool for the Orchestrator Agent.

Provides a high-level interface for the Orchestrator Agent to query Prometheus
metrics. Supports parameterized PromQL queries, result parsing, statistical
summary generation, and pre-flight health checks.

The tool wraps the low-level PrometheusClient (from Track B) with
Orchestrator-specific query patterns and result formatting.

Query Categories:
  - Pre-flight health checks (cluster readiness validation)
  - Baseline metrics (establish normal operating ranges)
  - Real-time monitoring (SLO tracking during experiments)
  - Post-experiment analysis (metric comparison and statistics)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient, QueryResult

logger = logging.getLogger(__name__)


# Pre-defined PromQL queries for Ethereum consensus monitoring
CONSENSUS_QUERIES: dict[str, str] = {
    "finality_delay_seconds": (
        'beacon_head_slot - beacon_finalized_epoch * 32'
    ),
    "participation_rate_percent": (
        'beacon_current_epoch_active_validators_count > 0 and '
        'beacon_previous_epoch_attesting_validators_count / '
        'beacon_previous_epoch_active_validators_count * 100'
    ),
    "slashing_rate_percent": (
        'beacon_slashings_total / beacon_validators_total * 100'
    ),
    "attestation_inclusion_delay": (
        'beacon_attestation_inclusion_delay_bucket'
    ),
    "block_proposal_rate": (
        'rate(beacon_blocks_total[5m])'
    ),
    "peer_count": (
        'p2p_peer_count'
    ),
    "head_slot": (
        'beacon_head_slot'
    ),
    "finalized_epoch": (
        'beacon_finalized_epoch'
    ),
    "validator_balance_avg": (
        'avg(beacon_validator_balance)'
    ),
    "mempool_size": (
        'txpool_pending'
    ),
}


@dataclass
class MetricSample:
    """A single metric sample with metadata.

    Attributes:
        metric_name: Name of the metric.
        value: Current metric value.
        timestamp: When the sample was taken.
        labels: Additional Prometheus labels.
    """

    metric_name: str
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


@dataclass
class MetricSummary:
    """Statistical summary of a metric over time.

    Attributes:
        metric_name: Name of the metric.
        count: Number of samples.
        mean: Mean value.
        min_val: Minimum value.
        max_val: Maximum value.
        std_dev: Standard deviation.
        latest: Most recent value.
        samples: Raw sample values.
    """

    metric_name: str
    count: int = 0
    mean: float = 0.0
    min_val: float = float("inf")
    max_val: float = float("-inf")
    std_dev: float = 0.0
    latest: float = 0.0
    samples: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_name": self.metric_name,
            "count": self.count,
            "mean": self.mean,
            "min": self.min_val,
            "max": self.max_val,
            "std_dev": self.std_dev,
            "latest": self.latest,
        }


@dataclass
class HealthCheckResult:
    """Result of a pre-flight health check.

    Attributes:
        healthy: Whether the cluster is healthy enough for experiments.
        checks: Individual check results.
        summary: Human-readable summary.
        metrics: Current metric values.
    """

    healthy: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "healthy": self.healthy,
            "checks": self.checks,
            "summary": self.summary,
            "metrics": self.metrics,
        }


class PrometheusQueryTool:
    """High-level Prometheus query tool for the Orchestrator Agent.

    Wraps the PrometheusClient with pre-defined query patterns for
    Ethereum consensus monitoring. Used during pre-flight health checks,
    baseline establishment, real-time monitoring, and post-experiment analysis.

    Examples:
        >>> from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient
        >>> prom = PrometheusClient(base_url="http://localhost:9090")
        >>> tool = PrometheusQueryTool(prometheus_client=prom)
        >>> health = tool.pre_flight_health_check()
        >>> baseline = tool.collect_baseline()
    """

    def __init__(
        self,
        prometheus_client: PrometheusClient,
        custom_queries: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the Prometheus query tool.

        Args:
            prometheus_client: Prometheus client for executing queries.
            custom_queries: Additional custom PromQL queries to register.
            dry_run: If True, return mock data instead of querying Prometheus.
        """
        self._client = prometheus_client
        self._dry_run = dry_run

        # Build query registry from defaults + custom
        self._queries: dict[str, str] = dict(CONSENSUS_QUERIES)
        if custom_queries:
            self._queries.update(custom_queries)

        # History for statistical summaries
        self._history: dict[str, list[float]] = {}

    @property
    def available_metrics(self) -> list[str]:
        """Get list of available metric names."""
        return list(self._queries.keys())

    def query_metric(self, metric_name: str) -> MetricSample | None:
        """Query a single metric by name.

        Args:
            metric_name: Name of the metric to query.

        Returns:
            MetricSample if available, None if not found or error.
        """
        if self._dry_run:
            return self._get_dry_run_sample(metric_name)

        promql = self._queries.get(metric_name)
        if promql is None:
            # Try as a raw PromQL query
            promql = metric_name

        result = self._client.query(promql)
        if not result.success:
            logger.warning(
                "Failed to query metric %s: %s",
                metric_name,
                result.error,
            )
            return None

        value = result.get_value()
        if value is None:
            return None

        sample = MetricSample(
            metric_name=metric_name,
            value=value,
        )

        # Record in history
        if metric_name not in self._history:
            self._history[metric_name] = []
        self._history[metric_name].append(value)

        return sample

    def query_multiple(self, metric_names: list[str]) -> dict[str, float]:
        """Query multiple metrics at once.

        Args:
            metric_names: List of metric names to query.

        Returns:
            Dictionary of metric_name -> value for all successful queries.
        """
        results: dict[str, float] = {}
        for name in metric_names:
            sample = self.query_metric(name)
            if sample is not None:
                results[name] = sample.value
        return results

    def query_all(self) -> dict[str, float]:
        """Query all registered metrics.

        Returns:
            Dictionary of metric_name -> value for all successful queries.
        """
        return self.query_multiple(list(self._queries.keys()))

    def pre_flight_health_check(
        self,
        min_peer_count: int = 3,
        max_finality_delay: float = 300.0,
        min_participation_rate: float = 80.0,
    ) -> HealthCheckResult:
        """Run pre-flight health checks for experiment readiness.

        Validates that the Ethereum testnet is healthy enough to begin
        a chaos engineering experiment.

        Args:
            min_peer_count: Minimum peer count for healthy network.
            max_finality_delay: Maximum finality delay in seconds.
            min_participation_rate: Minimum participation rate percentage.

        Returns:
            HealthCheckResult with pass/fail status and details.
        """
        checks: list[dict[str, Any]] = []
        healthy = True
        metrics: dict[str, float] = {}

        # Check finality delay
        finality_sample = self.query_metric("finality_delay_seconds")
        if finality_sample is not None:
            metrics["finality_delay_seconds"] = finality_sample.value
            passed = finality_sample.value <= max_finality_delay
            checks.append({
                "check": "finality_delay",
                "passed": passed,
                "value": finality_sample.value,
                "threshold": max_finality_delay,
                "message": (
                    f"Finality delay {finality_sample.value:.1f}s "
                    f"{'<=' if passed else '>'} {max_finality_delay:.1f}s threshold"
                ),
            })
            if not passed:
                healthy = False
        else:
            checks.append({
                "check": "finality_delay",
                "passed": False,
                "value": None,
                "threshold": max_finality_delay,
                "message": "Could not query finality delay metric",
            })
            if not self._dry_run:
                healthy = False

        # Check participation rate
        participation_sample = self.query_metric("participation_rate_percent")
        if participation_sample is not None:
            metrics["participation_rate_percent"] = participation_sample.value
            passed = participation_sample.value >= min_participation_rate
            checks.append({
                "check": "participation_rate",
                "passed": passed,
                "value": participation_sample.value,
                "threshold": min_participation_rate,
                "message": (
                    f"Participation rate {participation_sample.value:.1f}% "
                    f"{'>=' if passed else '<'} {min_participation_rate:.1f}% threshold"
                ),
            })
            if not passed:
                healthy = False
        else:
            checks.append({
                "check": "participation_rate",
                "passed": False,
                "value": None,
                "threshold": min_participation_rate,
                "message": "Could not query participation rate metric",
            })
            if not self._dry_run:
                healthy = False

        # Check peer count
        peer_sample = self.query_metric("peer_count")
        if peer_sample is not None:
            metrics["peer_count"] = peer_sample.value
            passed = peer_sample.value >= min_peer_count
            checks.append({
                "check": "peer_count",
                "passed": passed,
                "value": peer_sample.value,
                "threshold": min_peer_count,
                "message": (
                    f"Peer count {int(peer_sample.value)} "
                    f"{'>=' if passed else '<'} {min_peer_count} threshold"
                ),
            })
            if not passed:
                healthy = False
        else:
            checks.append({
                "check": "peer_count",
                "passed": False,
                "value": None,
                "threshold": min_peer_count,
                "message": "Could not query peer count metric",
            })
            if not self._dry_run:
                healthy = False

        # Build summary
        passed_count = sum(1 for c in checks if c["passed"])
        summary = (
            f"Health check: {passed_count}/{len(checks)} checks passed. "
            f"{'Cluster is healthy.' if healthy else 'Cluster is NOT healthy.'}"
        )

        return HealthCheckResult(
            healthy=healthy,
            checks=checks,
            summary=summary,
            metrics=metrics,
        )

    def collect_baseline(
        self,
        metric_names: list[str] | None = None,
    ) -> dict[str, MetricSummary]:
        """Collect baseline metrics for comparison.

        Queries all specified metrics and returns their current values
        as baseline references for experiment comparison.

        Args:
            metric_names: Specific metrics to collect. If None, collects all.

        Returns:
            Dictionary of metric_name -> MetricSummary.
        """
        names = metric_names or list(self._queries.keys())
        baselines: dict[str, MetricSummary] = {}

        for name in names:
            sample = self.query_metric(name)
            if sample is not None:
                baselines[name] = MetricSummary(
                    metric_name=name,
                    count=1,
                    mean=sample.value,
                    min_val=sample.value,
                    max_val=sample.value,
                    std_dev=0.0,
                    latest=sample.value,
                    samples=[sample.value],
                )

        return baselines

    def get_metric_summary(self, metric_name: str) -> MetricSummary | None:
        """Get statistical summary of a metric from collected history.

        Args:
            metric_name: Name of the metric.

        Returns:
            MetricSummary with statistics, or None if no history.
        """
        history = self._history.get(metric_name, [])
        if not history:
            return None

        count = len(history)
        mean = sum(history) / count
        min_val = min(history)
        max_val = max(history)

        # Calculate standard deviation
        if count > 1:
            variance = sum((x - mean) ** 2 for x in history) / (count - 1)
            std_dev = math.sqrt(variance)
        else:
            std_dev = 0.0

        return MetricSummary(
            metric_name=metric_name,
            count=count,
            mean=mean,
            min_val=min_val,
            max_val=max_val,
            std_dev=std_dev,
            latest=history[-1],
            samples=list(history),
        )

    def compare_with_baseline(
        self,
        baseline: dict[str, MetricSummary],
        current: dict[str, float],
    ) -> dict[str, dict[str, Any]]:
        """Compare current metrics against a baseline.

        Args:
            baseline: Baseline metric summaries.
            current: Current metric values.

        Returns:
            Dictionary of metric_name -> comparison result.
        """
        comparisons: dict[str, dict[str, Any]] = {}

        for name, baseline_summary in baseline.items():
            current_value = current.get(name)
            if current_value is None:
                continue

            # Calculate deviation from baseline
            if baseline_summary.mean != 0:
                deviation_percent = (
                    (current_value - baseline_summary.mean) / abs(baseline_summary.mean) * 100
                )
            else:
                deviation_percent = 0.0

            # Calculate z-score if we have std_dev
            if baseline_summary.std_dev > 0:
                z_score = (current_value - baseline_summary.mean) / baseline_summary.std_dev
            else:
                z_score = 0.0

            comparisons[name] = {
                "metric_name": name,
                "baseline_mean": baseline_summary.mean,
                "current_value": current_value,
                "deviation_percent": deviation_percent,
                "z_score": z_score,
                "significant": abs(z_score) > 2.0,
            }

        return comparisons

    def clear_history(self) -> None:
        """Clear all collected metric history."""
        self._history.clear()

    def _get_dry_run_sample(self, metric_name: str) -> MetricSample:
        """Generate a mock metric sample for dry-run mode.

        Args:
            metric_name: Name of the metric.

        Returns:
            MetricSample with realistic mock data.
        """
        # Realistic mock values for common Ethereum metrics
        mock_values: dict[str, float] = {
            "finality_delay_seconds": 13.2,
            "participation_rate_percent": 96.5,
            "slashing_rate_percent": 0.0,
            "attestation_inclusion_delay": 1.2,
            "block_proposal_rate": 0.083,  # ~1 block per 12s
            "peer_count": 48.0,
            "head_slot": 1000.0,
            "finalized_epoch": 30.0,
            "validator_balance_avg": 32.0,
            "mempool_size": 150.0,
        }

        value = mock_values.get(metric_name, 0.0)

        # Record in history
        if metric_name not in self._history:
            self._history[metric_name] = []
        self._history[metric_name].append(value)

        return MetricSample(
            metric_name=metric_name,
            value=value,
        )
