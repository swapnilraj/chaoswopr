"""Client diversity configuration for Ethereum testnets.

Parameterizes client type ratios (execution and consensus layers)
for testnet deployments. Supports the spec requirement:
- 40% Nethermind, 30% Geth for execution layer
- 40% Prysm, 30% Lighthouse for consensus layer

Ratios are specified in a YAML config file that the Kurtosis package
reads, keeping experiment parameters decoupled from infrastructure code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Supported Ethereum clients
EXECUTION_CLIENTS = ["nethermind", "geth", "besu", "erigon"]
CONSENSUS_CLIENTS = ["prysm", "lighthouse", "teku", "nimbus", "lodestar"]

# Default mainnet-like distribution
DEFAULT_EXECUTION_DISTRIBUTION = {
    "nethermind": 0.40,
    "geth": 0.30,
    "besu": 0.15,
    "erigon": 0.15,
}

DEFAULT_CONSENSUS_DISTRIBUTION = {
    "prysm": 0.40,
    "lighthouse": 0.30,
    "teku": 0.15,
    "nimbus": 0.15,
}


@dataclass
class ClientDistribution:
    """Distribution of client types for a layer.

    Attributes:
        distribution: Mapping of client name to ratio (0.0 to 1.0).
            Ratios must sum to approximately 1.0.
    """

    distribution: dict[str, float] = field(default_factory=dict)

    def validate(self, valid_clients: list[str]) -> list[str]:
        """Validate the distribution.

        Args:
            valid_clients: List of valid client names.

        Returns:
            List of validation errors. Empty means valid.
        """
        errors: list[str] = []

        # Check all clients are valid
        for client in self.distribution:
            if client not in valid_clients:
                errors.append(f"Unknown client: {client}. Valid: {valid_clients}")

        # Check ratios
        for client, ratio in self.distribution.items():
            if ratio < 0 or ratio > 1:
                errors.append(f"Invalid ratio for {client}: {ratio} (must be 0.0-1.0)")

        # Check sum
        total = sum(self.distribution.values())
        if abs(total - 1.0) > 0.01:
            errors.append(f"Ratios sum to {total:.3f}, expected ~1.0")

        return errors

    def get_node_counts(self, total_nodes: int) -> dict[str, int]:
        """Calculate node counts for each client type.

        Args:
            total_nodes: Total number of nodes.

        Returns:
            Mapping of client name to number of nodes.
        """
        counts: dict[str, int] = {}
        remaining = total_nodes

        # Assign nodes proportionally, largest remainder method
        for client, ratio in sorted(
            self.distribution.items(), key=lambda x: x[1], reverse=True
        ):
            count = int(total_nodes * ratio)
            counts[client] = count
            remaining -= count

        # Distribute remainder to largest clients first
        for client in sorted(counts, key=lambda c: counts[c], reverse=True):
            if remaining <= 0:
                break
            counts[client] += 1
            remaining -= 1

        return counts


@dataclass
class ClientConfig:
    """Complete client configuration for a testnet.

    Attributes:
        node_count: Total number of nodes.
        execution: Execution layer client distribution.
        consensus: Consensus layer client distribution.
    """

    node_count: int = 50
    execution: ClientDistribution = field(
        default_factory=lambda: ClientDistribution(DEFAULT_EXECUTION_DISTRIBUTION.copy())
    )
    consensus: ClientDistribution = field(
        default_factory=lambda: ClientDistribution(DEFAULT_CONSENSUS_DISTRIBUTION.copy())
    )

    def validate(self) -> list[str]:
        """Validate the complete client configuration.

        Returns:
            List of validation errors. Empty means valid.
        """
        errors: list[str] = []

        if self.node_count < 4:
            errors.append(f"node_count must be >= 4, got {self.node_count}")
        if self.node_count > 500:
            errors.append(f"node_count must be <= 500, got {self.node_count}")

        errors.extend(self.execution.validate(EXECUTION_CLIENTS))
        errors.extend(self.consensus.validate(CONSENSUS_CLIENTS))

        return errors

    def get_execution_counts(self) -> dict[str, int]:
        """Get execution client node counts."""
        return self.execution.get_node_counts(self.node_count)

    def get_consensus_counts(self) -> dict[str, int]:
        """Get consensus client node counts."""
        return self.consensus.get_node_counts(self.node_count)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClientConfig:
        """Create from dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            ClientConfig instance.
        """
        el_dist = data.get("client_distribution", {}).get(
            "execution", DEFAULT_EXECUTION_DISTRIBUTION
        )
        cl_dist = data.get("client_distribution", {}).get(
            "consensus", DEFAULT_CONSENSUS_DISTRIBUTION
        )
        return cls(
            node_count=data.get("node_count", 50),
            execution=ClientDistribution(el_dist),
            consensus=ClientDistribution(cl_dist),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "node_count": self.node_count,
            "client_distribution": {
                "execution": self.execution.distribution,
                "consensus": self.consensus.distribution,
            },
        }

    def to_participants_list(self) -> list[dict[str, Any]]:
        """Generate ethpandaops/ethereum-package participants list.

        Creates the participant configuration format expected by
        the ethereum-package Kurtosis package.

        Returns:
            List of participant configuration dictionaries.
        """
        el_counts = self.get_execution_counts()
        cl_counts = self.get_consensus_counts()

        participants: list[dict[str, Any]] = []

        # Create participant entries for each EL/CL combination
        el_clients = list(el_counts.keys())
        cl_clients = list(cl_counts.keys())

        el_index = 0
        cl_index = 0
        el_remaining = {k: v for k, v in el_counts.items()}
        cl_remaining = {k: v for k, v in cl_counts.items()}

        while sum(el_remaining.values()) > 0 and sum(cl_remaining.values()) > 0:
            # Find next available EL and CL
            while el_index < len(el_clients) and el_remaining.get(el_clients[el_index], 0) == 0:
                el_index += 1
            while cl_index < len(cl_clients) and cl_remaining.get(cl_clients[cl_index], 0) == 0:
                cl_index += 1

            if el_index >= len(el_clients) or cl_index >= len(cl_clients):
                break

            el_client = el_clients[el_index]
            cl_client = cl_clients[cl_index]

            # Take the minimum of remaining counts
            count = min(el_remaining[el_client], cl_remaining[cl_client])
            if count > 0:
                participants.append({
                    "el_type": el_client,
                    "cl_type": cl_client,
                    "count": count,
                })
                el_remaining[el_client] -= count
                cl_remaining[cl_client] -= count

            # Move to next client when exhausted
            if el_remaining.get(el_client, 0) == 0:
                el_index += 1
            if cl_remaining.get(cl_client, 0) == 0:
                cl_index += 1

        return participants
