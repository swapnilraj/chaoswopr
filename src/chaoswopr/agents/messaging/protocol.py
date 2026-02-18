"""Typed message protocol for agent communication.

Defines the message schemas used by all agents in the chaoswopr multi-agent
system. Messages are typed, serializable, and carry enough metadata for
audit logging and replay.

Message Types:
  - Command: Orchestrator -> Agent directives (switch mode, inject fault, etc.)
  - Response: Agent -> Orchestrator acknowledgments with results
  - StatusUpdate: Agent -> Coordinator periodic health/state reports
  - Event: Agent -> All subscribers for significant occurrences (anomaly, breach)

All messages include:
  - Unique ID for correlation
  - Timestamps for ordering
  - Source and target agent IDs
  - Payload with typed content
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    """Top-level message type classification."""

    COMMAND = "command"
    RESPONSE = "response"
    STATUS_UPDATE = "status_update"
    EVENT = "event"


class AgentType(str, Enum):
    """Types of agents in the system."""

    ORCHESTRATOR = "orchestrator"
    NODE_AGENT = "node_agent"
    OBSERVER = "observer"
    COORDINATOR = "coordinator"


class CommandType(str, Enum):
    """Types of commands the orchestrator can send."""

    # Node agent commands
    SWITCH_MODE = "switch_mode"
    SET_BEHAVIOR = "set_behavior"
    START_AGENT = "start_agent"
    STOP_AGENT = "stop_agent"
    GET_STATUS = "get_status"

    # Observer commands
    START_OBSERVING = "start_observing"
    STOP_OBSERVING = "stop_observing"
    CONFIGURE_SLOS = "configure_slos"

    # Experiment lifecycle
    START_EXPERIMENT = "start_experiment"
    HALT_EXPERIMENT = "halt_experiment"
    RESET = "reset"

    # Fault injection
    INJECT_FAULT = "inject_fault"
    REMOVE_FAULT = "remove_fault"
    REMOVE_ALL_FAULTS = "remove_all_faults"

    # Batch operations
    BATCH_SWITCH_MODE = "batch_switch_mode"
    BATCH_SET_BEHAVIOR = "batch_set_behavior"


class EventType(str, Enum):
    """Types of events agents can emit."""

    # Observer events
    ANOMALY_DETECTED = "anomaly_detected"
    SLO_BREACH = "slo_breach"
    ROOT_CAUSE_HYPOTHESIS = "root_cause_hypothesis"
    RECOVERY_OBSERVED = "recovery_observed"

    # Orchestrator events
    EXPERIMENT_STARTED = "experiment_started"
    EXPERIMENT_COMPLETED = "experiment_completed"
    EXPERIMENT_HALTED = "experiment_halted"
    PHASE_CHANGED = "phase_changed"
    FAULT_INJECTED = "fault_injected"
    FAULT_REMOVED = "fault_removed"

    # Node agent events
    MODE_SWITCHED = "mode_switched"
    BEHAVIOR_SET = "behavior_set"
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"

    # Safety events
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker_tripped"
    BLAST_RADIUS_EXCEEDED = "blast_radius_exceeded"


@dataclass
class Message:
    """Base message for agent communication.

    All messages in the system extend this base with typed payloads.

    Attributes:
        message_id: Unique message identifier for correlation.
        message_type: Top-level type classification.
        source_agent_id: ID of the sending agent.
        target_agent_id: ID of the target agent (None for broadcast).
        timestamp: When the message was created.
        correlation_id: ID for request/response correlation.
        experiment_id: Associated experiment ID (if any).
        payload: Message-specific content.
    """

    source_agent_id: str
    message_type: MessageType = MessageType.EVENT
    target_agent_id: str | None = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None
    experiment_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "source_agent_id": self.source_agent_id,
            "target_agent_id": self.target_agent_id,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "experiment_id": self.experiment_id,
            "payload": self.payload,
        }


@dataclass
class Command(Message):
    """Command message from orchestrator to agents.

    Carries a typed command with parameters that the target agent
    should execute.

    Attributes:
        command_type: Specific command to execute.
        parameters: Command-specific parameters.
        timeout_seconds: Maximum time to wait for response.
    """

    command_type: CommandType = CommandType.GET_STATUS
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        """Set message type to COMMAND."""
        self.message_type = MessageType.COMMAND
        self.payload = {
            "command_type": self.command_type.value,
            "parameters": self.parameters,
            "timeout_seconds": self.timeout_seconds,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        base = super().to_dict()
        base["command_type"] = self.command_type.value
        base["parameters"] = self.parameters
        base["timeout_seconds"] = self.timeout_seconds
        return base


@dataclass
class Response(Message):
    """Response message from agent back to orchestrator.

    Acknowledges a command with success/failure status and result data.

    Attributes:
        success: Whether the command was executed successfully.
        result: Command execution result data.
        error_message: Error description if failed.
    """

    success: bool = True
    result: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Set message type to RESPONSE."""
        self.message_type = MessageType.RESPONSE
        self.payload = {
            "success": self.success,
            "result": self.result,
            "error_message": self.error_message,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        base = super().to_dict()
        base["success"] = self.success
        base["result"] = self.result
        base["error_message"] = self.error_message
        return base


@dataclass
class StatusUpdate(Message):
    """Status update from agent to coordinator.

    Periodic health/state reports that agents send to keep the
    coordinator informed of their current state.

    Attributes:
        agent_type: Type of agent sending the update.
        agent_state: Current state of the agent.
        metrics: Agent-specific metrics (uptime, action count, etc.).
    """

    agent_type: AgentType = AgentType.NODE_AGENT
    agent_state: str = "unknown"
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set message type to STATUS_UPDATE."""
        self.message_type = MessageType.STATUS_UPDATE
        self.payload = {
            "agent_type": self.agent_type.value,
            "agent_state": self.agent_state,
            "metrics": self.metrics,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        base = super().to_dict()
        base["agent_type"] = self.agent_type.value
        base["agent_state"] = self.agent_state
        base["metrics"] = self.metrics
        return base


@dataclass
class Event(Message):
    """Event message broadcast to subscribers.

    Significant occurrences that agents emit for other agents or
    external systems to react to.

    Attributes:
        event_type: Specific type of event.
        severity: Event severity (info, warning, critical).
        details: Event-specific details.
    """

    event_type: EventType = EventType.ANOMALY_DETECTED
    severity: str = "info"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set message type to EVENT."""
        self.message_type = MessageType.EVENT
        self.payload = {
            "event_type": self.event_type.value,
            "severity": self.severity,
            "details": self.details,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        base = super().to_dict()
        base["event_type"] = self.event_type.value
        base["severity"] = self.severity
        base["details"] = self.details
        return base
