"""Unit tests for Prometheus deployment and query client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chaoswopr.infrastructure.monitoring.prometheus import (
    PrometheusClient,
    PrometheusConfig,
    QueryResult,
    ScrapeTarget,
)


class TestScrapeTarget:
    """Tests for ScrapeTarget."""

    def test_create_target(self) -> None:
        target = ScrapeTarget(
            job_name="ethereum_cl",
            targets=["10.0.0.1:9090", "10.0.0.2:9090"],
            labels={"layer": "consensus"},
        )
        assert target.job_name == "ethereum_cl"
        assert len(target.targets) == 2

    def test_to_dict(self) -> None:
        target = ScrapeTarget(
            job_name="test",
            targets=["localhost:9090"],
        )
        d = target.to_dict()
        assert d["job_name"] == "test"
        assert "static_configs" in d
        assert d["static_configs"][0]["targets"] == ["localhost:9090"]


class TestPrometheusConfig:
    """Tests for PrometheusConfig."""

    def test_default_config(self) -> None:
        config = PrometheusConfig()
        assert config.retention_period == "24h"
        assert config.scrape_interval == "15s"

    def test_generate_config(self) -> None:
        config = PrometheusConfig()
        config.add_scrape_target(
            ScrapeTarget(job_name="test", targets=["localhost:9090"])
        )
        prom_config = config.generate_config()
        assert "global" in prom_config
        assert "scrape_configs" in prom_config
        assert len(prom_config["scrape_configs"]) == 1

    def test_generate_config_with_remote_write(self) -> None:
        config = PrometheusConfig(remote_write_url="http://pg-adapter:9201/write")
        prom_config = config.generate_config()
        assert "remote_write" in prom_config

    def test_add_ethereum_node_targets(self) -> None:
        config = PrometheusConfig()
        config.add_ethereum_node_targets(
            el_endpoints=["10.0.0.1:8545", "10.0.0.2:8545"],
            cl_endpoints=["10.0.0.1:5052", "10.0.0.2:5052"],
        )
        assert len(config.scrape_targets) == 2

    def test_add_ethereum_empty_targets(self) -> None:
        config = PrometheusConfig()
        config.add_ethereum_node_targets(el_endpoints=[], cl_endpoints=[])
        assert len(config.scrape_targets) == 0


class TestQueryResult:
    """Tests for QueryResult."""

    def test_success(self) -> None:
        result = QueryResult(
            status="success",
            result_type="vector",
            data=[{"value": [1234567890, "13.2"]}],
        )
        assert result.success is True

    def test_failure(self) -> None:
        result = QueryResult(
            status="error",
            result_type="vector",
            error="query failed",
        )
        assert result.success is False

    def test_get_value(self) -> None:
        result = QueryResult(
            status="success",
            result_type="vector",
            data=[{"value": [1234567890, "13.2"]}],
        )
        assert result.get_value() == 13.2

    def test_get_value_empty(self) -> None:
        result = QueryResult(
            status="success",
            result_type="vector",
            data=[],
        )
        assert result.get_value() is None


class TestPrometheusClient:
    """Tests for PrometheusClient."""

    def test_create_client(self) -> None:
        client = PrometheusClient(base_url="http://localhost:9090")
        assert client.base_url == "http://localhost:9090"

    def test_url_trailing_slash_stripped(self) -> None:
        client = PrometheusClient(base_url="http://localhost:9090/")
        assert client.base_url == "http://localhost:9090"

    def test_health_check_no_client(self) -> None:
        client = PrometheusClient()
        assert client.health_check() is False

    def test_query_no_client(self) -> None:
        client = PrometheusClient()
        result = client.query("test_metric")
        assert result.success is False
        assert "No client" in (result.error or "")

    def test_query_with_mock(self, mock_prometheus: MagicMock) -> None:
        mock_prometheus.query.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"value": [1234567890, "42.0"]}],
            },
        }
        client = PrometheusClient(client=mock_prometheus)
        result = client.query("test_metric")
        assert result.success
        assert result.get_value() == 42.0

    def test_query_range_no_client(self) -> None:
        client = PrometheusClient()
        result = client.query_range("test", "1h", "now")
        assert result.success is False

    def test_get_metric_value(self, mock_prometheus: MagicMock) -> None:
        mock_prometheus.query.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"value": [1234567890, "13.2"]}],
            },
        }
        client = PrometheusClient(client=mock_prometheus)
        value = client.get_metric_value("finality_delay")
        assert value == 13.2

    def test_get_metric_value_no_client(self) -> None:
        client = PrometheusClient()
        value = client.get_metric_value("test")
        assert value is None
