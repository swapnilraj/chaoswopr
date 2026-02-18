"""Agent messaging infrastructure for chaoswopr.

Provides typed message protocols, an in-process message bus with pub/sub
semantics, and a coordinator for routing messages between agents.
"""

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
from chaoswopr.agents.messaging.message_bus import (
    MessageBus,
    Subscription,
)
from chaoswopr.agents.messaging.coordinator import (
    AgentRegistry,
    AgentState,
    MessageCoordinator,
)

__all__ = [
    # Protocol
    "Message",
    "MessageType",
    "Command",
    "CommandType",
    "Response",
    "StatusUpdate",
    "Event",
    "EventType",
    "AgentType",
    # Message Bus
    "MessageBus",
    "Subscription",
    # Coordinator
    "MessageCoordinator",
    "AgentRegistry",
    "AgentState",
]
