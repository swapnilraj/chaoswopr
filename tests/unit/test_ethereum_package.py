"""Unit tests for the ethpandaops/ethereum-package integration."""

from __future__ import annotations

import pytest

from chaoswopr.infrastructure.testnet.client_config import ClientConfig, ClientDistribution
from chaoswopr.infrastructure.testnet.ethereum_package import (
    ETHEREUM_PACKAGE_URL,
    EthereumPackageConfig,
    ForkConfig,
    MEVConfig,
    SpammerConfig,
)


class TestForkConfig:
    """Tests for ForkConfig."""

    def test_default_disabled(self) -> None:
        config = ForkConfig()
        assert config.enabled is False

    def test_to_dict(self) -> None:
        config = ForkConfig(enabled=True, block_number=19000000)
        d = config.to_dict()
        assert d["enabled"] is True
        assert d["block_number"] == 19000000


class TestMEVConfig:
    """Tests for MEVConfig."""

    def test_default_disabled(self) -> None:
        config = MEVConfig()
        assert config.enabled is False

    def test_to_dict(self) -> None:
        config = MEVConfig(enabled=True, relay_type="flashbots")
        d = config.to_dict()
        assert d["enabled"] is True


class TestSpammerConfig:
    """Tests for SpammerConfig."""

    def test_default_config(self) -> None:
        config = SpammerConfig()
        assert config.enabled is True
        assert config.tps == 100

    def test_valid_config(self) -> None:
        config = SpammerConfig(tps=1000)
        errors = config.validate()
        assert errors == []

    def test_negative_tps(self) -> None:
        config = SpammerConfig(tps=-1)
        errors = config.validate()
        assert any("tps" in e for e in errors)

    def test_excessive_tps(self) -> None:
        config = SpammerConfig(tps=50000)
        errors = config.validate()
        assert any("tps" in e for e in errors)


class TestEthereumPackageConfig:
    """Tests for EthereumPackageConfig."""

    def test_default_config(self) -> None:
        config = EthereumPackageConfig()
        errors = config.validate()
        assert errors == []

    def test_to_kurtosis_args(self) -> None:
        config = EthereumPackageConfig()
        args = config.to_kurtosis_args()
        assert "participants" in args
        assert len(args["participants"]) > 0
        total = sum(p["count"] for p in args["participants"])
        assert total == 50  # default node count

    def test_kurtosis_args_participant_format(self) -> None:
        config = EthereumPackageConfig(
            client_config=ClientConfig(
                node_count=10,
                execution=ClientDistribution({"nethermind": 0.5, "geth": 0.5}),
                consensus=ClientDistribution({"prysm": 0.5, "lighthouse": 0.5}),
            )
        )
        args = config.to_kurtosis_args()
        for p in args["participants"]:
            assert "el_type" in p
            assert "cl_type" in p
            assert "count" in p
            assert isinstance(p["count"], int)
            assert p["count"] > 0

    def test_kurtosis_args_with_mev(self) -> None:
        config = EthereumPackageConfig(
            mev_config=MEVConfig(enabled=True, relay_type="flashbots"),
        )
        args = config.to_kurtosis_args()
        assert args.get("mev_type") == "flashbots"

    def test_kurtosis_args_with_spammer(self) -> None:
        # Spammer is currently disabled in to_kurtosis_args() for deployment stability.
        # When enabled via additional_services explicitly, it should appear.
        config = EthereumPackageConfig(
            spammer_config=SpammerConfig(enabled=True),
            additional_services=["tx_spammer"],
        )
        args = config.to_kurtosis_args()
        assert "tx_spammer" in args.get("additional_services", [])

    def test_kurtosis_args_without_spammer(self) -> None:
        config = EthereumPackageConfig(
            spammer_config=SpammerConfig(enabled=False),
        )
        args = config.to_kurtosis_args()
        additional = args.get("additional_services", [])
        assert "tx_spammer" not in additional

    def test_from_dict_scenario_format(self) -> None:
        """Test creating config from a scenario YAML network_config section."""
        data = {
            "network_config": {
                "node_count": 100,
                "client_distribution": {
                    "execution": {"nethermind": 0.5, "geth": 0.5},
                    "consensus": {"prysm": 0.5, "lighthouse": 0.5},
                },
                "mev_enabled": True,
                "tx_spammer_tps": 500,
            }
        }
        config = EthereumPackageConfig.from_dict(data)
        assert config.client_config.node_count == 100
        assert config.mev_config.enabled is True
        assert config.spammer_config.tps == 500

    def test_to_dict(self) -> None:
        config = EthereumPackageConfig()
        d = config.to_dict()
        assert "client_config" in d
        assert "fork_config" in d
        assert "mev_config" in d
        assert "spammer_config" in d

    def test_package_url(self) -> None:
        config = EthereumPackageConfig()
        url = config.package_url
        assert ETHEREUM_PACKAGE_URL in url
        # When ETHEREUM_PACKAGE_VERSION is empty, the URL uses main branch
        # (no @version suffix) for compatibility with latest client versions.
        from chaoswopr.infrastructure.testnet.ethereum_package import ETHEREUM_PACKAGE_VERSION
        if ETHEREUM_PACKAGE_VERSION:
            assert "@" in url
        else:
            assert url == ETHEREUM_PACKAGE_URL

    def test_network_params(self) -> None:
        # network_params is currently disabled in to_kurtosis_args() to avoid
        # "devnet URL" errors in ethereum-package. Verify that the network_name
        # is stored on the config and that to_kurtosis_args() does not include
        # network_params (current intentional behavior).
        config = EthereumPackageConfig(network_name="test-net")
        assert config.network_name == "test-net"
        args = config.to_kurtosis_args()
        # network_params is intentionally omitted for deployment stability
        assert "network_params" not in args

    def test_validation_propagates_errors(self) -> None:
        config = EthereumPackageConfig(
            client_config=ClientConfig(node_count=0),
        )
        errors = config.validate()
        assert len(errors) > 0
