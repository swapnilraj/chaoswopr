"""In-process message bus with pub/sub semantics.

Provides asynchronous message routing between agents using topic-based
publish/subscribe. Designed as the communication backbone for the
multi-agent chaos engineering system.

Architecture:
  - Topics are hierarchical: "agents.node.node-001.commands"
  - Subscribers can use wildcard patterns: "agents.node.*.events"
  - Messages are delivered synchronously within the process
  - Message history is retained for audit and replay

Designed for in-memory operation with a clear interface that could be
swapped for Redis pub/sub in production without changing agent code.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from chaoswopr.agents.messaging.protocol import Message, MessageType

logger = logging.getLogger(__name__)

# Type alias for message handler callbacks
MessageHandler = Callable[[Message], None]


@dataclass
class Subscription:
    """A topic subscription in the message bus.

    Attributes:
        subscription_id: Unique subscription identifier.
        topic_pattern: Topic pattern (supports * wildcards).
        handler: Callback function for matching messages.
        subscriber_id: ID of the subscribing agent.
        created_at: When the subscription was created.
    """

    subscription_id: str
    topic_pattern: str
    handler: MessageHandler
    subscriber_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def matches(self, topic: str) -> bool:
        """Check if a topic matches this subscription pattern.

        Args:
            topic: Topic string to match against.

        Returns:
            True if the topic matches the pattern.
        """
        return fnmatch.fnmatch(topic, self.topic_pattern)


class MessageBus:
    """In-process message bus for agent communication.

    Implements topic-based publish/subscribe messaging with synchronous
    delivery. All agents publish and subscribe through this central bus.

    Topic conventions:
      - agents.<type>.<id>.commands  -- Commands to specific agents
      - agents.<type>.<id>.responses -- Responses from specific agents
      - agents.<type>.*.events       -- Events from all agents of a type
      - experiments.<id>.events      -- Experiment-scoped events
      - system.events                -- System-wide events

    Examples:
        >>> bus = MessageBus()
        >>> received = []
        >>> bus.subscribe("test.topic", lambda msg: received.append(msg), "subscriber-1")
        >>> from chaoswopr.agents.messaging.protocol import Message, MessageType
        >>> msg = Message(message_type=MessageType.EVENT, source_agent_id="test")
        >>> bus.publish("test.topic", msg)
        >>> assert len(received) == 1
    """

    def __init__(self) -> None:
        """Initialize the message bus."""
        self._subscriptions: list[Subscription] = []
        self._subscription_counter = 0
        self._message_history: list[tuple[str, Message]] = []
        self._lock = threading.Lock()
        self._stats: dict[str, int] = defaultdict(int)

    @property
    def subscription_count(self) -> int:
        """Get the number of active subscriptions."""
        return len(self._subscriptions)

    @property
    def message_count(self) -> int:
        """Get the total number of messages published."""
        return self._stats["messages_published"]

    def subscribe(
        self,
        topic_pattern: str,
        handler: MessageHandler,
        subscriber_id: str,
    ) -> str:
        """Subscribe to messages on a topic pattern.

        Args:
            topic_pattern: Topic pattern to subscribe to (supports * wildcards).
            handler: Callback function invoked for each matching message.
            subscriber_id: ID of the subscribing agent.

        Returns:
            Subscription ID for later unsubscription.
        """
        with self._lock:
            self._subscription_counter += 1
            sub_id = f"sub-{self._subscription_counter:04d}"

            subscription = Subscription(
                subscription_id=sub_id,
                topic_pattern=topic_pattern,
                handler=handler,
                subscriber_id=subscriber_id,
            )
            self._subscriptions.append(subscription)

            logger.debug(
                "Subscription %s created: %s -> %s",
                sub_id,
                subscriber_id,
                topic_pattern,
            )

            return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription.

        Args:
            subscription_id: ID of the subscription to remove.

        Returns:
            True if the subscription was found and removed.
        """
        with self._lock:
            for i, sub in enumerate(self._subscriptions):
                if sub.subscription_id == subscription_id:
                    self._subscriptions.pop(i)
                    logger.debug("Subscription %s removed", subscription_id)
                    return True
            return False

    def unsubscribe_all(self, subscriber_id: str) -> int:
        """Remove all subscriptions for a subscriber.

        Args:
            subscriber_id: ID of the subscriber.

        Returns:
            Number of subscriptions removed.
        """
        with self._lock:
            before = len(self._subscriptions)
            self._subscriptions = [
                s for s in self._subscriptions if s.subscriber_id != subscriber_id
            ]
            removed = before - len(self._subscriptions)
            if removed > 0:
                logger.debug(
                    "Removed %d subscriptions for %s", removed, subscriber_id
                )
            return removed

    def publish(self, topic: str, message: Message) -> int:
        """Publish a message to a topic.

        All subscribers whose topic pattern matches will receive
        the message synchronously.

        Args:
            topic: Topic to publish on.
            message: Message to publish.

        Returns:
            Number of subscribers that received the message.
        """
        with self._lock:
            matching_subs = [s for s in self._subscriptions if s.matches(topic)]

        # Record in history
        self._message_history.append((topic, message))
        self._stats["messages_published"] += 1

        # Deliver to subscribers
        delivered = 0
        for sub in matching_subs:
            try:
                sub.handler(message)
                delivered += 1
            except Exception as e:
                logger.error(
                    "Error delivering message to %s (sub %s): %s",
                    sub.subscriber_id,
                    sub.subscription_id,
                    e,
                )
                self._stats["delivery_errors"] += 1

        self._stats["messages_delivered"] += delivered

        logger.debug(
            "Published message %s to topic '%s' (%d subscribers)",
            message.message_id,
            topic,
            delivered,
        )

        return delivered

    def get_history(
        self,
        topic_pattern: str | None = None,
        source_agent_id: str | None = None,
        message_type: MessageType | None = None,
        limit: int = 100,
    ) -> list[tuple[str, Message]]:
        """Get message history with optional filters.

        Args:
            topic_pattern: Filter by topic pattern (supports wildcards).
            source_agent_id: Filter by source agent ID.
            message_type: Filter by message type.
            limit: Maximum number of messages to return.

        Returns:
            List of (topic, message) tuples, newest first.
        """
        results = list(reversed(self._message_history))

        if topic_pattern:
            results = [(t, m) for t, m in results if fnmatch.fnmatch(t, topic_pattern)]

        if source_agent_id:
            results = [(t, m) for t, m in results if m.source_agent_id == source_agent_id]

        if message_type:
            results = [(t, m) for t, m in results if m.message_type == message_type]

        return results[:limit]

    def clear_history(self) -> None:
        """Clear all message history."""
        self._message_history.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get message bus statistics.

        Returns:
            Dictionary with bus statistics.
        """
        return {
            "subscriptions": len(self._subscriptions),
            "messages_published": self._stats["messages_published"],
            "messages_delivered": self._stats["messages_delivered"],
            "delivery_errors": self._stats["delivery_errors"],
            "history_size": len(self._message_history),
        }

    def reset(self) -> None:
        """Reset the message bus, clearing all subscriptions and history."""
        with self._lock:
            self._subscriptions.clear()
        self._message_history.clear()
        self._stats.clear()
        self._subscription_counter = 0
        logger.info("Message bus reset")
