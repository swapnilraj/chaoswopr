"""Root conftest.py - shared pytest fixtures for chaoswopr tests.

Provides fixtures for:
- PostgreSQL (via testcontainers for integration, mock for unit)
- S3/MinIO (via moto for unit, testcontainers for integration)
- Redis (via testcontainers for integration)
- Prometheus mock server
- Kurtosis mock client
- Common test data factories
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
SCHEMA_DIR = CONFIG_DIR / "schema"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CONFIGS_DIR = FIXTURES_DIR / "sample_configs"


# ---------------------------------------------------------------------------
# Scenario fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_scenario_yaml() -> dict[str, Any]:
    """Return a valid scenario dictionary matching the JSON Schema."""
    return {
        "version": "1.0",
        "name": "baseline_observation",
        "description": "No-fault baseline observation scenario for smoke testing",
        "hypothesis": "The network maintains healthy finality and participation with no faults injected",
        "network_config": {
            "node_count": 50,
            "client_distribution": {
                "execution": {"nethermind": 0.4, "geth": 0.3, "besu": 0.15, "erigon": 0.15},
                "consensus": {"prysm": 0.4, "lighthouse": 0.3, "teku": 0.15, "nimbus": 0.15},
            },
        },
        "fault_sequence": [
            {
                "time": "0s",
                "action": "baseline",
                "description": "Begin baseline observation with no faults",
            },
            {
                "time": "300s",
                "action": "observe",
                "description": "Continue observing network health",
            },
            {
                "time": "600s",
                "action": "complete",
                "description": "End observation period",
            },
        ],
        "slo_thresholds": {
            "finality_delay_max_epochs": 5,
            "slashing_rate_max_percent": 5.0,
            "participation_rate_min_percent": 66.0,
            "recovery_time_max_seconds": 300,
        },
        "blast_radius": {
            "max_affected_percent": 0.0,
            "phased_rollout": [],
        },
        "success_criteria": "Finality maintained within normal parameters and participation rate stays above 95%",
        "tags": ["baseline", "smoke-test"],
    }


@pytest.fixture
def invalid_scenario_yaml() -> dict[str, Any]:
    """Return an invalid scenario dictionary (missing required fields)."""
    return {
        "name": "invalid_scenario",
        # Missing: version, hypothesis, fault_sequence, slo_thresholds, etc.
    }


@pytest.fixture
def valid_scenario_yaml_string(valid_scenario_yaml: dict[str, Any]) -> str:
    """Return valid scenario as a YAML string."""
    return yaml.dump(valid_scenario_yaml, default_flow_style=False)


@pytest.fixture
def scenario_schema() -> dict[str, Any]:
    """Load the scenario JSON Schema."""
    schema_path = SCHEMA_DIR / "scenario_schema.json"
    if schema_path.exists():
        with open(schema_path) as f:
            return json.load(f)
    pytest.skip("Scenario schema not yet created")


# ---------------------------------------------------------------------------
# Blast radius fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_blast_radius_config() -> dict[str, Any]:
    """Default blast radius configuration."""
    return {
        "max_affected_percent": 33.0,
        "phased_rollout": [5.0, 10.0, 20.0, 33.0],
        "per_client_max_percent": 50.0,
        "observation_window_seconds": 60,
    }


# ---------------------------------------------------------------------------
# Circuit breaker fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def circuit_breaker_thresholds() -> dict[str, Any]:
    """Default circuit breaker thresholds."""
    return {
        "finality_delay_max_seconds": 600,  # 10 minutes
        "slashing_rate_max_percent": 5.0,
        "participation_rate_min_percent": 66.0,
    }


# ---------------------------------------------------------------------------
# Mock service fixtures (for unit tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_prometheus() -> MagicMock:
    """Create a mock Prometheus client."""
    mock = MagicMock()
    mock.query.return_value = {"status": "success", "data": {"resultType": "vector", "result": []}}
    mock.query_range.return_value = {
        "status": "success",
        "data": {"resultType": "matrix", "result": []},
    }
    return mock


@pytest.fixture
def mock_kurtosis() -> MagicMock:
    """Create a mock Kurtosis client."""
    mock = MagicMock()
    mock.create_enclave.return_value = {"enclave_id": "test-enclave-001"}
    mock.get_enclave_status.return_value = {"status": "running", "services": {}}
    mock.destroy_enclave.return_value = True
    return mock


@pytest.fixture
def mock_s3_client() -> MagicMock:
    """Create a mock S3 client."""
    mock = MagicMock()
    mock.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    mock.get_object.return_value = {"Body": MagicMock()}
    return mock


@pytest.fixture
def mock_redis() -> MagicMock:
    """Create a mock Redis client."""
    mock = MagicMock()
    mock.publish.return_value = 1
    mock.subscribe.return_value = None
    return mock


@pytest.fixture
def mock_postgres_session() -> MagicMock:
    """Create a mock SQLAlchemy session."""
    mock = MagicMock()
    mock.add.return_value = None
    mock.commit.return_value = None
    mock.query.return_value = MagicMock()
    mock.rollback.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Environment fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_env_vars() -> Generator[dict[str, str], None, None]:
    """Set up test environment variables."""
    env_vars = {
        "CHAOSWOPR_ENV": "test",
        "CHAOSWOPR_DB_HOST": "localhost",
        "CHAOSWOPR_DB_PORT": "5432",
        "CHAOSWOPR_DB_NAME": "chaoswopr_test",
        "CHAOSWOPR_DB_USER": "test",
        "CHAOSWOPR_DB_PASSWORD": "test",
        "CHAOSWOPR_S3_BUCKET": "chaoswopr-test",
        "CHAOSWOPR_S3_ENDPOINT": "http://localhost:9000",
        "CHAOSWOPR_REDIS_URL": "redis://localhost:6379/0",
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars


# ---------------------------------------------------------------------------
# Temporary directory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_scenario_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for scenario files."""
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    return scenario_dir


@pytest.fixture
def tmp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for configuration files."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir
