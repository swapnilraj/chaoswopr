"""Conftest for real infrastructure integration tests.

Provides fixtures that require Docker and Kurtosis to be available.
Tests are automatically skipped when infrastructure is not present.
"""

from __future__ import annotations

import subprocess
import uuid
from typing import Generator

import pytest

from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient


def _is_docker_running() -> bool:
    """Check if Docker daemon is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _is_kurtosis_available() -> bool:
    """Check if Kurtosis CLI is installed."""
    try:
        result = subprocess.run(
            ["kurtosis", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _is_kurtosis_engine_running() -> bool:
    """Check if Kurtosis engine is running (requires Docker)."""
    if not _is_docker_running():
        return False
    try:
        result = subprocess.run(
            ["kurtosis", "engine", "status"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# Marks for infrastructure tests
require_docker = pytest.mark.skipif(
    not _is_docker_running(),
    reason="Docker daemon not running",
)

require_kurtosis = pytest.mark.skipif(
    not _is_kurtosis_available(),
    reason="Kurtosis CLI not installed",
)

require_kurtosis_engine = pytest.mark.skipif(
    not _is_kurtosis_engine_running(),
    reason="Kurtosis engine not running (start with `kurtosis engine start`)",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark all tests in this directory as infra tests."""
    for item in items:
        if "integration_real" in str(item.fspath):
            item.add_marker(pytest.mark.infra)
            item.add_marker(pytest.mark.timeout(600))


@pytest.fixture
def kurtosis_client() -> KurtosisClient:
    """Create a real (non-dry-run) Kurtosis client."""
    return KurtosisClient(dry_run=False)


@pytest.fixture
def unique_enclave_name() -> str:
    """Generate a unique enclave name for test isolation."""
    short_id = uuid.uuid4().hex[:8]
    return f"chaoswopr-test-{short_id}"


@pytest.fixture
def kurtosis_enclave(
    kurtosis_client: KurtosisClient,
    unique_enclave_name: str,
) -> Generator[str, None, None]:
    """Create and yield a Kurtosis enclave, always tearing down after.

    Yields:
        The enclave name.
    """
    kurtosis_client.create_enclave(unique_enclave_name)
    yield unique_enclave_name
    # Always cleanup, even on test failure
    try:
        kurtosis_client.destroy_enclave(unique_enclave_name)
    except Exception:
        pass
