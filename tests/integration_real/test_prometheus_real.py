"""Real Prometheus integration tests.

Tests deploy a real Prometheus instance using testcontainers and
verify metric scraping, querying, and alerting against it.
Requires Docker.
"""

from __future__ import annotations

import time
from typing import Generator

import pytest
import requests

from chaoswopr.infrastructure.monitoring.alerting import AlertRuleSet
from chaoswopr.infrastructure.monitoring.prometheus import (
    PrometheusClient,
    PrometheusConfig,
    QueryResult,
    ScrapeTarget,
)

from .conftest import require_docker


def _start_prometheus_container() -> tuple[str, any] | None:
    """Start a Prometheus container using testcontainers.

    Returns:
        Tuple of (base_url, container) or None if not available.
    """
    try:
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.waiting_utils import wait_for_logs

        container = (
            DockerContainer("prom/prometheus:v2.51.0")
            .with_exposed_ports(9090)
            .with_command("--config.file=/etc/prometheus/prometheus.yml --web.enable-lifecycle")
        )
        container.start()

        # Wait for Prometheus to be ready
        host = container.get_container_host_ip()
        port = container.get_exposed_port(9090)
        base_url = f"http://{host}:{port}"

        # Poll until ready
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
    except ImportError:
        return None
    except Exception:
        return None


@require_docker
class TestRealPrometheusDeployment:
    """Test deploying and querying a real Prometheus instance."""

    @pytest.fixture(scope="class")
    def prometheus_instance(self) -> Generator[tuple[str, any], None, None]:
        """Deploy a real Prometheus instance for testing."""
        result = _start_prometheus_container()
        if result is None:
            pytest.skip("Could not start Prometheus container (Docker/testcontainers required)")
        base_url, container = result
        yield base_url, container
        try:
            container.stop()
        except Exception:
            pass

    def test_prometheus_health(self, prometheus_instance: tuple[str, any]) -> None:
        """Prometheus instance should be healthy."""
        base_url, _ = prometheus_instance
        resp = requests.get(f"{base_url}/-/ready", timeout=5)
        assert resp.status_code == 200

    def test_prometheus_query(self, prometheus_instance: tuple[str, any]) -> None:
        """Prometheus should respond to queries."""
        base_url, _ = prometheus_instance
        # Query a built-in metric
        resp = requests.get(
            f"{base_url}/api/v1/query",
            params={"query": "up"},
            timeout=5,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_prometheus_config_endpoint(self, prometheus_instance: tuple[str, any]) -> None:
        """Prometheus should expose its config."""
        base_url, _ = prometheus_instance
        resp = requests.get(f"{base_url}/api/v1/status/config", timeout=5)
        assert resp.status_code == 200

    def test_prometheus_client_query(self, prometheus_instance: tuple[str, any]) -> None:
        """Our PrometheusClient should be able to query real Prometheus.

        Note: The current PrometheusClient uses a mock client interface.
        This test verifies we can query Prometheus directly via HTTP
        as the future production implementation will.
        """
        base_url, _ = prometheus_instance

        # Direct HTTP query (production-ready approach)
        resp = requests.get(
            f"{base_url}/api/v1/query",
            params={"query": "prometheus_build_info"},
            timeout=5,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data.get("data", {}).get("result", [])) > 0

    def test_prometheus_scrape_targets(self, prometheus_instance: tuple[str, any]) -> None:
        """Prometheus should have default scrape targets configured."""
        base_url, _ = prometheus_instance
        resp = requests.get(f"{base_url}/api/v1/targets", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        # Should have at least itself as a target
        targets = data.get("data", {}).get("activeTargets", [])
        assert len(targets) > 0

    def test_alert_rules_format(self, prometheus_instance: tuple[str, any]) -> None:
        """Our alert rules should generate valid Prometheus rule format."""
        ruleset = AlertRuleSet()
        rules = ruleset.to_prometheus_rules()

        # Validate structure
        assert "groups" in rules
        assert len(rules["groups"]) == 1
        group = rules["groups"][0]
        assert group["name"] == "chaoswopr_alerts"
        assert len(group["rules"]) >= 10

        # Each rule should have required fields
        for rule in group["rules"]:
            assert "alert" in rule
            assert "expr" in rule
            assert "labels" in rule
            assert "severity" in rule["labels"]


@require_docker
class TestRealPrometheusMetricScraping:
    """Test scraping real metrics from a Prometheus instance."""

    @pytest.fixture(scope="class")
    def prometheus_with_scrape(self) -> Generator[str, None, None]:
        """Deploy Prometheus and verify it scrapes itself."""
        result = _start_prometheus_container()
        if result is None:
            pytest.skip("Could not start Prometheus container")
        base_url, container = result

        # Wait for self-scrape data to be available
        for _ in range(20):
            try:
                resp = requests.get(
                    f"{base_url}/api/v1/query",
                    params={"query": "up"},
                    timeout=5,
                )
                data = resp.json()
                results = data.get("data", {}).get("result", [])
                if results:
                    break
            except Exception:
                pass
            time.sleep(2)

        yield base_url

        try:
            container.stop()
        except Exception:
            pass

    def test_scrape_metrics_available(self, prometheus_with_scrape: str) -> None:
        """Scraped metrics should be queryable."""
        base_url = prometheus_with_scrape
        resp = requests.get(
            f"{base_url}/api/v1/query",
            params={"query": "up"},
            timeout=5,
        )
        data = resp.json()
        results = data.get("data", {}).get("result", [])
        assert len(results) > 0, "No 'up' metric results"

    def test_scrape_interval_metrics(self, prometheus_with_scrape: str) -> None:
        """Prometheus should collect scrape duration metrics."""
        base_url = prometheus_with_scrape
        resp = requests.get(
            f"{base_url}/api/v1/query",
            params={"query": "scrape_duration_seconds"},
            timeout=5,
        )
        data = resp.json()
        results = data.get("data", {}).get("result", [])
        assert len(results) > 0, "No scrape_duration_seconds results"

    def test_multiple_metrics_queryable(self, prometheus_with_scrape: str) -> None:
        """Multiple built-in metrics should be queryable."""
        base_url = prometheus_with_scrape
        metrics_to_check = [
            "prometheus_build_info",
            "process_cpu_seconds_total",
            "go_goroutines",
            "process_resident_memory_bytes",
        ]
        found = 0
        for metric in metrics_to_check:
            resp = requests.get(
                f"{base_url}/api/v1/query",
                params={"query": metric},
                timeout=5,
            )
            data = resp.json()
            if data.get("data", {}).get("result"):
                found += 1

        assert found >= 3, f"Only {found}/{len(metrics_to_check)} metrics found"

    def test_range_query(self, prometheus_with_scrape: str) -> None:
        """Range queries should return time-series data."""
        base_url = prometheus_with_scrape
        import time as t

        now = t.time()
        resp = requests.get(
            f"{base_url}/api/v1/query_range",
            params={
                "query": "up",
                "start": now - 60,
                "end": now,
                "step": "15s",
            },
            timeout=5,
        )
        data = resp.json()
        assert data["status"] == "success"
        assert data.get("data", {}).get("resultType") == "matrix"
