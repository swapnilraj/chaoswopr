"""Message coordinator for routing and agent state tracking.

The MessageCoordinator sits atop the MessageBus and provides:
  - Agent registration and discovery
  - Command routing with response correlation
  - Agent state tracking and health monitoring
  - Experiment-scoped message routing

It is the primary interface agents use for inter-agent communication,
abstracting away topic naming conventions and message correlation.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from chaoswopr.agents.messaging.message_bus import MessageBus
from chaoswopr.agents.messaging.protocol import (
    AgentType,
    Command,
    CommandType,
    Event,
    EventType,
    Message,
    MessageType,
    Response,
    StatusUpdate,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Tracked state of a registered agent.

    Attributes:
        agent_id: Unique agent identifier.
        agent_type: Type of agent.
        state: Current agent state string.
        last_heartbeat: Time of last status update.
        registered_at: When the agent was registered.
        metadata: Agent-specific metadata.
    """

    agent_id: str
    agent_type: AgentType
    state: str = "registered"
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "state": self.state,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "registered_at": self.registered_at.isoformat(),
            "metadata": self.metadata,
        }


class AgentRegistry:
    """Registry of all agents in the system.

    Tracks agent registration, state, and provides discovery methods.
    """

    def __init__(self) -> None:
        """Initialize the agent registry."""
        self._agents: dict[str, AgentState] = {}
        self._lock = threading.Lock()

    @property
    def agent_count(self) -> int:
        """Get the total number of registered agents."""
        return len(self._agents)

    def register(
        self,
        agent_id: str,
        agent_type: AgentType,
        metadata: dict[str, Any] | None = None,
    ) -> AgentState:
        """Register an agent.

        Args:
            agent_id: Unique agent identifier.
            agent_type: Type of agent.
            metadata: Optional agent metadata.

        Returns:
            AgentState for the registered agent.

        Raises:
            ValueError: If agent_id is already registered.
        """
        with self._lock:
            if agent_id in self._agents:
                raise ValueError(f"Agent '{agent_id}' is already registered")

            state = AgentState(
                agent_id=agent_id,
                agent_type=agent_type,
                metadata=metadata or {},
            )
            self._agents[agent_id] = state

            logger.info(
                "Agent registered: %s (type=%s)", agent_id, agent_type.value
            )
            return state

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent.

        Args:
            agent_id: Agent to unregister.

        Returns:
            True if agent was found and removed.
        """
        with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                logger.info("Agent unregistered: %s", agent_id)
                return True
            return False

    def get_agent(self, agent_id: str) -> AgentState | None:
        """Get an agent's state.

        Args:
            agent_id: Agent identifier.

        Returns:
            AgentState or None if not found.
        """
        return self._agents.get(agent_id)

    def get_agents_by_type(self, agent_type: AgentType) -> list[AgentState]:
        """Get all agents of a specific type.

        Args:
            agent_type: Type of agents to find.

        Returns:
            List of matching AgentState objects.
        """
        return [a for a in self._agents.values() if a.agent_type == agent_type]

    def update_state(
        self,
        agent_id: str,
        state: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update an agent's state.

        Args:
            agent_id: Agent to update.
            state: New state string.
            metadata: Optional metadata to merge.

        Returns:
            True if agent was found and updated.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            return False

        agent.state = state
        agent.last_heartbeat = datetime.now(timezone.utc)
        if metadata:
            agent.metadata.update(metadata)
        return True

    def get_all(self) -> list[AgentState]:
        """Get all registered agents.

        Returns:
            List of all AgentState objects.
        """
        return list(self._agents.values())

    def clear(self) -> None:
        """Remove all registered agents."""
        with self._lock:
            self._agents.clear()


class MessageCoordinator:
    """High-level coordinator for agent messaging.

    Provides a simplified interface for agents to communicate, handling
    topic naming, message correlation, and agent state tracking.

    Topic naming conventions:
      agents.<type>.<id>.commands   -- Direct commands to an agent
      agents.<type>.<id>.responses  -- Responses from an agent
      agents.<type>.events          -- Events from agents of a type
      experiments.<id>.events       -- Experiment-scoped events
      system.events                 -- System-wide events
      system.status                 -- Status updates

    Examples:
        >>> from chaoswopr.agents.messaging.message_bus import MessageBus
        >>> bus = MessageBus()
        >>> coordinator = MessageCoordinator(bus)
        >>> coordinator.register_agent("orch-1", AgentType.ORCHESTRATOR)
        >>> coordinator.register_agent("node-1", AgentType.NODE_AGENT)
    """

    def __init__(self, message_bus: MessageBus) -> None:
        """Initialize the coordinator.

        Args:
            message_bus: The underlying message bus for pub/sub.
        """
        self._bus = message_bus
        self._registry = AgentRegistry()
        self._pending_responses: dict[str, Response | None] = {}
        self._response_lock = threading.Lock()

    @property
    def bus(self) -> MessageBus:
        """Get the underlying message bus."""
        return self._bus

    @property
    def registry(self) -> AgentRegistry:
        """Get the agent registry."""
        return self._registry

    def register_agent(
        self,
        agent_id: str,
        agent_type: AgentType,
        command_handler: Callable[[Command], Response] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentState:
        """Register an agent and set up its message subscriptions.

        Args:
            agent_id: Unique agent identifier.
            agent_type: Type of agent.
            command_handler: Optional handler for incoming commands.
            metadata: Optional agent metadata.

        Returns:
            AgentState for the registered agent.
        """
        state = self._registry.register(agent_id, agent_type, metadata)

        # Subscribe to commands directed at this agent
        if command_handler is not None:
            command_topic = f"agents.{agent_type.value}.{agent_id}.commands"

            def _handle_command(msg: Message) -> None:
                if isinstance(msg, Command):
                    response = command_handler(msg)
                    # Publish the response
                    response_topic = f"agents.{agent_type.value}.{agent_id}.responses"
                    response.correlation_id = msg.message_id
                    response.target_agent_id = msg.source_agent_id
                    self._bus.publish(response_topic, response)

                    # Also notify pending response waiters
                    with self._response_lock:
                        if msg.message_id in self._pending_responses:
                            self._pending_responses[msg.message_id] = response

            self._bus.subscribe(command_topic, _handle_command, agent_id)

        # Subscribe to system-wide events
        self._bus.subscribe("system.events", lambda _: None, agent_id)

        return state

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent and remove its subscriptions.

        Args:
            agent_id: Agent to unregister.

        Returns:
            True if agent was found and removed.
        """
        self._bus.unsubscribe_all(agent_id)
        return self._registry.unregister(agent_id)

    def send_command(
        self,
        source_agent_id: str,
        target_agent_id: str,
        command_type: CommandType,
        parameters: dict[str, Any] | None = None,
        experiment_id: str | None = None,
    ) -> Command:
        """Send a command to a specific agent.

        Args:
            source_agent_id: ID of the sending agent.
            target_agent_id: ID of the target agent.
            command_type: Type of command.
            parameters: Command parameters.
            experiment_id: Associated experiment ID.

        Returns:
            The sent Command message.

        Raises:
            ValueError: If target agent is not registered.
        """
        target = self._registry.get_agent(target_agent_id)
        if target is None:
            raise ValueError(f"Target agent '{target_agent_id}' is not registered")

        command = Command(
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            command_type=command_type,
            parameters=parameters or {},
            experiment_id=experiment_id,
        )

        # Determine topic from target agent type
        topic = f"agents.{target.agent_type.value}.{target_agent_id}.commands"
        self._bus.publish(topic, command)

        return command

    def broadcast_command(
        self,
        source_agent_id: str,
        agent_type: AgentType,
        command_type: CommandType,
        parameters: dict[str, Any] | None = None,
        experiment_id: str | None = None,
        target_agent_ids: list[str] | None = None,
    ) -> list[Command]:
        """Broadcast a command to all agents of a type.

        Args:
            source_agent_id: ID of the sending agent.
            agent_type: Type of agents to command.
            command_type: Type of command.
            parameters: Command parameters.
            experiment_id: Associated experiment ID.
            target_agent_ids: Optional subset of agent IDs to target.

        Returns:
            List of sent Command messages.
        """
        agents = self._registry.get_agents_by_type(agent_type)

        if target_agent_ids is not None:
            agents = [a for a in agents if a.agent_id in target_agent_ids]

        commands = []
        for agent in agents:
            command = self.send_command(
                source_agent_id=source_agent_id,
                target_agent_id=agent.agent_id,
                command_type=command_type,
                parameters=parameters,
                experiment_id=experiment_id,
            )
            commands.append(command)

        return commands

    def emit_event(
        self,
        source_agent_id: str,
        event_type: EventType,
        severity: str = "info",
        details: dict[str, Any] | None = None,
        experiment_id: str | None = None,
    ) -> Event:
        """Emit an event to all subscribers.

        Args:
            source_agent_id: ID of the emitting agent.
            event_type: Type of event.
            severity: Event severity.
            details: Event details.
            experiment_id: Associated experiment ID.

        Returns:
            The emitted Event message.
        """
        source = self._registry.get_agent(source_agent_id)
        agent_type_str = source.agent_type.value if source else "unknown"

        event = Event(
            source_agent_id=source_agent_id,
            event_type=event_type,
            severity=severity,
            details=details or {},
            experiment_id=experiment_id,
        )

        # Publish to agent-type-specific topic
        self._bus.publish(f"agents.{agent_type_str}.events", event)

        # Also publish to experiment topic if applicable
        if experiment_id:
            self._bus.publish(f"experiments.{experiment_id}.events", event)

        # System events go to system topic
        if event_type in (EventType.CIRCUIT_BREAKER_TRIPPED, EventType.BLAST_RADIUS_EXCEEDED):
            self._bus.publish("system.events", event)

        return event

    def send_status_update(
        self,
        agent_id: str,
        agent_state: str,
        metrics: dict[str, Any] | None = None,
    ) -> StatusUpdate:
        """Send a status update from an agent.

        Updates the registry and publishes the status.

        Args:
            agent_id: ID of the agent sending status.
            agent_state: Current agent state.
            metrics: Agent metrics.

        Returns:
            The sent StatusUpdate message.
        """
        agent = self._registry.get_agent(agent_id)
        agent_type = agent.agent_type if agent else AgentType.NODE_AGENT

        # Update registry
        self._registry.update_state(agent_id, agent_state, metrics)

        update = StatusUpdate(
            source_agent_id=agent_id,
            agent_type=agent_type,
            agent_state=agent_state,
            metrics=metrics or {},
        )

        self._bus.publish("system.status", update)

        return update

    def subscribe_to_events(
        self,
        subscriber_id: str,
        handler: Callable[[Event], None],
        agent_type: AgentType | None = None,
        experiment_id: str | None = None,
    ) -> str:
        """Subscribe to events.

        Args:
            subscriber_id: ID of the subscribing agent.
            handler: Callback for events.
            agent_type: Optional filter by source agent type.
            experiment_id: Optional filter by experiment.

        Returns:
            Subscription ID.
        """
        def _event_handler(msg: Message) -> None:
            if isinstance(msg, Event):
                handler(msg)

        if experiment_id:
            topic = f"experiments.{experiment_id}.events"
        elif agent_type:
            topic = f"agents.{agent_type.value}.events"
        else:
            topic = "agents.*.events"

        return self._bus.subscribe(topic, _event_handler, subscriber_id)

    def get_fleet_status(
        self,
        agent_type: AgentType | None = None,
    ) -> dict[str, Any]:
        """Get status of all registered agents.

        Args:
            agent_type: Optional filter by agent type.

        Returns:
            Fleet status dictionary.
        """
        if agent_type:
            agents = self._registry.get_agents_by_type(agent_type)
        else:
            agents = self._registry.get_all()

        return {
            "total_agents": len(agents),
            "agents": [a.to_dict() for a in agents],
            "by_type": {
                t.value: len([a for a in agents if a.agent_type == t])
                for t in AgentType
            },
            "bus_stats": self._bus.get_stats(),
        }

    def reset(self) -> None:
        """Reset the coordinator, clearing all agents and subscriptions."""
        self._registry.clear()
        self._bus.reset()
        with self._response_lock:
            self._pending_responses.clear()
        logger.info("Message coordinator reset")
