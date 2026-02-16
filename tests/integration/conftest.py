"""Integration test conftest - fixtures requiring external services via testcontainers."""

from __future__ import annotations

from typing import Any, Generator
from unittest.mock import MagicMock

import pytest


# All integration tests are automatically marked
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Automatically mark all tests in this directory as integration tests."""
    for item in items:
        item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def postgres_container() -> Generator[dict[str, Any], None, None]:
    """Start a PostgreSQL container for integration tests.

    Uses testcontainers when available, falls back to mock for CI environments
    without Docker.
    """
    try:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine") as postgres:
            yield {
                "host": postgres.get_container_host_ip(),
                "port": postgres.get_exposed_port(5432),
                "user": "test",
                "password": "test",
                "dbname": "test",
                "url": postgres.get_connection_url(),
            }
    except Exception:
        # Fallback for environments without Docker
        yield {
            "host": "localhost",
            "port": "5432",
            "user": "test",
            "password": "test",
            "dbname": "chaoswopr_test",
            "url": "postgresql://test:test@localhost:5432/chaoswopr_test",
        }


@pytest.fixture(scope="session")
def redis_container() -> Generator[dict[str, Any], None, None]:
    """Start a Redis container for integration tests."""
    try:
        from testcontainers.redis import RedisContainer  # type: ignore[import-untyped]

        with RedisContainer("redis:7-alpine") as redis_c:
            yield {
                "host": redis_c.get_container_host_ip(),
                "port": redis_c.get_exposed_port(6379),
                "url": f"redis://{redis_c.get_container_host_ip()}:{redis_c.get_exposed_port(6379)}/0",
            }
    except Exception:
        yield {
            "host": "localhost",
            "port": "6379",
            "url": "redis://localhost:6379/0",
        }


@pytest.fixture
def mock_s3_integration() -> Generator[MagicMock, None, None]:
    """Create a moto-backed S3 mock for integration tests."""
    try:
        import boto3
        from moto import mock_aws

        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="chaoswopr-test-audit")
            s3.create_bucket(Bucket="chaoswopr-test-artifacts")
            yield s3
    except ImportError:
        yield MagicMock()
