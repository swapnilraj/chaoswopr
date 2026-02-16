"""Network isolation validation for chaoswopr testnets.

Ensures that the testnet enclave cannot make external network calls
(no mainnet RPC, no public DNS). Enforced via Kurtosis network policies
or iptables rules.

This is a safety-critical module: testnets must NEVER contact mainnet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Known Ethereum mainnet endpoints that must be blocked
MAINNET_ENDPOINTS = [
    "mainnet.infura.io",
    "eth-mainnet.g.alchemy.com",
    "rpc.ankr.com",
    "cloudflare-eth.com",
    "api.etherscan.io",
    "beaconcha.in",
]

# Known DNS servers that should be blocked (or restricted to internal)
PUBLIC_DNS_SERVERS = [
    "8.8.8.8",
    "8.8.4.4",
    "1.1.1.1",
    "1.0.0.1",
]


@dataclass
class IsolationRule:
    """A network isolation rule."""

    name: str
    rule_type: str  # "block_egress", "block_dns", "allow_internal"
    target: str
    enabled: bool = True
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "rule_type": self.rule_type,
            "target": self.target,
            "enabled": self.enabled,
            "description": self.description,
        }


@dataclass
class IsolationConfig:
    """Configuration for testnet network isolation.

    Attributes:
        block_external_egress: Block all outbound traffic to external networks.
        block_mainnet_endpoints: Block known mainnet RPC endpoints.
        block_public_dns: Block public DNS servers.
        allowed_external_hosts: Exceptions for specific external hosts.
        rules: List of explicit isolation rules.
    """

    block_external_egress: bool = True
    block_mainnet_endpoints: bool = True
    block_public_dns: bool = True
    allowed_external_hosts: list[str] = field(default_factory=list)
    rules: list[IsolationRule] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Generate default rules if none specified."""
        if not self.rules:
            self.rules = self._generate_default_rules()

    def _generate_default_rules(self) -> list[IsolationRule]:
        """Generate default isolation rules based on config."""
        rules: list[IsolationRule] = []

        if self.block_external_egress:
            rules.append(
                IsolationRule(
                    name="block_all_egress",
                    rule_type="block_egress",
                    target="0.0.0.0/0",
                    description="Block all external egress traffic",
                )
            )

        if self.block_mainnet_endpoints:
            for endpoint in MAINNET_ENDPOINTS:
                rules.append(
                    IsolationRule(
                        name=f"block_{endpoint.replace('.', '_')}",
                        rule_type="block_egress",
                        target=endpoint,
                        description=f"Block mainnet endpoint: {endpoint}",
                    )
                )

        if self.block_public_dns:
            for dns in PUBLIC_DNS_SERVERS:
                rules.append(
                    IsolationRule(
                        name=f"block_dns_{dns.replace('.', '_')}",
                        rule_type="block_dns",
                        target=dns,
                        description=f"Block public DNS: {dns}",
                    )
                )

        # Allow internal communication
        rules.append(
            IsolationRule(
                name="allow_internal",
                rule_type="allow_internal",
                target="10.0.0.0/8",
                description="Allow internal network communication",
            )
        )

        return rules

    def get_blocked_hosts(self) -> list[str]:
        """Get list of all blocked hosts/IPs."""
        blocked = []
        if self.block_mainnet_endpoints:
            blocked.extend(MAINNET_ENDPOINTS)
        if self.block_public_dns:
            blocked.extend(PUBLIC_DNS_SERVERS)
        return blocked

    def is_host_allowed(self, host: str) -> bool:
        """Check if a host is allowed by the isolation config.

        Args:
            host: Hostname or IP to check.

        Returns:
            True if the host is allowed, False if blocked.
        """
        # Check explicit allowlist
        if host in self.allowed_external_hosts:
            return True

        # Check against blocked endpoints
        if self.block_mainnet_endpoints and host in MAINNET_ENDPOINTS:
            return False

        # Check against blocked DNS
        if self.block_public_dns and host in PUBLIC_DNS_SERVERS:
            return False

        # If external egress is blocked, only internal IPs are allowed
        if self.block_external_egress:
            return _is_internal_ip(host)

        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "block_external_egress": self.block_external_egress,
            "block_mainnet_endpoints": self.block_mainnet_endpoints,
            "block_public_dns": self.block_public_dns,
            "allowed_external_hosts": self.allowed_external_hosts,
            "rules": [r.to_dict() for r in self.rules],
        }


def _is_internal_ip(host: str) -> bool:
    """Check if a host is an internal/private IP address.

    Args:
        host: IP address or hostname to check.

    Returns:
        True if the IP is internal/private.
    """
    internal_prefixes = [
        "10.",
        "172.16.", "172.17.", "172.18.", "172.19.",
        "172.20.", "172.21.", "172.22.", "172.23.",
        "172.24.", "172.25.", "172.26.", "172.27.",
        "172.28.", "172.29.", "172.30.", "172.31.",
        "192.168.",
        "127.",
        "localhost",
    ]
    return any(host.startswith(prefix) for prefix in internal_prefixes)


@dataclass
class IsolationCheckResult:
    """Result of an isolation validation check."""

    passed: bool
    checks_performed: int = 0
    violations: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def validate_isolation_config(config: IsolationConfig) -> IsolationCheckResult:
    """Validate that an isolation configuration is properly defined.

    Args:
        config: The isolation configuration to validate.

    Returns:
        IsolationCheckResult with validation results.
    """
    result = IsolationCheckResult(passed=True)

    # Check that external egress is blocked
    result.checks_performed += 1
    if not config.block_external_egress:
        result.violations.append("External egress is not blocked")
        result.passed = False

    # Check that mainnet endpoints are blocked
    result.checks_performed += 1
    if not config.block_mainnet_endpoints:
        result.violations.append("Mainnet endpoints are not blocked")
        result.passed = False

    # Check that no mainnet endpoints are in the allowlist
    result.checks_performed += 1
    for host in config.allowed_external_hosts:
        if host in MAINNET_ENDPOINTS:
            result.violations.append(
                f"Mainnet endpoint {host} is in the allowed hosts list"
            )
            result.passed = False

    # Verify rules are generated
    result.checks_performed += 1
    if not config.rules:
        result.violations.append("No isolation rules defined")
        result.passed = False

    result.details = {
        "rule_count": len(config.rules),
        "blocked_hosts": len(config.get_blocked_hosts()),
        "allowed_hosts": len(config.allowed_external_hosts),
    }

    return result
