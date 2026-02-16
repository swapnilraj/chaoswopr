"""Blast radius configuration and validation for chaoswopr.

Enforces safety limits on the percentage of nodes that can be affected
by chaos injection at any given time. Supports phased rollout (5% -> 10% -> 20%)
and per-client-type limits.

Key constraint: NEVER affect more than 33% of nodes simultaneously.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Absolute safety limit - never exceed this
MAX_BLAST_RADIUS_PERCENT = 33.0


@dataclass
class BlastRadiusConfig:
    """Configuration for blast radius limits.

    Attributes:
        max_affected_percent: Maximum percentage of nodes that can be affected.
            Must be <= 33%.
        phased_rollout: List of percentages for phased fault rollout.
            Must be in ascending order, each <= max_affected_percent.
        per_client_max_percent: Maximum percentage of any single client type
            that can be affected. Prevents wiping out all nodes of one type.
        observation_window_seconds: Minimum time between rollout phases.
    """

    max_affected_percent: float = 33.0
    phased_rollout: list[float] = field(default_factory=lambda: [5.0, 10.0, 20.0, 33.0])
    per_client_max_percent: float = 50.0
    observation_window_seconds: int = 60

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self.validate()

    def validate(self) -> list[str]:
        """Validate the blast radius configuration.

        Returns:
            List of validation error messages. Empty means valid.

        Raises:
            ValueError: If the configuration violates safety limits.
        """
        errors: list[str] = []

        # Hard safety limit
        if self.max_affected_percent > MAX_BLAST_RADIUS_PERCENT:
            errors.append(
                f"max_affected_percent ({self.max_affected_percent}%) "
                f"exceeds safety limit ({MAX_BLAST_RADIUS_PERCENT}%)"
            )

        if self.max_affected_percent < 0:
            errors.append("max_affected_percent must be >= 0")

        # Per-client limit
        if self.per_client_max_percent < 0 or self.per_client_max_percent > 100:
            errors.append("per_client_max_percent must be between 0 and 100")

        # Observation window
        if self.observation_window_seconds < 0:
            errors.append("observation_window_seconds must be >= 0")

        # Phased rollout validation
        if self.phased_rollout:
            # Must be ascending
            for i in range(1, len(self.phased_rollout)):
                if self.phased_rollout[i] <= self.phased_rollout[i - 1]:
                    errors.append(
                        f"Phased rollout must be ascending: "
                        f"{self.phased_rollout[i]} <= {self.phased_rollout[i-1]}"
                    )
                    break

            # No value should exceed max
            for val in self.phased_rollout:
                if val > MAX_BLAST_RADIUS_PERCENT:
                    errors.append(
                        f"Phased rollout value {val}% exceeds safety limit "
                        f"({MAX_BLAST_RADIUS_PERCENT}%)"
                    )
                    break

            # No value should be negative
            if any(v < 0 for v in self.phased_rollout):
                errors.append("Phased rollout values must be >= 0")

        if errors:
            raise ValueError(f"Invalid blast radius config: {'; '.join(errors)}")

        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlastRadiusConfig:
        """Create a BlastRadiusConfig from a dictionary.

        Args:
            data: Dictionary with configuration values.

        Returns:
            BlastRadiusConfig instance.
        """
        return cls(
            max_affected_percent=data.get("max_affected_percent", 33.0),
            phased_rollout=data.get("phased_rollout", [5.0, 10.0, 20.0, 33.0]),
            per_client_max_percent=data.get("per_client_max_percent", 50.0),
            observation_window_seconds=data.get("observation_window_seconds", 60),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "max_affected_percent": self.max_affected_percent,
            "phased_rollout": self.phased_rollout,
            "per_client_max_percent": self.per_client_max_percent,
            "observation_window_seconds": self.observation_window_seconds,
        }


def calculate_affected_nodes(
    total_nodes: int,
    percent: float,
) -> int:
    """Calculate the number of nodes affected by a given percentage.

    Args:
        total_nodes: Total number of nodes in the testnet.
        percent: Percentage of nodes to affect.

    Returns:
        Number of nodes affected (rounded down).
    """
    return int(total_nodes * percent / 100.0)


def validate_blast_radius(
    config: BlastRadiusConfig,
    total_nodes: int,
    requested_nodes: int,
    client_counts: dict[str, int] | None = None,
    requested_by_client: dict[str, int] | None = None,
) -> tuple[bool, list[str]]:
    """Validate a fault injection request against blast radius limits.

    Args:
        config: The blast radius configuration.
        total_nodes: Total number of nodes in the testnet.
        requested_nodes: Number of nodes the injection wants to affect.
        client_counts: Total node count per client type.
        requested_by_client: Nodes to affect per client type.

    Returns:
        Tuple of (is_valid, list_of_violation_messages).
    """
    violations: list[str] = []

    if total_nodes <= 0:
        violations.append("total_nodes must be > 0")
        return False, violations

    # Check overall blast radius
    actual_percent = (requested_nodes / total_nodes) * 100.0
    if actual_percent > config.max_affected_percent:
        violations.append(
            f"Requested {requested_nodes} nodes ({actual_percent:.1f}%) "
            f"exceeds max_affected_percent ({config.max_affected_percent}%)"
        )

    # Check absolute safety limit
    if actual_percent > MAX_BLAST_RADIUS_PERCENT:
        violations.append(
            f"Requested {requested_nodes} nodes ({actual_percent:.1f}%) "
            f"exceeds absolute safety limit ({MAX_BLAST_RADIUS_PERCENT}%)"
        )

    # Check per-client limits
    if client_counts and requested_by_client:
        for client_type, requested in requested_by_client.items():
            total_for_client = client_counts.get(client_type, 0)
            if total_for_client > 0:
                client_percent = (requested / total_for_client) * 100.0
                if client_percent > config.per_client_max_percent:
                    violations.append(
                        f"Requested {requested} {client_type} nodes ({client_percent:.1f}%) "
                        f"exceeds per_client_max_percent ({config.per_client_max_percent}%)"
                    )

    return len(violations) == 0, violations


def get_next_rollout_phase(
    config: BlastRadiusConfig,
    current_percent: float,
) -> float | None:
    """Get the next phase in the rollout schedule.

    Args:
        config: The blast radius configuration.
        current_percent: Current percentage of nodes affected.

    Returns:
        Next rollout percentage, or None if at max.
    """
    for phase_percent in config.phased_rollout:
        if phase_percent > current_percent:
            return phase_percent
    return None
