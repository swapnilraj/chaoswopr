"""Unit tests for Node Agent architecture and base functionality.

Tests the NodeAgent base class, mode switching, and sidecar pattern integration.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from chaoswopr.agents.node_agent import (
    AgentMode,
    BeaconAPIProxy,
    NodeAgent,
    NodeAgentConfig,
    NodeAgentStatus,
)


class TestNodeAgentConfig:
    """Test NodeAgent configuration."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = NodeAgentConfig(
            node_id="validator-1",
            beacon_api_url="http://localhost:5052",
        )
        assert config.node_id == "validator-1"
        assert config.beacon_api_url == "http://localhost:5052"
        assert config.mode == AgentMode.HONEST
        assert config.proxy_port == 5053
        assert config.audit_logging is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = NodeAgentConfig(
            node_id="validator-2",
            beacon_api_url="http://localhost:5052",
            mode=AgentMode.ADVERSARIAL,
            proxy_port=6000,
            audit_logging=False,
        )
        assert config.mode == AgentMode.ADVERSARIAL
        assert config.proxy_port == 6000
        assert config.audit_logging is False


class TestAgentMode:
    """Test agent mode enum."""

    def test_mode_values(self) -> None:
        """Test mode enum values."""
        assert AgentMode.HONEST.value == "honest"
        assert AgentMode.ADVERSARIAL.value == "adversarial"


class TestBeaconAPIProxy:
    """Test Beacon API proxy functionality."""

    def test_proxy_creation(self) -> None:
        """Test proxy creation."""
        proxy = BeaconAPIProxy(
            upstream_url="http://localhost:5052",
            listen_port=5053,
        )
        assert proxy.upstream_url == "http://localhost:5052"
        assert proxy.listen_port == 5053
        assert proxy.is_running is False

    def test_proxy_start_stop(self) -> None:
        """Test proxy start and stop (dry-run mode)."""
        proxy = BeaconAPIProxy(
            upstream_url="http://localhost:5052",
            listen_port=5053,
            dry_run=True,
        )

        # Start proxy
        proxy.start()
        assert proxy.is_running is True

        # Stop proxy
        proxy.stop()
        assert proxy.is_running is False

    def test_proxy_intercept_request(self) -> None:
        """Test request interception."""
        proxy = BeaconAPIProxy(
            upstream_url="http://localhost:5052",
            listen_port=5053,
            dry_run=True,
        )

        # Register an interceptor
        interceptor = MagicMock(return_value={"modified": True})
        proxy.register_interceptor("/eth/v1/validator/duties/attester", interceptor)

        # Simulate a request
        result = proxy._intercept_request(
            "/eth/v1/validator/duties/attester/123",
            {"slot": "123"},
        )

        assert result == {"modified": True}
        interceptor.assert_called_once()

    def test_proxy_passthrough(self) -> None:
        """Test passthrough for non-intercepted requests."""
        proxy = BeaconAPIProxy(
            upstream_url="http://localhost:5052",
            listen_port=5053,
            dry_run=True,
        )

        # No interceptor registered, should passthrough
        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"data": "original"}
            mock_get.return_value.status_code = 200

            result = proxy._intercept_request("/eth/v1/node/health", {})

            # In dry-run mode, returns None for passthrough
            assert result is None


class TestNodeAgent:
    """Test NodeAgent base functionality."""

    def test_agent_creation(self) -> None:
        """Test agent creation."""
        config = NodeAgentConfig(
            node_id="validator-1",
            beacon_api_url="http://localhost:5052",
        )
        agent = NodeAgent(config=config)

        assert agent.node_id == "validator-1"
        assert agent.mode == AgentMode.HONEST
        assert agent.status == NodeAgentStatus.STOPPED

    def test_agent_start_stop(self) -> None:
        """Test agent start and stop."""
        config = NodeAgentConfig(
            node_id="validator-1",
            beacon_api_url="http://localhost:5052",
        )
        agent = NodeAgent(config=config, dry_run=True)

        # Start agent
        agent.start()
        assert agent.status == NodeAgentStatus.RUNNING
        assert agent.proxy.is_running is True

        # Stop agent
        agent.stop()
        assert agent.status == NodeAgentStatus.STOPPED
        assert agent.proxy.is_running is False

    def test_agent_mode_switching(self) -> None:
        """Test switching between honest and adversarial modes."""
        config = NodeAgentConfig(
            node_id="validator-1",
            beacon_api_url="http://localhost:5052",
        )
        agent = NodeAgent(config=config, dry_run=True)

        # Start in honest mode
        agent.start()
        assert agent.mode == AgentMode.HONEST

        # Switch to adversarial
        agent.switch_mode(AgentMode.ADVERSARIAL)
        assert agent.mode == AgentMode.ADVERSARIAL

        # Switch back to honest
        agent.switch_mode(AgentMode.HONEST)
        assert agent.mode == AgentMode.HONEST

    def test_agent_get_status(self) -> None:
        """Test getting agent status."""
        config = NodeAgentConfig(
            node_id="validator-1",
            beacon_api_url="http://localhost:5052",
        )
        agent = NodeAgent(config=config, dry_run=True)

        status = agent.get_status()

        assert status["node_id"] == "validator-1"
        assert status["mode"] == AgentMode.HONEST.value
        assert status["status"] == NodeAgentStatus.STOPPED.value
        assert status["proxy_running"] is False
        assert "uptime_seconds" in status

    def test_agent_with_audit_logging(self) -> None:
        """Test agent with audit logging enabled."""
        from chaoswopr.safety.audit import AuditLogger

        audit_logger = AuditLogger(default_agent_id="validator-1")
        config = NodeAgentConfig(
            node_id="validator-1",
            beacon_api_url="http://localhost:5052",
            audit_logging=True,
        )
        agent = NodeAgent(config=config, audit_logger=audit_logger, dry_run=True)

        # Start agent (should log)
        agent.start()

        # Check audit log
        entries = audit_logger.get_entries(agent_id="validator-1")
        assert len(entries) > 0
        assert any(e.action_type == "node_agent_start" for e in entries)

        # Switch mode (should log)
        agent.switch_mode(AgentMode.ADVERSARIAL)
        entries = audit_logger.get_entries(agent_id="validator-1")
        assert any(e.action_type == "node_agent_mode_switch" for e in entries)

    def test_agent_mode_switching_while_stopped(self) -> None:
        """Test that mode switching works when agent is stopped."""
        config = NodeAgentConfig(
            node_id="validator-1",
            beacon_api_url="http://localhost:5052",
        )
        agent = NodeAgent(config=config, dry_run=True)

        # Switch mode while stopped
        agent.switch_mode(AgentMode.ADVERSARIAL)
        assert agent.mode == AgentMode.ADVERSARIAL
        assert agent.status == NodeAgentStatus.STOPPED

    def test_agent_uptime_tracking(self) -> None:
        """Test agent uptime tracking."""
        config = NodeAgentConfig(
            node_id="validator-1",
            beacon_api_url="http://localhost:5052",
        )
        agent = NodeAgent(config=config, dry_run=True)

        # Start agent
        agent.start()
        time.sleep(0.1)  # Wait a bit

        status = agent.get_status()
        assert status["uptime_seconds"] > 0

        # Stop and restart
        agent.stop()
        agent.start()

        # Uptime should reset
        status = agent.get_status()
        assert status["uptime_seconds"] < 1.0


class TestNodeAgentStatus:
    """Test NodeAgent status enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert NodeAgentStatus.STOPPED.value == "stopped"
        assert NodeAgentStatus.STARTING.value == "starting"
        assert NodeAgentStatus.RUNNING.value == "running"
        assert NodeAgentStatus.ERROR.value == "error"
