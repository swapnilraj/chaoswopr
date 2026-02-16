"""Unit tests for client diversity configuration."""

from __future__ import annotations

import pytest

from chaoswopr.infrastructure.testnet.client_config import (
    CONSENSUS_CLIENTS,
    EXECUTION_CLIENTS,
    ClientConfig,
    ClientDistribution,
)


class TestClientDistribution:
    """Tests for ClientDistribution."""

    def test_valid_distribution(self) -> None:
        dist = ClientDistribution({"nethermind": 0.4, "geth": 0.3, "besu": 0.15, "erigon": 0.15})
        errors = dist.validate(EXECUTION_CLIENTS)
        assert errors == []

    def test_invalid_client_name(self) -> None:
        dist = ClientDistribution({"invalid_client": 1.0})
        errors = dist.validate(EXECUTION_CLIENTS)
        assert any("Unknown client" in e for e in errors)

    def test_ratio_not_summing_to_one(self) -> None:
        dist = ClientDistribution({"nethermind": 0.5, "geth": 0.3})
        errors = dist.validate(EXECUTION_CLIENTS)
        assert any("sum to" in e for e in errors)

    def test_negative_ratio(self) -> None:
        dist = ClientDistribution({"nethermind": -0.5, "geth": 1.5})
        errors = dist.validate(EXECUTION_CLIENTS)
        assert any("Invalid ratio" in e for e in errors)

    def test_get_node_counts_50(self) -> None:
        dist = ClientDistribution({"nethermind": 0.4, "geth": 0.3, "besu": 0.15, "erigon": 0.15})
        counts = dist.get_node_counts(50)
        assert sum(counts.values()) == 50
        # nethermind gets 20 from int(50*0.4) + 1 remainder = 21
        assert counts["nethermind"] == 21
        assert counts["geth"] == 15

    def test_get_node_counts_100(self) -> None:
        dist = ClientDistribution({"nethermind": 0.4, "geth": 0.3, "besu": 0.15, "erigon": 0.15})
        counts = dist.get_node_counts(100)
        assert sum(counts.values()) == 100
        assert counts["nethermind"] == 40

    def test_get_node_counts_small(self) -> None:
        dist = ClientDistribution({"nethermind": 0.5, "geth": 0.5})
        counts = dist.get_node_counts(4)
        assert sum(counts.values()) == 4
        assert counts["nethermind"] == 2
        assert counts["geth"] == 2

    def test_get_node_counts_handles_remainder(self) -> None:
        """Node counts should always sum to total_nodes."""
        dist = ClientDistribution({"nethermind": 0.33, "geth": 0.33, "besu": 0.34})
        counts = dist.get_node_counts(10)
        assert sum(counts.values()) == 10


class TestClientConfig:
    """Tests for ClientConfig."""

    def test_default_config(self) -> None:
        config = ClientConfig()
        assert config.node_count == 50
        errors = config.validate()
        assert errors == []

    def test_valid_custom_config(self) -> None:
        config = ClientConfig(
            node_count=100,
            execution=ClientDistribution({"nethermind": 0.5, "geth": 0.5}),
            consensus=ClientDistribution({"prysm": 0.5, "lighthouse": 0.5}),
        )
        errors = config.validate()
        assert errors == []

    def test_too_few_nodes(self) -> None:
        config = ClientConfig(node_count=2)
        errors = config.validate()
        assert any("node_count" in e for e in errors)

    def test_too_many_nodes(self) -> None:
        config = ClientConfig(node_count=1000)
        errors = config.validate()
        assert any("node_count" in e for e in errors)

    def test_get_execution_counts(self) -> None:
        config = ClientConfig(node_count=50)
        counts = config.get_execution_counts()
        assert sum(counts.values()) == 50

    def test_get_consensus_counts(self) -> None:
        config = ClientConfig(node_count=50)
        counts = config.get_consensus_counts()
        assert sum(counts.values()) == 50

    def test_from_dict(self) -> None:
        data = {
            "node_count": 100,
            "client_distribution": {
                "execution": {"nethermind": 0.5, "geth": 0.5},
                "consensus": {"prysm": 0.5, "lighthouse": 0.5},
            },
        }
        config = ClientConfig.from_dict(data)
        assert config.node_count == 100

    def test_to_dict(self) -> None:
        config = ClientConfig()
        d = config.to_dict()
        assert d["node_count"] == 50
        assert "execution" in d["client_distribution"]
        assert "consensus" in d["client_distribution"]

    def test_to_participants_list(self) -> None:
        config = ClientConfig(
            node_count=10,
            execution=ClientDistribution({"nethermind": 0.5, "geth": 0.5}),
            consensus=ClientDistribution({"prysm": 0.5, "lighthouse": 0.5}),
        )
        participants = config.to_participants_list()
        assert len(participants) > 0
        total_count = sum(p["count"] for p in participants)
        assert total_count == 10
        for p in participants:
            assert "el_type" in p
            assert "cl_type" in p
            assert "count" in p

    def test_to_participants_list_default(self) -> None:
        config = ClientConfig(node_count=50)
        participants = config.to_participants_list()
        total = sum(p["count"] for p in participants)
        assert total == 50
