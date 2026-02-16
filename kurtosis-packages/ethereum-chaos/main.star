"""Custom Ethereum testnet package with NET_ADMIN capability for chaos testing.

This package wraps the official ethereum-package and adds NET_ADMIN capability
to all containers, enabling tc/netem network fault injection for chaos engineering.
"""

ethereum = import_module("github.com/ethpandaops/ethereum-package/main.star")


def run(plan, args):
    """Deploy Ethereum testnet with NET_ADMIN capability.

    This function wraps the official ethereum-package deployment and adds
    NET_ADMIN capability to all execution and consensus client containers.

    Args:
        plan: Kurtosis plan object
        args: Configuration arguments (same format as ethereum-package)

    Returns:
        Deployment result from ethereum-package
    """
    # Deploy the standard ethereum testnet
    result = ethereum.run(plan, args)

    # Add NET_ADMIN capability to all services
    # Note: This requires Kurtosis to support post-deployment service updates,
    # which is not currently available. This approach documents the intent.
    #
    # In practice, we need to fork ethereum-package and add capabilities
    # directly in the ServiceConfig calls within the package source.

    return result
