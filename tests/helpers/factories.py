"""Test data factories for generating consistent test fixtures."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def make_experiment_run(
    *,
    experiment_id: str | None = None,
    scenario_name: str = "baseline_observation",
    status: str = "pending",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a test experiment run record."""
    return {
        "experiment_id": experiment_id or str(uuid.uuid4()),
        "scenario_name": scenario_name,
        "status": status,
        "started_at": started_at or datetime.now(timezone.utc),
        "completed_at": completed_at,
        "config": {},
        "results": None,
    }


def make_metric_snapshot(
    *,
    experiment_id: str | None = None,
    metric_name: str = "finality_delay_seconds",
    value: float = 13.2,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Create a test metric snapshot record."""
    return {
        "experiment_id": experiment_id or str(uuid.uuid4()),
        "metric_name": metric_name,
        "value": value,
        "timestamp": timestamp or datetime.now(timezone.utc),
        "labels": {},
    }


def make_audit_log_entry(
    *,
    agent_id: str = "orchestrator",
    action_type: str = "experiment_start",
    target: str = "testnet-001",
    parameters: dict[str, Any] | None = None,
    outcome: str = "success",
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Create a test audit log entry."""
    return {
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        "agent_id": agent_id,
        "action_type": action_type,
        "target": target,
        "parameters": parameters or {},
        "outcome": outcome,
        "trace_id": str(uuid.uuid4()),
    }


def make_scenario_config(
    *,
    name: str = "test_scenario",
    hypothesis: str = "Test hypothesis",
    node_count: int = 50,
    max_affected_percent: float = 20.0,
) -> dict[str, Any]:
    """Create a test scenario configuration."""
    return {
        "version": "1.0",
        "name": name,
        "description": f"Test scenario: {name}",
        "hypothesis": hypothesis,
        "network_config": {
            "node_count": node_count,
            "client_distribution": {
                "execution": {"nethermind": 0.4, "geth": 0.3, "besu": 0.15, "erigon": 0.15},
                "consensus": {"prysm": 0.4, "lighthouse": 0.3, "teku": 0.15, "nimbus": 0.15},
            },
        },
        "fault_sequence": [
            {"time": "0s", "action": "baseline", "description": "Start baseline"},
            {"time": "60s", "action": "complete", "description": "End"},
        ],
        "slo_thresholds": {
            "finality_delay_max_epochs": 5,
            "slashing_rate_max_percent": 5.0,
            "participation_rate_min_percent": 66.0,
            "recovery_time_max_seconds": 300,
        },
        "blast_radius": {
            "max_affected_percent": max_affected_percent,
            "phased_rollout": [5.0, 10.0, 20.0] if max_affected_percent > 0 else [],
        },
        "success_criteria": "Test criteria",
        "tags": ["test"],
    }


def make_blast_radius_config(
    *,
    max_affected_percent: float = 33.0,
    phased_rollout: list[float] | None = None,
    per_client_max_percent: float = 50.0,
    observation_window_seconds: int = 60,
) -> dict[str, Any]:
    """Create a test blast radius configuration."""
    return {
        "max_affected_percent": max_affected_percent,
        "phased_rollout": phased_rollout or [5.0, 10.0, 20.0, 33.0],
        "per_client_max_percent": per_client_max_percent,
        "observation_window_seconds": observation_window_seconds,
    }


def make_circuit_breaker_state(
    *,
    state: str = "armed",
    trip_reason: str | None = None,
    last_check: datetime | None = None,
) -> dict[str, Any]:
    """Create a test circuit breaker state."""
    return {
        "state": state,
        "trip_reason": trip_reason,
        "last_check": (last_check or datetime.now(timezone.utc)).isoformat(),
        "trip_count": 0 if state == "armed" else 1,
        "thresholds": {
            "finality_delay_max_seconds": 600,
            "slashing_rate_max_percent": 5.0,
            "participation_rate_min_percent": 66.0,
        },
    }
