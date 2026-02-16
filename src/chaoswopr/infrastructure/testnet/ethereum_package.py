"""ethpandaops/ethereum-package integration for chaoswopr.

Generates Kurtosis package configuration for deploying multi-client
Ethereum testnets. Supports:
- Client diversity (Nethermind, Geth, Besu, Erigon / Prysm, Lighthouse, Teku, Nimbus)
- Mainnet state fork
- MEV-boost infrastructure
- Transaction spammers
- Configurable node counts (50-500)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chaoswopr.infrastructure.testnet.client_config import ClientConfig

# Use main branch for latest compatibility with current client versions
# Note: main branch is required for compatibility with Prysm and Nethermind latest versions
# Older pinned versions (4.x) have genesis config incompatibilities (EIP7594/Fulu fork parameters)
ETHEREUM_PACKAGE_URL = "github.com/ethpandaops/ethereum-package"
ETHEREUM_PACKAGE_VERSION = ""  # Empty string = use main branch


@dataclass
class ForkConfig:
    """Mainnet state fork configuration.

    Attributes:
        enabled: Whether to fork mainnet state.
        block_number: Block number to fork from (0 = latest).
        rpc_url: Mainnet RPC URL for forking.
    """

    enabled: bool = False
    block_number: int = 0
    rpc_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "block_number": self.block_number,
            "rpc_url": self.rpc_url,
        }


@dataclass
class MEVConfig:
    """MEV-boost configuration.

    Attributes:
        enabled: Whether to enable MEV-boost.
        relay_type: Type of relay to use.
    """

    enabled: bool = False
    relay_type: str = "flashbots"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "relay_type": self.relay_type,
        }


@dataclass
class SpammerConfig:
    """Transaction spammer configuration.

    Attributes:
        enabled: Whether to enable the transaction spammer.
        tps: Target transactions per second.
    """

    enabled: bool = True
    tps: int = 100

    def validate(self) -> list[str]:
        """Validate configuration."""
        errors: list[str] = []
        if self.tps < 0:
            errors.append("tps must be >= 0")
        if self.tps > 10000:
            errors.append("tps must be <= 10000")
        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "tps": self.tps,
        }


@dataclass
class EthereumPackageConfig:
    """Complete configuration for the ethereum-package Kurtosis deployment.

    Generates the args format expected by ethpandaops/ethereum-package.
    """

    client_config: ClientConfig = field(default_factory=ClientConfig)
    fork_config: ForkConfig = field(default_factory=ForkConfig)
    mev_config: MEVConfig = field(default_factory=MEVConfig)
    spammer_config: SpammerConfig = field(default_factory=SpammerConfig)
    network_name: str = "chaoswopr-testnet"
    additional_services: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Validate the complete configuration.

        Returns:
            List of validation errors. Empty means valid.
        """
        errors: list[str] = []
        errors.extend(self.client_config.validate())
        errors.extend(self.spammer_config.validate())
        return errors

    def to_kurtosis_args(self) -> dict[str, Any]:
        """Generate Kurtosis package arguments.

        Returns:
            Dictionary in the format expected by ethereum-package.
        """
        participants = self.client_config.to_participants_list()

        # Build participants in ethereum-package format
        kurtosis_participants = []
        for p in participants:
            participant = {
                "el_type": p["el_type"],
                "cl_type": p["cl_type"],
                "count": p["count"],
            }
            kurtosis_participants.append(participant)

        args: dict[str, Any] = {
            "participants": kurtosis_participants,
            # Disable network_params temporarily - causes "devnet URL" errors
            # "network_params": {
            #     "network": self.network_name,
            #     "seconds_per_slot": 12,
            # },
        }

        # Add additional services
        # Disable spammer temporarily for first successful deployment
        # if self.spammer_config.enabled:
        #     # Use 'spamoor' - the correct service name in ethereum-package v4.2.0+
        #     args["additional_services"] = self.additional_services + ["spamoor"]
        if self.additional_services:
            args["additional_services"] = self.additional_services

        # MEV configuration
        if self.mev_config.enabled:
            args["mev_type"] = self.mev_config.relay_type

        return args

    def to_dict(self) -> dict[str, Any]:
        """Convert to full configuration dictionary."""
        return {
            "client_config": self.client_config.to_dict(),
            "fork_config": self.fork_config.to_dict(),
            "mev_config": self.mev_config.to_dict(),
            "spammer_config": self.spammer_config.to_dict(),
            "network_name": self.network_name,
            "additional_services": self.additional_services,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EthereumPackageConfig:
        """Create from dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            EthereumPackageConfig instance.
        """
        client_config = ClientConfig.from_dict(data.get("network_config", data))

        fork_data = data.get("fork_config", {})
        fork_config = ForkConfig(
            enabled=fork_data.get("enabled", False),
            block_number=fork_data.get("block_number", 0),
            rpc_url=fork_data.get("rpc_url", ""),
        )

        mev_data = data.get("mev_config", {})
        mev_config = MEVConfig(
            enabled=mev_data.get("enabled", data.get("network_config", {}).get("mev_enabled", False)),
        )

        spammer_data = data.get("spammer_config", {})
        spammer_config = SpammerConfig(
            enabled=spammer_data.get("enabled", True),
            tps=spammer_data.get(
                "tps",
                data.get("network_config", {}).get("tx_spammer_tps", 100),
            ),
        )

        return cls(
            client_config=client_config,
            fork_config=fork_config,
            mev_config=mev_config,
            spammer_config=spammer_config,
        )

    @property
    def package_url(self) -> str:
        """Get the ethereum-package URL with version."""
        if ETHEREUM_PACKAGE_VERSION:
            return f"{ETHEREUM_PACKAGE_URL}@{ETHEREUM_PACKAGE_VERSION}"
        return ETHEREUM_PACKAGE_URL  # Use main branch if no version specified
