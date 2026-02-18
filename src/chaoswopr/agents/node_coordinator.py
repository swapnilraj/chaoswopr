"""Node Agent Coordinator for managing a fleet of node agents.

The NodeAgentCoordinator manages the lifecycle of multiple node agents,
distributes the 70/30 honest/adversarial split, and provides batch
operations for the orchestrator.

Responsibilities:
  - Create and configure a fleet of N node agents
  - Assign 70% honest / 30% adversarial split
  - Batch command execution (switch modes, set behaviors)
  - Fleet health monitoring
  - Integration with the message bus for orchestrator commands

The coordinator is the single point of control for all node agents
during an experiment.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable

from chaoswopr.agents.messaging.coordinator import MessageCoordinator
from chaoswopr.agents.messaging.protocol import (
    AgentType,
    Command,
    CommandType,
    Response,
)
from chaoswopr.agents.node_agent import AgentMode, NodeAgent, NodeAgentConfig, NodeAgentStatus
from chaoswopr.agents.node_agent_api import _create_behavior
from chaoswopr.safety.audit import AuditLogger

logger = logging.getLogger(__name__)


@dataclass
class FleetConfig:
    """Configuration for a node agent fleet.

    Attributes:
        num_agents: Total number of node agents.
        adversarial_ratio: Fraction of agents that start adversarial (0-1).
        beacon_api_urls: List of beacon API URLs (cycled if fewer than num_agents).
        base_proxy_port: Base port for proxy servers.
        default_behavior: Default adversarial behavior type.
        default_behavior_params: Default adversarial behavior parameters.
    """

    num_agents: int = 10
    adversarial_ratio: float = 0.3
    beacon_api_urls: list[str] = field(
        default_factory=lambda: ["http://localhost:5052"]
    )
    base_proxy_port: int = 6000
    default_behavior: str = "attestation_withholding"
    default_behavior_params: dict[str, Any] = field(
        default_factory=lambda: {"withhold_probability": 1.0}
    )


class NodeAgentCoordinator:
    """Coordinator for managing a fleet of node agents.

    Creates, configures, and controls multiple node agents during
    chaos engineering experiments. Handles the 70/30 honest/adversarial
    split and provides batch operations.

    Examples:
        >>> from chaoswopr.agents.messaging.message_bus import MessageBus
        >>> from chaoswopr.agents.messaging.coordinator import MessageCoordinator
        >>> bus = MessageBus()
        >>> msg_coordinator = MessageCoordinator(bus)
        >>> fleet_config = FleetConfig(num_agents=10, adversarial_ratio=0.3)
        >>> coordinator = NodeAgentCoordinator(
        ...     fleet_config=fleet_config,
        ...     message_coordinator=msg_coordinator,
        ...     dry_run=True,
        ... )
        >>> coordinator.create_fleet()
        >>> coordinator.start_all()
        >>> honest, adversarial = coordinator.get_split()
        >>> assert len(honest) == 7
        >>> assert len(adversarial) == 3
    """

    def __init__(
        self,
        fleet_config: FleetConfig,
        message_coordinator: MessageCoordinator | None = None,
        audit_logger: AuditLogger | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the node agent coordinator.

        Args:
            fleet_config: Fleet configuration.
            message_coordinator: Optional message coordinator for messaging integration.
            audit_logger: Optional audit logger.
            dry_run: If True, agents run in dry-run mode.
        """
        self._config = fleet_config
        self._msg_coordinator = message_coordinator
        self._audit_logger = audit_logger
        self._dry_run = dry_run

        # Agent storage
        self._agents: dict[str, NodeAgent] = {}
        self._honest_ids: list[str] = []
        self._adversarial_ids: list[str] = []
        self._fleet_created = False

    @property
    def fleet_size(self) -> int:
        """Get the total number of agents in the fleet."""
        return len(self._agents)

    @property
    def fleet_created(self) -> bool:
        """Check if the fleet has been created."""
        return self._fleet_created

    @property
    def honest_count(self) -> int:
        """Get the number of honest agents."""
        return len(self._honest_ids)

    @property
    def adversarial_count(self) -> int:
        """Get the number of adversarial agents."""
        return len(self._adversarial_ids)

    def get_agent(self, agent_id: str) -> NodeAgent | None:
        """Get a specific agent by ID.

        Args:
            agent_id: Agent identifier.

        Returns:
            NodeAgent or None if not found.
        """
        return self._agents.get(agent_id)

    def get_all_agents(self) -> list[NodeAgent]:
        """Get all agents in the fleet.

        Returns:
            List of all NodeAgent instances.
        """
        return list(self._agents.values())

    def get_honest_agents(self) -> list[NodeAgent]:
        """Get all honest agents.

        Returns:
            List of honest NodeAgent instances.
        """
        return [self._agents[aid] for aid in self._honest_ids if aid in self._agents]

    def get_adversarial_agents(self) -> list[NodeAgent]:
        """Get all adversarial agents.

        Returns:
            List of adversarial NodeAgent instances.
        """
        return [self._agents[aid] for aid in self._adversarial_ids if aid in self._agents]

    def get_split(self) -> tuple[list[NodeAgent], list[NodeAgent]]:
        """Get the honest/adversarial split.

        Returns:
            Tuple of (honest_agents, adversarial_agents).
        """
        return self.get_honest_agents(), self.get_adversarial_agents()

    def create_fleet(self) -> dict[str, Any]:
        """Create the fleet of node agents.

        Creates N agents with the configured honest/adversarial ratio.
        Agents are not started -- call start_all() to start them.

        Returns:
            Dictionary with fleet creation results.

        Raises:
            RuntimeError: If fleet is already created.
        """
        if self._fleet_created:
            raise RuntimeError("Fleet already created. Call destroy_fleet() first.")

        num_agents = self._config.num_agents
        num_adversarial = math.ceil(num_agents * self._config.adversarial_ratio)
        num_honest = num_agents - num_adversarial

        beacon_urls = self._config.beacon_api_urls

        for i in range(num_agents):
            agent_id = f"node-{i:03d}"
            beacon_url = beacon_urls[i % len(beacon_urls)]
            mode = AgentMode.ADVERSARIAL if i < num_adversarial else AgentMode.HONEST

            config = NodeAgentConfig(
                node_id=agent_id,
                beacon_api_url=beacon_url,
                mode=mode,
                proxy_port=self._config.base_proxy_port + i,
            )

            agent = NodeAgent(
                config=config,
                audit_logger=self._audit_logger,
                dry_run=self._dry_run,
            )

            self._agents[agent_id] = agent

            if mode == AgentMode.ADVERSARIAL:
                self._adversarial_ids.append(agent_id)
            else:
                self._honest_ids.append(agent_id)

            # Register with message coordinator if available
            if self._msg_coordinator is not None:
                handler = self._make_command_handler(agent)
                self._msg_coordinator.register_agent(
                    agent_id=agent_id,
                    agent_type=AgentType.NODE_AGENT,
                    command_handler=handler,
                    metadata={"mode": mode.value},
                )

        self._fleet_created = True

        logger.info(
            "Fleet created: %d agents (%d honest, %d adversarial)",
            num_agents,
            num_honest,
            num_adversarial,
        )

        return {
            "total_agents": num_agents,
            "honest_count": num_honest,
            "adversarial_count": num_adversarial,
            "agent_ids": list(self._agents.keys()),
        }

    def start_all(self) -> dict[str, Any]:
        """Start all agents in the fleet.

        Returns:
            Dictionary with start results.
        """
        if not self._fleet_created:
            raise RuntimeError("Fleet not created yet. Call create_fleet() first.")

        started = 0
        failed = 0

        for agent_id, agent in self._agents.items():
            try:
                agent.start()
                started += 1
            except Exception as e:
                logger.error("Failed to start agent %s: %s", agent_id, e)
                failed += 1

        # Set default behavior on adversarial agents
        for agent_id in self._adversarial_ids:
            agent = self._agents[agent_id]
            try:
                behavior = _create_behavior(
                    self._config.default_behavior,
                    self._config.default_behavior_params,
                )
                agent.set_behavior(behavior)
            except Exception as e:
                logger.error("Failed to set behavior on %s: %s", agent_id, e)

        logger.info("Fleet started: %d succeeded, %d failed", started, failed)

        return {
            "started": started,
            "failed": failed,
        }

    def stop_all(self) -> dict[str, Any]:
        """Stop all agents in the fleet.

        Returns:
            Dictionary with stop results.
        """
        stopped = 0
        failed = 0

        for agent_id, agent in self._agents.items():
            try:
                agent.stop()
                stopped += 1
            except Exception as e:
                logger.error("Failed to stop agent %s: %s", agent_id, e)
                failed += 1

        logger.info("Fleet stopped: %d succeeded, %d failed", stopped, failed)

        return {
            "stopped": stopped,
            "failed": failed,
        }

    def destroy_fleet(self) -> None:
        """Destroy the fleet, stopping all agents and cleaning up."""
        self.stop_all()

        # Unregister from message coordinator
        if self._msg_coordinator is not None:
            for agent_id in self._agents:
                self._msg_coordinator.unregister_agent(agent_id)

        self._agents.clear()
        self._honest_ids.clear()
        self._adversarial_ids.clear()
        self._fleet_created = False

        logger.info("Fleet destroyed")

    def switch_mode(
        self,
        agent_ids: list[str],
        mode: AgentMode,
    ) -> list[dict[str, Any]]:
        """Switch mode for a list of agents.

        Args:
            agent_ids: IDs of agents to switch.
            mode: New mode.

        Returns:
            List of result dictionaries.
        """
        results = []
        for agent_id in agent_ids:
            agent = self._agents.get(agent_id)
            if agent is None:
                results.append({
                    "agent_id": agent_id,
                    "success": False,
                    "error": "Agent not found",
                })
                continue

            try:
                old_mode = agent.mode
                agent.switch_mode(mode)

                # Update tracking lists
                if mode == AgentMode.ADVERSARIAL and agent_id not in self._adversarial_ids:
                    self._adversarial_ids.append(agent_id)
                    if agent_id in self._honest_ids:
                        self._honest_ids.remove(agent_id)
                elif mode == AgentMode.HONEST and agent_id not in self._honest_ids:
                    self._honest_ids.append(agent_id)
                    if agent_id in self._adversarial_ids:
                        self._adversarial_ids.remove(agent_id)

                results.append({
                    "agent_id": agent_id,
                    "success": True,
                    "old_mode": old_mode.value,
                    "new_mode": mode.value,
                })
            except Exception as e:
                results.append({
                    "agent_id": agent_id,
                    "success": False,
                    "error": str(e),
                })

        return results

    def set_behavior(
        self,
        agent_ids: list[str],
        behavior_type: str,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Set adversarial behavior on a list of agents.

        Args:
            agent_ids: IDs of agents to configure.
            behavior_type: Behavior type name.
            parameters: Behavior parameters.

        Returns:
            List of result dictionaries.
        """
        results = []
        for agent_id in agent_ids:
            agent = self._agents.get(agent_id)
            if agent is None:
                results.append({
                    "agent_id": agent_id,
                    "success": False,
                    "error": "Agent not found",
                })
                continue

            if agent.mode != AgentMode.ADVERSARIAL:
                results.append({
                    "agent_id": agent_id,
                    "success": False,
                    "error": "Agent not in adversarial mode",
                })
                continue

            try:
                behavior = _create_behavior(behavior_type, parameters)
                agent.set_behavior(behavior)
                results.append({
                    "agent_id": agent_id,
                    "success": True,
                    "behavior_type": behavior_type,
                })
            except Exception as e:
                results.append({
                    "agent_id": agent_id,
                    "success": False,
                    "error": str(e),
                })

        return results

    def get_fleet_status(self) -> dict[str, Any]:
        """Get status of the entire fleet.

        Returns:
            Fleet status dictionary.
        """
        agent_statuses = []
        running_count = 0
        honest_running = 0
        adversarial_running = 0

        for agent_id, agent in self._agents.items():
            status = agent.get_status()
            agent_statuses.append(status)

            if agent.status == NodeAgentStatus.RUNNING:
                running_count += 1
                if agent.mode == AgentMode.HONEST:
                    honest_running += 1
                else:
                    adversarial_running += 1

        return {
            "fleet_created": self._fleet_created,
            "total_agents": len(self._agents),
            "running_agents": running_count,
            "honest_count": len(self._honest_ids),
            "adversarial_count": len(self._adversarial_ids),
            "honest_running": honest_running,
            "adversarial_running": adversarial_running,
            "agents": agent_statuses,
        }

    def get_agent_ids(self) -> list[str]:
        """Get all agent IDs.

        Returns:
            List of agent IDs.
        """
        return list(self._agents.keys())

    def _make_command_handler(self, agent: NodeAgent) -> Callable[[Command], Response]:
        """Create a command handler for a node agent.

        Args:
            agent: The NodeAgent to create a handler for.

        Returns:
            Command handler function.
        """
        def handler(cmd: Command) -> Response:
            try:
                if cmd.command_type == CommandType.SWITCH_MODE:
                    mode = AgentMode(cmd.parameters.get("mode", "honest"))
                    agent.switch_mode(mode)
                    return Response(
                        source_agent_id=agent.node_id,
                        success=True,
                        result={"mode": mode.value},
                    )

                elif cmd.command_type == CommandType.SET_BEHAVIOR:
                    behavior_type = cmd.parameters.get("behavior_type", "")
                    behavior_params = cmd.parameters.get("parameters", {})
                    behavior = _create_behavior(behavior_type, behavior_params)
                    agent.set_behavior(behavior)
                    return Response(
                        source_agent_id=agent.node_id,
                        success=True,
                        result={"behavior_type": behavior_type},
                    )

                elif cmd.command_type == CommandType.START_AGENT:
                    agent.start()
                    return Response(
                        source_agent_id=agent.node_id,
                        success=True,
                        result={"status": agent.status.value},
                    )

                elif cmd.command_type == CommandType.STOP_AGENT:
                    agent.stop()
                    return Response(
                        source_agent_id=agent.node_id,
                        success=True,
                        result={"status": agent.status.value},
                    )

                elif cmd.command_type == CommandType.GET_STATUS:
                    return Response(
                        source_agent_id=agent.node_id,
                        success=True,
                        result=agent.get_status(),
                    )

                else:
                    return Response(
                        source_agent_id=agent.node_id,
                        success=False,
                        error_message=f"Unknown command: {cmd.command_type.value}",
                    )

            except Exception as e:
                return Response(
                    source_agent_id=agent.node_id,
                    success=False,
                    error_message=str(e),
                )

        return handler
