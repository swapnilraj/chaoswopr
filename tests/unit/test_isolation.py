"""Unit tests for network isolation validation."""

from __future__ import annotations

import pytest

from chaoswopr.safety.isolation import (
    MAINNET_ENDPOINTS,
    PUBLIC_DNS_SERVERS,
    IsolationConfig,
    IsolationRule,
    IsolationCheckResult,
    _is_internal_ip,
    validate_isolation_config,
)


class TestIsolationRule:
    """Tests for IsolationRule."""

    def test_create_rule(self) -> None:
        rule = IsolationRule(
            name="block_mainnet",
            rule_type="block_egress",
            target="mainnet.infura.io",
        )
        assert rule.name == "block_mainnet"
        assert rule.enabled is True

    def test_rule_to_dict(self) -> None:
        rule = IsolationRule(
            name="test",
            rule_type="block_egress",
            target="example.com",
        )
        d = rule.to_dict()
        assert d["name"] == "test"
        assert d["enabled"] is True


class TestIsolationConfig:
    """Tests for IsolationConfig."""

    def test_default_config(self) -> None:
        config = IsolationConfig()
        assert config.block_external_egress is True
        assert config.block_mainnet_endpoints is True
        assert config.block_public_dns is True
        assert len(config.rules) > 0

    def test_default_rules_generated(self) -> None:
        config = IsolationConfig()
        rule_names = [r.name for r in config.rules]
        assert "block_all_egress" in rule_names
        assert "allow_internal" in rule_names

    def test_mainnet_endpoints_blocked(self) -> None:
        config = IsolationConfig()
        blocked = config.get_blocked_hosts()
        for endpoint in MAINNET_ENDPOINTS:
            assert endpoint in blocked

    def test_public_dns_blocked(self) -> None:
        config = IsolationConfig()
        blocked = config.get_blocked_hosts()
        for dns in PUBLIC_DNS_SERVERS:
            assert dns in blocked

    @pytest.mark.safety
    def test_mainnet_host_not_allowed(self) -> None:
        """SAFETY: Mainnet endpoints must be blocked."""
        config = IsolationConfig()
        for endpoint in MAINNET_ENDPOINTS:
            assert not config.is_host_allowed(endpoint), f"{endpoint} should be blocked"

    @pytest.mark.safety
    def test_public_dns_not_allowed(self) -> None:
        """SAFETY: Public DNS servers must be blocked."""
        config = IsolationConfig()
        for dns in PUBLIC_DNS_SERVERS:
            assert not config.is_host_allowed(dns), f"{dns} should be blocked"

    def test_internal_ip_allowed(self) -> None:
        config = IsolationConfig()
        assert config.is_host_allowed("10.0.0.1")
        assert config.is_host_allowed("192.168.1.1")
        assert config.is_host_allowed("172.16.0.1")

    def test_explicit_allowlist(self) -> None:
        config = IsolationConfig(allowed_external_hosts=["pypi.org"])
        assert config.is_host_allowed("pypi.org")

    def test_external_host_blocked(self) -> None:
        config = IsolationConfig()
        assert not config.is_host_allowed("google.com")
        assert not config.is_host_allowed("203.0.113.1")

    def test_config_to_dict(self) -> None:
        config = IsolationConfig()
        d = config.to_dict()
        assert d["block_external_egress"] is True
        assert "rules" in d
        assert len(d["rules"]) > 0

    @pytest.mark.safety
    def test_mainnet_in_allowlist_detected(self) -> None:
        """SAFETY: Mainnet endpoints in allowlist must be detected by validation."""
        config = IsolationConfig(
            allowed_external_hosts=["mainnet.infura.io"]
        )
        result = validate_isolation_config(config)
        assert not result.passed
        assert any("mainnet" in v.lower() for v in result.violations)


class TestIsInternalIP:
    """Tests for the internal IP checker."""

    def test_class_a_private(self) -> None:
        assert _is_internal_ip("10.0.0.1") is True
        assert _is_internal_ip("10.255.255.255") is True

    def test_class_b_private(self) -> None:
        assert _is_internal_ip("172.16.0.1") is True
        assert _is_internal_ip("172.31.255.255") is True

    def test_class_c_private(self) -> None:
        assert _is_internal_ip("192.168.0.1") is True
        assert _is_internal_ip("192.168.255.255") is True

    def test_loopback(self) -> None:
        assert _is_internal_ip("127.0.0.1") is True
        assert _is_internal_ip("localhost") is True

    def test_public_ip(self) -> None:
        assert _is_internal_ip("8.8.8.8") is False
        assert _is_internal_ip("203.0.113.1") is False


class TestValidateIsolationConfig:
    """Tests for the isolation configuration validator."""

    def test_valid_config_passes(self) -> None:
        config = IsolationConfig()
        result = validate_isolation_config(config)
        assert result.passed
        assert result.checks_performed > 0
        assert len(result.violations) == 0

    def test_egress_not_blocked_fails(self) -> None:
        config = IsolationConfig(block_external_egress=False)
        result = validate_isolation_config(config)
        assert not result.passed
        assert any("egress" in v.lower() for v in result.violations)

    def test_mainnet_not_blocked_fails(self) -> None:
        config = IsolationConfig(block_mainnet_endpoints=False)
        result = validate_isolation_config(config)
        assert not result.passed
        assert any("mainnet" in v.lower() for v in result.violations)

    def test_result_has_details(self) -> None:
        config = IsolationConfig()
        result = validate_isolation_config(config)
        assert "rule_count" in result.details
        assert result.details["rule_count"] > 0
