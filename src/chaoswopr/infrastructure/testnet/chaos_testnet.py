"""Chaos-enabled testnet deployment with NET_ADMIN capabilities.

This module provides a wrapper around standard testnet deployment that uses
a patched version of ethereum-package with NET_ADMIN capability enabled.

The standard ethereum-package doesn't include NET_ADMIN by default for security,
but chaos testing requires it for network fault injection via tc/netem.

To use this deployer:
1. Run scripts/patch_ethereum_package.sh to create a patched version
2. Set use_patched_package=True when deploying
3. The deployer will use the local patched package with NET_ADMIN enabled
"""

from __future__ import annotations

import os
from pathlib import Path

from chaoswopr.infrastructure.testnet.deployer import (
    DeploymentResult,
    TestnetDeployer,
)
from chaoswopr.infrastructure.testnet.ethereum_package import (
    ETHEREUM_PACKAGE_URL,
    EthereumPackageConfig,
)
from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient


class ChaosTestnetDeployer(TestnetDeployer):
    """Testnet deployer with NET_ADMIN capability for chaos injection.

    This deployer uses a patched version of ethereum-package that includes
    NET_ADMIN capability in all service configurations. This enables tc/netem
    network fault injection for chaos engineering.

    The patched package is created by scripts/patch_ethereum_package.sh and
    stored in kurtosis-packages/ethereum-package-patched/.
    """

    def __init__(
        self,
        kurtosis_client: KurtosisClient | None = None,
        package_config: EthereumPackageConfig | None = None,
        enclave_name: str = "chaoswopr-testnet",
        use_patched_package: bool = True,
    ) -> None:
        """Initialize chaos-enabled deployer.

        Args:
            kurtosis_client: Kurtosis client instance.
            package_config: ethereum-package configuration.
            enclave_name: Name for the Kurtosis enclave.
            use_patched_package: If True, use local patched package with NET_ADMIN.
        """
        super().__init__(kurtosis_client, package_config, enclave_name)
        self._use_patched_package = use_patched_package

    def _get_package_url(self) -> str:
        """Get the package URL to use for deployment.

        Returns:
            Package URL or path (local path if using patched package).
        """
        if self._use_patched_package:
            # Use local patched package
            repo_root = Path(__file__).parent.parent.parent.parent.parent
            patched_dir = repo_root / "kurtosis-packages" / "ethereum-package-patched"

            if patched_dir.exists():
                return str(patched_dir)
            else:
                # Patched package not found, fall back to upstream and warn
                print(f"WARNING: Patched ethereum-package not found at {patched_dir}")
                print("         Run scripts/patch_ethereum_package.sh to create it")
                print("         Falling back to upstream package (NET_ADMIN not enabled)")
                return self._package_config.package_url
        else:
            return self._package_config.package_url

    def deploy(
        self,
        wait_for_finality: bool = True,
        finality_timeout_seconds: int = 600,
    ) -> DeploymentResult:
        """Deploy testnet with NET_ADMIN capability.

        If use_patched_package=True, this uses a local patched version of
        ethereum-package with NET_ADMIN capability enabled at service creation time.

        Args:
            wait_for_finality: Whether to wait for network finality.
            finality_timeout_seconds: Max time to wait for finality.

        Returns:
            DeploymentResult with deployment outcome.
        """
        # Override package URL if using patched version
        if self._use_patched_package:
            original_url = self._package_config._package_url if hasattr(self._package_config, '_package_url') else None
            package_url = self._get_package_url()

            # Temporarily override the package URL
            # (This is a bit hacky, but avoids modifying the config)
            if hasattr(self._package_config, '_package_url'):
                self._package_config._package_url = package_url

        # Deploy using parent method
        result = super().deploy(wait_for_finality, finality_timeout_seconds)

        # Restore original URL if we overrode it
        if self._use_patched_package and original_url:
            if hasattr(self._package_config, '_package_url'):
                self._package_config._package_url = original_url

        # Add note about NET_ADMIN in result message
        if result.success and self._use_patched_package:
            if not result.message:
                result.message = ""
            result.message += "\nNET_ADMIN capability enabled for chaos injection"

        return result


def create_chaos_testnet(
    node_count: int = 4,
    enclave_name: str = "chaoswopr-chaos-test",
    dry_run: bool = False,
    use_patched_package: bool = True,
) -> tuple[ChaosTestnetDeployer, DeploymentResult]:
    """Create a chaos-enabled testnet with NET_ADMIN capabilities.

    Convenience function for creating testnets suitable for chaos injection testing.

    This function uses a patched version of ethereum-package with NET_ADMIN
    capability enabled. Run scripts/patch_ethereum_package.sh first to create
    the patched package.

    Args:
        node_count: Number of validator nodes to deploy.
        enclave_name: Name for the Kurtosis enclave.
        dry_run: If True, don't actually deploy (for testing).
        use_patched_package: If True, use local patched package with NET_ADMIN.

    Returns:
        Tuple of (deployer, deployment_result).

    Example:
        >>> # First, create the patched package:
        >>> # $ ./scripts/patch_ethereum_package.sh
        >>> deployer, result = create_chaos_testnet(node_count=4)
        >>> if result.success:
        ...     # Ready for chaos injection with NET_ADMIN enabled
        ...     pass
    """
    from chaoswopr.infrastructure.testnet.client_config import (
        ClientConfig,
        ClientDistribution,
    )

    client = KurtosisClient(dry_run=dry_run)

    # Use Nethermind (EL) + Prysm (CL) as they're well-tested
    config = EthereumPackageConfig(
        client_config=ClientConfig(
            node_count=node_count,
            execution=ClientDistribution({"nethermind": 1.0}),
            consensus=ClientDistribution({"prysm": 1.0}),
        ),
    )

    deployer = ChaosTestnetDeployer(
        kurtosis_client=client,
        package_config=config,
        enclave_name=enclave_name,
        use_patched_package=use_patched_package,
    )

    result = deployer.deploy(wait_for_finality=False)

    return deployer, result
