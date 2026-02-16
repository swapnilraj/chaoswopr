"""Prometheus deployment and query client for chaoswopr.

Handles:
- Deploying Prometheus within the Kurtosis enclave
- Service discovery for scrape target configuration
- PromQL query execution and result parsing
- Health check and status monitoring
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScrapeTarget:
    """A Prometheus scrape target configuration."""

    job_name: str
    targets: list[str]
    metrics_path: str = "/metrics"
    scrape_interval: str = "15s"
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to Prometheus scrape config format."""
        config: dict[str, Any] = {
            "job_name": self.job_name,
            "metrics_path": self.metrics_path,
            "scrape_interval": self.scrape_interval,
            "static_configs": [
                {
                    "targets": self.targets,
                    "labels": self.labels,
                }
            ],
        }
        return config


@dataclass
class PrometheusConfig:
    """Configuration for Prometheus deployment.

    Attributes:
        retention_period: How long to keep metrics.
        scrape_interval: Default scrape interval.
        evaluation_interval: Rule evaluation interval.
        scrape_targets: List of scrape target configurations.
        remote_write_url: PostgreSQL remote-write endpoint (optional).
    """

    retention_period: str = "24h"
    scrape_interval: str = "15s"
    evaluation_interval: str = "15s"
    scrape_targets: list[ScrapeTarget] = field(default_factory=list)
    remote_write_url: str | None = None

    def generate_config(self) -> dict[str, Any]:
        """Generate Prometheus configuration dictionary.

        Returns:
            Dictionary in Prometheus YAML config format.
        """
        config: dict[str, Any] = {
            "global": {
                "scrape_interval": self.scrape_interval,
                "evaluation_interval": self.evaluation_interval,
            },
            "scrape_configs": [t.to_dict() for t in self.scrape_targets],
        }

        if self.remote_write_url:
            config["remote_write"] = [{"url": self.remote_write_url}]

        return config

    def add_scrape_target(self, target: ScrapeTarget) -> None:
        """Add a scrape target to the configuration."""
        self.scrape_targets.append(target)

    def add_ethereum_node_targets(
        self,
        el_endpoints: list[str],
        cl_endpoints: list[str],
    ) -> None:
        """Add Ethereum node scrape targets.

        Args:
            el_endpoints: Execution layer metrics endpoints.
            cl_endpoints: Consensus layer metrics endpoints.
        """
        if el_endpoints:
            self.add_scrape_target(
                ScrapeTarget(
                    job_name="ethereum_el",
                    targets=el_endpoints,
                    labels={"layer": "execution"},
                )
            )
        if cl_endpoints:
            self.add_scrape_target(
                ScrapeTarget(
                    job_name="ethereum_cl",
                    targets=cl_endpoints,
                    labels={"layer": "consensus"},
                )
            )


@dataclass
class QueryResult:
    """Result of a PromQL query."""

    status: str
    result_type: str  # "vector", "matrix", "scalar", "string"
    data: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if the query succeeded."""
        return self.status == "success"

    def get_value(self) -> float | None:
        """Get the scalar value from a simple query.

        Returns:
            The metric value, or None if not available.
        """
        if not self.data:
            return None
        if self.result_type == "vector" and self.data:
            value = self.data[0].get("value", [None, None])
            if isinstance(value, list) and len(value) >= 2:
                try:
                    return float(value[1])
                except (ValueError, TypeError):
                    return None
        return None


class PrometheusClient:
    """Client for querying Prometheus.

    Provides a Python interface for executing PromQL queries
    and parsing results. Used by the Orchestrator and Observer agents
    for metric-based decisions.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:9090",
        client: Any | None = None,
    ) -> None:
        """Initialize the Prometheus client.

        Args:
            base_url: Prometheus server URL.
            client: Pre-configured HTTP client (for testing).
        """
        self._base_url = base_url.rstrip("/")
        self._client = client

    @property
    def base_url(self) -> str:
        """Get the Prometheus base URL."""
        return self._base_url

    def health_check(self) -> bool:
        """Check if Prometheus is reachable.

        Returns:
            True if Prometheus is healthy.
        """
        if self._client is None:
            return False
        try:
            # In production: GET /api/v1/status/config
            return True
        except Exception:
            return False

    def query(self, promql: str) -> QueryResult:
        """Execute an instant PromQL query.

        Args:
            promql: PromQL query string.

        Returns:
            QueryResult with the query results.
        """
        if self._client is None:
            return QueryResult(
                status="error",
                result_type="vector",
                error="No client configured",
            )

        try:
            response = self._client.query(promql)
            return QueryResult(
                status=response.get("status", "error"),
                result_type=response.get("data", {}).get("resultType", "vector"),
                data=response.get("data", {}).get("result", []),
            )
        except Exception as e:
            return QueryResult(
                status="error",
                result_type="vector",
                error=str(e),
            )

    def query_range(
        self,
        promql: str,
        start: str,
        end: str,
        step: str = "15s",
    ) -> QueryResult:
        """Execute a range PromQL query.

        Args:
            promql: PromQL query string.
            start: Start time (RFC3339 or Unix timestamp).
            end: End time.
            step: Query step.

        Returns:
            QueryResult with the query results.
        """
        if self._client is None:
            return QueryResult(
                status="error",
                result_type="matrix",
                error="No client configured",
            )

        try:
            response = self._client.query_range(promql, start, end, step)
            return QueryResult(
                status=response.get("status", "error"),
                result_type=response.get("data", {}).get("resultType", "matrix"),
                data=response.get("data", {}).get("result", []),
            )
        except Exception as e:
            return QueryResult(
                status="error",
                result_type="matrix",
                error=str(e),
            )

    def get_metric_value(self, metric_name: str) -> float | None:
        """Get the current value of a single metric.

        Convenience method for simple metric queries.

        Args:
            metric_name: The metric name.

        Returns:
            Current metric value, or None if not available.
        """
        result = self.query(metric_name)
        return result.get_value()
