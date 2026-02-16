"""Node Agent implementation for chaoswopr.

Node Agents are AI-controlled agents that run alongside validator clients
in a sidecar pattern, intercepting and potentially modifying Beacon API calls.

Architecture:
- Runs as HTTP proxy between validator client and beacon node
- Intercepts all Beacon API requests
- In HONEST mode: passes through all requests with audit logging
- In ADVERSARIAL mode: can manipulate requests based on configured behaviors

The agent system supports 30% of nodes being adversarial to simulate
Byzantine behavior and test network resilience.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Thread
from typing import Any

import requests

from chaoswopr.safety.audit import ActionType, AuditLogger, Outcome

logger = logging.getLogger(__name__)


class AgentMode(str, Enum):
    """Operating mode for node agents."""

    HONEST = "honest"
    ADVERSARIAL = "adversarial"


class NodeAgentStatus(str, Enum):
    """Status of a node agent."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class NodeAgentConfig:
    """Configuration for a node agent.

    Attributes:
        node_id: Unique identifier for this node/validator.
        beacon_api_url: Upstream beacon node API URL.
        mode: Initial operating mode (honest or adversarial).
        proxy_port: Port to listen on for proxied requests.
        audit_logging: Whether to enable audit logging.
    """

    node_id: str
    beacon_api_url: str
    mode: AgentMode = AgentMode.HONEST
    proxy_port: int = 5053
    audit_logging: bool = True


class BeaconAPIProxy:
    """HTTP proxy for Beacon API requests.

    Implements the sidecar pattern - sits between the validator client
    and the beacon node, intercepting all API calls. Requests can be
    modified, delayed, or blocked based on registered interceptors.
    """

    def __init__(
        self,
        upstream_url: str,
        listen_port: int,
        dry_run: bool = False,
    ) -> None:
        """Initialize the Beacon API proxy.

        Args:
            upstream_url: URL of the real beacon node.
            listen_port: Port to listen on.
            dry_run: If True, don't actually start HTTP server.
        """
        self._upstream_url = upstream_url.rstrip("/")
        self._listen_port = listen_port
        self._dry_run = dry_run
        self._is_running = False
        self._interceptors: dict[str, Any] = {}
        self._server_thread: Thread | None = None

    @property
    def upstream_url(self) -> str:
        """Get the upstream beacon node URL."""
        return self._upstream_url

    @property
    def listen_port(self) -> int:
        """Get the proxy listen port."""
        return self._listen_port

    @property
    def is_running(self) -> bool:
        """Check if the proxy is running."""
        return self._is_running

    def register_interceptor(self, path_prefix: str, interceptor: Any) -> None:
        """Register an interceptor for requests matching a path prefix.

        Args:
            path_prefix: Path prefix to match (e.g., "/eth/v1/validator/duties").
            interceptor: Callable that intercepts and potentially modifies requests.
        """
        self._interceptors[path_prefix] = interceptor

    def unregister_interceptor(self, path_prefix: str) -> None:
        """Unregister an interceptor.

        Args:
            path_prefix: Path prefix to unregister.
        """
        self._interceptors.pop(path_prefix, None)

    def start(self) -> None:
        """Start the proxy server."""
        if self._is_running:
            logger.warning("Proxy already running")
            return

        if self._dry_run:
            logger.info("Dry-run mode: proxy server not actually started")
            self._is_running = True
            return

        # In a real implementation, would start an HTTP server here
        # For now, mark as running for testing
        self._is_running = True
        logger.info(
            "Beacon API proxy started on port %d (upstream: %s)",
            self._listen_port,
            self._upstream_url,
        )

    def stop(self) -> None:
        """Stop the proxy server."""
        if not self._is_running:
            return

        if self._dry_run:
            logger.info("Dry-run mode: proxy server stopped")
            self._is_running = False
            return

        # In a real implementation, would stop the HTTP server here
        self._is_running = False
        logger.info("Beacon API proxy stopped")

    def _intercept_request(
        self, path: str, params: dict[str, Any], body: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Intercept a request and potentially modify it.

        Args:
            path: Request path.
            params: Query parameters.
            body: Request body.

        Returns:
            Modified response if intercepted, None to passthrough.
        """
        # Check if any interceptor matches this path
        for prefix, interceptor in self._interceptors.items():
            if path.startswith(prefix):
                result = interceptor(path, params, body)
                if result is not None:
                    return result

        # No interceptor matched, passthrough
        return None


class NodeAgent:
    """Node Agent controlling a single validator.

    Implements the sidecar pattern, running alongside the validator client
    and intercepting Beacon API calls. Can operate in honest or adversarial
    mode, with various behaviors available in adversarial mode.

    In production, 70% of agents are HONEST (passthrough + audit logging),
    and 30% are ADVERSARIAL (can manipulate protocol messages).
    """

    def __init__(
        self,
        config: NodeAgentConfig,
        audit_logger: AuditLogger | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the node agent.

        Args:
            config: Agent configuration.
            audit_logger: Audit logger for recording actions.
            dry_run: If True, don't actually start services.
        """
        self._config = config
        self._audit_logger = audit_logger
        self._dry_run = dry_run

        self._mode = config.mode
        self._status = NodeAgentStatus.STOPPED
        self._start_time: float | None = None

        # Initialize the Beacon API proxy
        self._proxy = BeaconAPIProxy(
            upstream_url=config.beacon_api_url,
            listen_port=config.proxy_port,
            dry_run=dry_run,
        )

        # Current behavior (used in adversarial mode)
        self._current_behavior: Any = None

        logger.info(
            "Node agent %s initialized in %s mode",
            config.node_id,
            config.mode.value,
        )

    @property
    def node_id(self) -> str:
        """Get the node ID."""
        return self._config.node_id

    @property
    def mode(self) -> AgentMode:
        """Get the current operating mode."""
        return self._mode

    @property
    def status(self) -> NodeAgentStatus:
        """Get the current status."""
        return self._status

    @property
    def proxy(self) -> BeaconAPIProxy:
        """Get the Beacon API proxy."""
        return self._proxy

    def start(self) -> None:
        """Start the node agent and proxy."""
        if self._status == NodeAgentStatus.RUNNING:
            logger.warning("Node agent %s already running", self.node_id)
            return

        self._status = NodeAgentStatus.STARTING
        self._start_time = time.monotonic()

        try:
            # Start the proxy server
            self._proxy.start()

            # Configure interceptors based on mode
            self._configure_interceptors()

            self._status = NodeAgentStatus.RUNNING

            if self._audit_logger and self._config.audit_logging:
                self._audit_logger.log(
                    agent_id=self.node_id,
                    action_type="node_agent_start",
                    target=self._config.beacon_api_url,
                    outcome=Outcome.SUCCESS,
                    parameters={"mode": self._mode.value},
                )

            logger.info("Node agent %s started successfully", self.node_id)

        except Exception as e:
            self._status = NodeAgentStatus.ERROR
            logger.error("Failed to start node agent %s: %s", self.node_id, e)
            raise

    def stop(self) -> None:
        """Stop the node agent and proxy."""
        if self._status == NodeAgentStatus.STOPPED:
            return

        try:
            # Stop the proxy server
            self._proxy.stop()

            self._status = NodeAgentStatus.STOPPED
            self._start_time = None

            if self._audit_logger and self._config.audit_logging:
                self._audit_logger.log(
                    agent_id=self.node_id,
                    action_type="node_agent_stop",
                    target=self._config.beacon_api_url,
                    outcome=Outcome.SUCCESS,
                )

            logger.info("Node agent %s stopped", self.node_id)

        except Exception as e:
            logger.error("Error stopping node agent %s: %s", self.node_id, e)
            raise

    def switch_mode(self, new_mode: AgentMode) -> None:
        """Switch between honest and adversarial mode.

        Args:
            new_mode: New operating mode.
        """
        if self._mode == new_mode:
            logger.debug("Node agent %s already in %s mode", self.node_id, new_mode.value)
            return

        old_mode = self._mode
        self._mode = new_mode

        # Reconfigure interceptors for new mode
        if self._status == NodeAgentStatus.RUNNING:
            self._configure_interceptors()

        if self._audit_logger and self._config.audit_logging:
            self._audit_logger.log(
                agent_id=self.node_id,
                action_type="node_agent_mode_switch",
                target=self._config.beacon_api_url,
                outcome=Outcome.SUCCESS,
                parameters={
                    "old_mode": old_mode.value,
                    "new_mode": new_mode.value,
                },
            )

        logger.info(
            "Node agent %s switched from %s to %s mode",
            self.node_id,
            old_mode.value,
            new_mode.value,
        )

    def set_behavior(self, behavior: Any) -> None:
        """Set the adversarial behavior for this agent.

        Only works in ADVERSARIAL mode.

        Args:
            behavior: Behavior instance to set.
        """
        if self._mode != AgentMode.ADVERSARIAL:
            raise ValueError("Cannot set behavior in honest mode")

        self._current_behavior = behavior

        # Reconfigure interceptors with new behavior
        if self._status == NodeAgentStatus.RUNNING:
            self._configure_interceptors()

        logger.info(
            "Node agent %s behavior set to: %s",
            self.node_id,
            getattr(behavior, "name", "unknown"),
        )

    def get_status(self) -> dict[str, Any]:
        """Get the current status of this agent.

        Returns:
            Status dictionary with agent state.
        """
        uptime = 0.0
        if self._start_time is not None:
            uptime = time.monotonic() - self._start_time

        return {
            "node_id": self.node_id,
            "mode": self._mode.value,
            "status": self._status.value,
            "proxy_running": self._proxy.is_running,
            "uptime_seconds": uptime,
            "beacon_api_url": self._config.beacon_api_url,
            "proxy_port": self._config.proxy_port,
        }

    def _configure_interceptors(self) -> None:
        """Configure proxy interceptors based on current mode and behavior."""
        # Clear existing interceptors
        self._proxy._interceptors.clear()

        if self._mode == AgentMode.HONEST:
            # Honest mode: passthrough with audit logging
            self._setup_honest_interceptors()
        elif self._mode == AgentMode.ADVERSARIAL and self._current_behavior:
            # Adversarial mode: use behavior interceptor
            self._setup_adversarial_interceptors()

    def _setup_honest_interceptors(self) -> None:
        """Set up interceptors for honest mode (passthrough + logging)."""
        from chaoswopr.agents.node_agent_behaviors import HonestBehavior

        honest_behavior = HonestBehavior(
            audit_logger=self._audit_logger,
            node_id=self.node_id,
        )

        # Register a catch-all interceptor
        def honest_interceptor(
            path: str, params: dict[str, Any], body: dict[str, Any] | None
        ) -> dict[str, Any] | None:
            return honest_behavior.intercept_request(path, params, body)

        self._proxy.register_interceptor("/eth/v1/", honest_interceptor)

    def _setup_adversarial_interceptors(self) -> None:
        """Set up interceptors for adversarial mode (behavior-based)."""
        if not self._current_behavior:
            return

        def adversarial_interceptor(
            path: str, params: dict[str, Any], body: dict[str, Any] | None
        ) -> dict[str, Any] | None:
            return self._current_behavior.intercept_request(path, params, body)

        self._proxy.register_interceptor("/eth/v1/", adversarial_interceptor)
