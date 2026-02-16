"""Reproducible testnet deployment script for chaoswopr.

Wraps the full deployment in a single CLI command (make testnet-up).
Orchestrates:
1. Kurtosis enclave creation
2. ethereum-package deployment with client diversity
3. Health check and finality verification via Beacon API
4. Service discovery and port mapping

Supports seed-based determinism where possible.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import click

from chaoswopr.infrastructure.testnet.beacon_api import (
    BeaconAPIClient,
    FinalityWaitResult,
)
from chaoswopr.infrastructure.testnet.ethereum_package import EthereumPackageConfig
from chaoswopr.infrastructure.testnet.kurtosis_client import (
    EnclaveInfo,
    KurtosisBackend,
    KurtosisClient,
    ServiceInfo,
)

logger = logging.getLogger(__name__)


class DeploymentState(str, Enum):
    """State of a testnet deployment."""

    NOT_STARTED = "not_started"
    CREATING_ENCLAVE = "creating_enclave"
    DEPLOYING_PACKAGE = "deploying_package"
    WAITING_FOR_FINALITY = "waiting_for_finality"
    RUNNING = "running"
    TEARING_DOWN = "tearing_down"
    DESTROYED = "destroyed"
    FAILED = "failed"


@dataclass
class DeploymentResult:
    """Result of a testnet deployment."""

    state: DeploymentState
    enclave_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    services: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    finality_achieved: bool = False
    finality_epoch: int | None = None
    finality_wait_seconds: float = 0.0
    beacon_endpoints: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if deployment succeeded."""
        return self.state == DeploymentState.RUNNING

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "state": self.state.value,
            "enclave_name": self.enclave_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "services": self.services,
            "error_message": self.error_message,
            "finality_achieved": self.finality_achieved,
            "finality_epoch": self.finality_epoch,
            "finality_wait_seconds": self.finality_wait_seconds,
            "beacon_endpoints": self.beacon_endpoints,
        }


class TestnetDeployer:
    """Orchestrates testnet deployment and lifecycle management.

    Provides a high-level API for deploying, checking, and tearing down
    Ethereum testnets using Kurtosis and ethpandaops/ethereum-package.
    Includes real finality verification via the Beacon API.
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(
        self,
        kurtosis_client: KurtosisClient | None = None,
        package_config: EthereumPackageConfig | None = None,
        enclave_name: str = "chaoswopr-testnet",
    ) -> None:
        """Initialize the deployer.

        Args:
            kurtosis_client: Kurtosis client instance.
            package_config: ethereum-package configuration.
            enclave_name: Name for the Kurtosis enclave.
        """
        self._kurtosis = kurtosis_client or KurtosisClient(dry_run=True)
        self._config = package_config or EthereumPackageConfig()
        self._enclave_name = enclave_name
        self._state = DeploymentState.NOT_STARTED
        self._deployment_result: DeploymentResult | None = None
        self._beacon_clients: list[BeaconAPIClient] = []

    @property
    def state(self) -> DeploymentState:
        """Get the current deployment state."""
        return self._state

    @property
    def enclave_name(self) -> str:
        """Get the enclave name."""
        return self._enclave_name

    @property
    def config(self) -> EthereumPackageConfig:
        """Get the package configuration."""
        return self._config

    @property
    def beacon_clients(self) -> list[BeaconAPIClient]:
        """Get the beacon API clients discovered from the enclave."""
        return self._beacon_clients

    def _discover_beacon_endpoints(self) -> list[str]:
        """Discover beacon node API endpoints from the Kurtosis enclave.

        Inspects the enclave services to find CL nodes and extract their
        HTTP API endpoints.

        Returns:
            List of beacon API URLs (e.g. http://127.0.0.1:32771).
        """
        if self._kurtosis.dry_run:
            return []

        beacon_services = self._kurtosis.find_beacon_services(self._enclave_name)
        endpoints: list[str] = []

        for svc in beacon_services:
            # Look for the HTTP API port (typically named 'http' or 'beacon')
            for port_name in ["http", "beacon", "rest", "api"]:
                url = svc.get_url(port_name)
                if url:
                    endpoints.append(url)
                    break

        logger.info("Discovered %d beacon endpoints", len(endpoints))
        return endpoints

    def _wait_for_finality(
        self,
        result: DeploymentResult,
        timeout_seconds: int = 300,
        node_ready_timeout: float = 120.0,
    ) -> None:
        """Wait for the network to achieve finality using real Beacon API.

        Discovers beacon node endpoints from the enclave, waits for
        at least one node to be ready, then polls finality checkpoints.

        Args:
            result: DeploymentResult to update with finality info.
            timeout_seconds: Maximum time to wait for finality.
            node_ready_timeout: Maximum time to wait for beacon node readiness.
        """
        if self._kurtosis.dry_run:
            # In dry-run mode, simulate success
            result.finality_achieved = True
            result.finality_epoch = 0
            return

        endpoints = self._discover_beacon_endpoints()
        result.beacon_endpoints = endpoints

        if not endpoints:
            logger.warning("No beacon endpoints discovered, skipping finality wait")
            result.finality_achieved = False
            result.error_message = "No beacon endpoints discovered"
            return

        # Create beacon clients and try each endpoint
        self._beacon_clients = [BeaconAPIClient(base_url=ep) for ep in endpoints]

        # Wait for at least one beacon node to be ready
        ready_client: BeaconAPIClient | None = None
        for client in self._beacon_clients:
            logger.info("Waiting for beacon node at %s...", client.base_url)
            if client.wait_for_node_ready(
                timeout_seconds=node_ready_timeout,
                poll_interval=5.0,
            ):
                ready_client = client
                break

        if not ready_client:
            result.finality_achieved = False
            result.error_message = (
                f"No beacon node became ready within {node_ready_timeout}s"
            )
            return

        # Poll for finality
        logger.info("Waiting for finality (timeout=%ds)...", timeout_seconds)
        finality_result = ready_client.wait_for_finality(
            timeout_seconds=float(timeout_seconds),
            poll_interval=12.0,
            min_finalized_epoch=1,
        )

        result.finality_achieved = finality_result.achieved
        result.finality_epoch = finality_result.finality_epoch
        result.finality_wait_seconds = finality_result.wait_seconds

        if not finality_result.achieved:
            result.error_message = finality_result.error

    def deploy(
        self,
        wait_for_finality: bool = True,
        finality_timeout_seconds: int = 600,
    ) -> DeploymentResult:
        """Deploy the Ethereum testnet.

        Args:
            wait_for_finality: Whether to wait for the network to reach finality.
            finality_timeout_seconds: Maximum time to wait for finality.

        Returns:
            DeploymentResult with deployment outcome.
        """
        result = DeploymentResult(
            state=DeploymentState.CREATING_ENCLAVE,
            enclave_name=self._enclave_name,
            config=self._config.to_dict(),
        )

        try:
            # Validate configuration
            errors = self._config.validate()
            if errors:
                result.state = DeploymentState.FAILED
                result.error_message = f"Configuration errors: {'; '.join(errors)}"
                self._state = DeploymentState.FAILED
                self._deployment_result = result
                return result

            # Step 1: Create enclave
            self._state = DeploymentState.CREATING_ENCLAVE
            result.state = DeploymentState.CREATING_ENCLAVE
            self._kurtosis.create_enclave(self._enclave_name)

            # Step 2: Deploy package
            self._state = DeploymentState.DEPLOYING_PACKAGE
            result.state = DeploymentState.DEPLOYING_PACKAGE
            kurtosis_args = self._config.to_kurtosis_args()
            self._kurtosis.run_package(
                self._enclave_name,
                self._config.package_url,
                args=kurtosis_args,
            )

            # Step 3: Wait for finality (if requested)
            if wait_for_finality:
                self._state = DeploymentState.WAITING_FOR_FINALITY
                result.state = DeploymentState.WAITING_FOR_FINALITY
                self._wait_for_finality(result, finality_timeout_seconds)

            # Step 4: Success
            self._state = DeploymentState.RUNNING
            result.state = DeploymentState.RUNNING
            result.completed_at = datetime.now(timezone.utc)
            result.duration_seconds = (
                result.completed_at - result.started_at
            ).total_seconds()

        except Exception as e:
            result.state = DeploymentState.FAILED
            result.error_message = str(e)
            self._state = DeploymentState.FAILED

        self._deployment_result = result
        return result

    def destroy(self) -> bool:
        """Tear down the testnet.

        Returns:
            True if teardown succeeded.
        """
        self._state = DeploymentState.TEARING_DOWN

        # Close beacon clients
        for client in self._beacon_clients:
            try:
                client.close()
            except Exception:
                pass
        self._beacon_clients = []

        try:
            ok = self._kurtosis.destroy_enclave(self._enclave_name)
            if ok:
                self._state = DeploymentState.DESTROYED
            else:
                self._state = DeploymentState.FAILED
            return ok
        except Exception:
            self._state = DeploymentState.FAILED
            return False

    def status(self) -> dict[str, Any]:
        """Get the current deployment status.

        Returns:
            Dictionary with deployment state and details.
        """
        result: dict[str, Any] = {
            "state": self._state.value,
            "enclave_name": self._enclave_name,
            "config": self._config.to_dict(),
        }

        if self._deployment_result:
            result["deployment"] = self._deployment_result.to_dict()

        # Try to get enclave info
        if self._state == DeploymentState.RUNNING:
            info = self._kurtosis.get_enclave_info(self._enclave_name)
            if info:
                result["enclave_info"] = info.to_dict()

        return result

    def get_last_deployment(self) -> DeploymentResult | None:
        """Get the result of the last deployment attempt."""
        return self._deployment_result


@click.group()
def cli() -> None:
    """Testnet deployment management."""


@cli.command()
@click.option("--nodes", default=50, help="Number of nodes")
@click.option("--name", default="chaoswopr-testnet", help="Enclave name")
@click.option("--no-wait", is_flag=True, help="Don't wait for finality")
@click.option("--dry-run", is_flag=True, help="Dry run mode")
def up(nodes: int, name: str, no_wait: bool, dry_run: bool) -> None:
    """Launch the Ethereum testnet."""
    client = KurtosisClient(dry_run=dry_run)

    from chaoswopr.infrastructure.testnet.client_config import ClientConfig

    config = EthereumPackageConfig(
        client_config=ClientConfig(node_count=nodes),
    )

    deployer = TestnetDeployer(
        kurtosis_client=client,
        package_config=config,
        enclave_name=name,
    )

    click.echo(f"Deploying {nodes}-node testnet as '{name}'...")
    result = deployer.deploy(wait_for_finality=not no_wait)

    if result.success:
        click.echo(f"Testnet deployed successfully in {result.duration_seconds:.1f}s")
        if result.finality_achieved:
            click.echo(f"Finality achieved at epoch {result.finality_epoch}")
    else:
        click.echo(f"Deployment failed: {result.error_message}")
        sys.exit(1)


@cli.command()
@click.option("--name", default="chaoswopr-testnet", help="Enclave name")
@click.option("--dry-run", is_flag=True, help="Dry run mode")
def down(name: str, dry_run: bool) -> None:
    """Tear down the Ethereum testnet."""
    client = KurtosisClient(dry_run=dry_run)
    deployer = TestnetDeployer(kurtosis_client=client, enclave_name=name)

    click.echo(f"Tearing down testnet '{name}'...")
    if deployer.destroy():
        click.echo("Testnet destroyed.")
    else:
        click.echo("Failed to destroy testnet.")
        sys.exit(1)


@cli.command()
@click.option("--name", default="chaoswopr-testnet", help="Enclave name")
@click.option("--dry-run", is_flag=True, help="Dry run mode")
def status(name: str, dry_run: bool) -> None:
    """Check testnet status."""
    client = KurtosisClient(dry_run=dry_run)
    deployer = TestnetDeployer(kurtosis_client=client, enclave_name=name)
    info = deployer.status()
    click.echo(f"State: {info['state']}")
    click.echo(f"Enclave: {info['enclave_name']}")


def main() -> None:
    """Entry point for the deployer CLI."""
    cli()


if __name__ == "__main__":
    main()
