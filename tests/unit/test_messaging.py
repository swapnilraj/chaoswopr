"""Tests for agent messaging infrastructure.

Tests the message protocol, message bus, and coordinator components.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

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
from chaoswopr.agents.messaging.message_bus import MessageBus, Subscription
from chaoswopr.agents.messaging.coordinator import (
    AgentRegistry,
    AgentState,
    MessageCoordinator,
)


# ---- Protocol Tests ----

class TestMessage:
    """Tests for the base Message class."""

    def test_message_creation(self) -> None:
        msg = Message(
            message_type=MessageType.EVENT,
            source_agent_id="test-agent",
        )
        assert msg.message_type == MessageType.EVENT
        assert msg.source_agent_id == "test-agent"
        assert msg.target_agent_id is None
        assert msg.message_id is not None
        assert msg.timestamp is not None

    def test_message_to_dict(self) -> None:
        msg = Message(
            message_type=MessageType.COMMAND,
            source_agent_id="orch-1",
            target_agent_id="node-1",
        )
        d = msg.to_dict()
        assert d["message_type"] == "command"
        assert d["source_agent_id"] == "orch-1"
        assert d["target_agent_id"] == "node-1"
        assert "message_id" in d
        assert "timestamp" in d


class TestCommand:
    """Tests for Command messages."""

    def test_command_creation(self) -> None:
        cmd = Command(
            source_agent_id="orch-1",
            target_agent_id="node-1",
            command_type=CommandType.SWITCH_MODE,
            parameters={"mode": "adversarial"},
        )
        assert cmd.message_type == MessageType.COMMAND
        assert cmd.command_type == CommandType.SWITCH_MODE
        assert cmd.parameters == {"mode": "adversarial"}

    def test_command_to_dict(self) -> None:
        cmd = Command(
            source_agent_id="orch-1",
            target_agent_id="node-1",
            command_type=CommandType.SET_BEHAVIOR,
            parameters={"behavior_type": "attestation_withholding"},
        )
        d = cmd.to_dict()
        assert d["command_type"] == "set_behavior"
        assert d["parameters"]["behavior_type"] == "attestation_withholding"

    def test_command_timeout(self) -> None:
        cmd = Command(
            source_agent_id="orch-1",
            command_type=CommandType.START_EXPERIMENT,
            timeout_seconds=60.0,
        )
        assert cmd.timeout_seconds == 60.0

    def test_all_command_types(self) -> None:
        """Verify all command types can be instantiated."""
        for cmd_type in CommandType:
            cmd = Command(
                source_agent_id="test",
                command_type=cmd_type,
            )
            assert cmd.command_type == cmd_type


class TestResponse:
    """Tests for Response messages."""

    def test_success_response(self) -> None:
        resp = Response(
            source_agent_id="node-1",
            target_agent_id="orch-1",
            success=True,
            result={"new_mode": "adversarial"},
        )
        assert resp.message_type == MessageType.RESPONSE
        assert resp.success is True
        assert resp.result == {"new_mode": "adversarial"}
        assert resp.error_message is None

    def test_failure_response(self) -> None:
        resp = Response(
            source_agent_id="node-1",
            target_agent_id="orch-1",
            success=False,
            error_message="Agent not running",
        )
        assert resp.success is False
        assert resp.error_message == "Agent not running"

    def test_response_to_dict(self) -> None:
        resp = Response(
            source_agent_id="node-1",
            success=True,
            result={"status": "ok"},
        )
        d = resp.to_dict()
        assert d["success"] is True
        assert d["result"] == {"status": "ok"}


class TestStatusUpdate:
    """Tests for StatusUpdate messages."""

    def test_status_update(self) -> None:
        update = StatusUpdate(
            source_agent_id="node-1",
            agent_type=AgentType.NODE_AGENT,
            agent_state="running",
            metrics={"uptime": 120.0},
        )
        assert update.message_type == MessageType.STATUS_UPDATE
        assert update.agent_type == AgentType.NODE_AGENT
        assert update.agent_state == "running"
        assert update.metrics == {"uptime": 120.0}

    def test_status_update_to_dict(self) -> None:
        update = StatusUpdate(
            source_agent_id="observer-1",
            agent_type=AgentType.OBSERVER,
            agent_state="observing",
        )
        d = update.to_dict()
        assert d["agent_type"] == "observer"
        assert d["agent_state"] == "observing"


class TestEvent:
    """Tests for Event messages."""

    def test_event_creation(self) -> None:
        event = Event(
            source_agent_id="observer-1",
            event_type=EventType.ANOMALY_DETECTED,
            severity="warning",
            details={"metric": "finality_delay", "z_score": 4.5},
        )
        assert event.message_type == MessageType.EVENT
        assert event.event_type == EventType.ANOMALY_DETECTED
        assert event.severity == "warning"
        assert event.details["z_score"] == 4.5

    def test_event_to_dict(self) -> None:
        event = Event(
            source_agent_id="orch-1",
            event_type=EventType.EXPERIMENT_STARTED,
            details={"scenario": "finality_loss"},
        )
        d = event.to_dict()
        assert d["event_type"] == "experiment_started"
        assert d["severity"] == "info"

    def test_all_event_types(self) -> None:
        """Verify all event types can be instantiated."""
        for ev_type in EventType:
            event = Event(
                source_agent_id="test",
                event_type=ev_type,
            )
            assert event.event_type == ev_type


# ---- Message Bus Tests ----

class TestMessageBus:
    """Tests for the MessageBus."""

    def test_subscribe_and_publish(self) -> None:
        bus = MessageBus()
        received: list[Message] = []

        bus.subscribe("test.topic", lambda msg: received.append(msg), "sub-1")

        msg = Message(message_type=MessageType.EVENT, source_agent_id="test")
        delivered = bus.publish("test.topic", msg)

        assert delivered == 1
        assert len(received) == 1
        assert received[0].source_agent_id == "test"

    def test_wildcard_subscription(self) -> None:
        bus = MessageBus()
        received: list[Message] = []

        bus.subscribe("agents.node.*.commands", lambda msg: received.append(msg), "sub-1")

        msg1 = Message(message_type=MessageType.COMMAND, source_agent_id="orch")
        msg2 = Message(message_type=MessageType.COMMAND, source_agent_id="orch")

        bus.publish("agents.node.node-001.commands", msg1)
        bus.publish("agents.node.node-002.commands", msg2)
        bus.publish("agents.observer.obs-1.commands", Message(
            message_type=MessageType.COMMAND, source_agent_id="orch"
        ))

        assert len(received) == 2

    def test_multiple_subscribers(self) -> None:
        bus = MessageBus()
        received_a: list[Message] = []
        received_b: list[Message] = []

        bus.subscribe("shared.topic", lambda msg: received_a.append(msg), "sub-a")
        bus.subscribe("shared.topic", lambda msg: received_b.append(msg), "sub-b")

        msg = Message(message_type=MessageType.EVENT, source_agent_id="test")
        delivered = bus.publish("shared.topic", msg)

        assert delivered == 2
        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_unsubscribe(self) -> None:
        bus = MessageBus()
        received: list[Message] = []

        sub_id = bus.subscribe("topic", lambda msg: received.append(msg), "sub-1")

        msg1 = Message(message_type=MessageType.EVENT, source_agent_id="test")
        bus.publish("topic", msg1)
        assert len(received) == 1

        bus.unsubscribe(sub_id)

        msg2 = Message(message_type=MessageType.EVENT, source_agent_id="test")
        bus.publish("topic", msg2)
        assert len(received) == 1  # No new messages

    def test_unsubscribe_all(self) -> None:
        bus = MessageBus()
        received: list[Message] = []

        bus.subscribe("topic-a", lambda msg: received.append(msg), "agent-1")
        bus.subscribe("topic-b", lambda msg: received.append(msg), "agent-1")
        bus.subscribe("topic-a", lambda msg: None, "agent-2")

        removed = bus.unsubscribe_all("agent-1")
        assert removed == 2
        assert bus.subscription_count == 1

    def test_no_matching_subscribers(self) -> None:
        bus = MessageBus()
        msg = Message(message_type=MessageType.EVENT, source_agent_id="test")
        delivered = bus.publish("no.subscribers.topic", msg)
        assert delivered == 0

    def test_message_history(self) -> None:
        bus = MessageBus()
        bus.subscribe("topic", lambda _: None, "sub-1")

        for i in range(5):
            msg = Message(
                message_type=MessageType.EVENT,
                source_agent_id=f"agent-{i}",
            )
            bus.publish("topic", msg)

        history = bus.get_history()
        assert len(history) == 5

    def test_history_filtering(self) -> None:
        bus = MessageBus()

        msg1 = Message(message_type=MessageType.EVENT, source_agent_id="agent-a")
        msg2 = Message(message_type=MessageType.COMMAND, source_agent_id="agent-b")

        bus.publish("events.topic", msg1)
        bus.publish("commands.topic", msg2)

        events_only = bus.get_history(message_type=MessageType.EVENT)
        assert len(events_only) == 1
        assert events_only[0][1].source_agent_id == "agent-a"

        by_source = bus.get_history(source_agent_id="agent-b")
        assert len(by_source) == 1

    def test_handler_error_does_not_crash(self) -> None:
        bus = MessageBus()
        received: list[Message] = []

        def bad_handler(msg: Message) -> None:
            raise ValueError("Handler error")

        bus.subscribe("topic", bad_handler, "bad-sub")
        bus.subscribe("topic", lambda msg: received.append(msg), "good-sub")

        msg = Message(message_type=MessageType.EVENT, source_agent_id="test")
        delivered = bus.publish("topic", msg)

        # Good subscriber still gets the message
        assert len(received) == 1
        assert bus.get_stats()["delivery_errors"] == 1

    def test_stats(self) -> None:
        bus = MessageBus()
        bus.subscribe("topic", lambda _: None, "sub-1")

        msg = Message(message_type=MessageType.EVENT, source_agent_id="test")
        bus.publish("topic", msg)

        stats = bus.get_stats()
        assert stats["subscriptions"] == 1
        assert stats["messages_published"] == 1
        assert stats["messages_delivered"] == 1

    def test_reset(self) -> None:
        bus = MessageBus()
        bus.subscribe("topic", lambda _: None, "sub-1")
        bus.publish("topic", Message(
            message_type=MessageType.EVENT, source_agent_id="test"
        ))

        bus.reset()

        assert bus.subscription_count == 0
        assert bus.message_count == 0
        assert len(bus.get_history()) == 0


# ---- Subscription Tests ----

class TestSubscription:
    """Tests for Subscription pattern matching."""

    def test_exact_match(self) -> None:
        sub = Subscription(
            subscription_id="sub-1",
            topic_pattern="exact.topic",
            handler=lambda _: None,
            subscriber_id="test",
        )
        assert sub.matches("exact.topic")
        assert not sub.matches("exact.other")

    def test_wildcard_match(self) -> None:
        sub = Subscription(
            subscription_id="sub-1",
            topic_pattern="agents.node.*.commands",
            handler=lambda _: None,
            subscriber_id="test",
        )
        assert sub.matches("agents.node.node-001.commands")
        assert sub.matches("agents.node.node-999.commands")
        assert not sub.matches("agents.observer.obs-1.commands")

    def test_star_all_match(self) -> None:
        sub = Subscription(
            subscription_id="sub-1",
            topic_pattern="agents.*.events",
            handler=lambda _: None,
            subscriber_id="test",
        )
        assert sub.matches("agents.node.events")
        assert sub.matches("agents.observer.events")


# ---- Agent Registry Tests ----

class TestAgentRegistry:
    """Tests for the AgentRegistry."""

    def test_register_agent(self) -> None:
        registry = AgentRegistry()
        state = registry.register("node-1", AgentType.NODE_AGENT)
        assert state.agent_id == "node-1"
        assert state.agent_type == AgentType.NODE_AGENT
        assert state.state == "registered"
        assert registry.agent_count == 1

    def test_register_duplicate_raises(self) -> None:
        registry = AgentRegistry()
        registry.register("node-1", AgentType.NODE_AGENT)
        with pytest.raises(ValueError, match="already registered"):
            registry.register("node-1", AgentType.NODE_AGENT)

    def test_unregister(self) -> None:
        registry = AgentRegistry()
        registry.register("node-1", AgentType.NODE_AGENT)
        assert registry.unregister("node-1")
        assert registry.agent_count == 0
        assert not registry.unregister("node-1")  # Already removed

    def test_get_agent(self) -> None:
        registry = AgentRegistry()
        registry.register("orch-1", AgentType.ORCHESTRATOR)
        agent = registry.get_agent("orch-1")
        assert agent is not None
        assert agent.agent_type == AgentType.ORCHESTRATOR
        assert registry.get_agent("nonexistent") is None

    def test_get_agents_by_type(self) -> None:
        registry = AgentRegistry()
        registry.register("node-1", AgentType.NODE_AGENT)
        registry.register("node-2", AgentType.NODE_AGENT)
        registry.register("orch-1", AgentType.ORCHESTRATOR)

        nodes = registry.get_agents_by_type(AgentType.NODE_AGENT)
        assert len(nodes) == 2

        orchestrators = registry.get_agents_by_type(AgentType.ORCHESTRATOR)
        assert len(orchestrators) == 1

    def test_update_state(self) -> None:
        registry = AgentRegistry()
        registry.register("node-1", AgentType.NODE_AGENT)
        registry.update_state("node-1", "running", {"uptime": 100})

        agent = registry.get_agent("node-1")
        assert agent is not None
        assert agent.state == "running"
        assert agent.metadata["uptime"] == 100

    def test_update_nonexistent_agent(self) -> None:
        registry = AgentRegistry()
        assert not registry.update_state("nonexistent", "running")

    def test_clear(self) -> None:
        registry = AgentRegistry()
        registry.register("node-1", AgentType.NODE_AGENT)
        registry.register("node-2", AgentType.NODE_AGENT)
        registry.clear()
        assert registry.agent_count == 0


# ---- Message Coordinator Tests ----

class TestMessageCoordinator:
    """Tests for the MessageCoordinator."""

    def _make_coordinator(self) -> MessageCoordinator:
        bus = MessageBus()
        return MessageCoordinator(bus)

    def test_register_agent(self) -> None:
        coord = self._make_coordinator()
        state = coord.register_agent("orch-1", AgentType.ORCHESTRATOR)
        assert state.agent_id == "orch-1"
        assert coord.registry.agent_count == 1

    def test_unregister_agent(self) -> None:
        coord = self._make_coordinator()
        coord.register_agent("node-1", AgentType.NODE_AGENT)
        assert coord.unregister_agent("node-1")
        assert coord.registry.agent_count == 0

    def test_send_command_to_registered_agent(self) -> None:
        coord = self._make_coordinator()
        received_commands: list[Command] = []

        def handle_cmd(cmd: Command) -> Response:
            received_commands.append(cmd)
            return Response(
                source_agent_id="node-1",
                target_agent_id=cmd.source_agent_id,
                success=True,
                result={"done": True},
            )

        coord.register_agent("orch-1", AgentType.ORCHESTRATOR)
        coord.register_agent("node-1", AgentType.NODE_AGENT, command_handler=handle_cmd)

        cmd = coord.send_command(
            source_agent_id="orch-1",
            target_agent_id="node-1",
            command_type=CommandType.SWITCH_MODE,
            parameters={"mode": "adversarial"},
        )

        assert len(received_commands) == 1
        assert received_commands[0].command_type == CommandType.SWITCH_MODE
        assert received_commands[0].parameters["mode"] == "adversarial"

    def test_send_command_to_unregistered_raises(self) -> None:
        coord = self._make_coordinator()
        coord.register_agent("orch-1", AgentType.ORCHESTRATOR)

        with pytest.raises(ValueError, match="not registered"):
            coord.send_command(
                source_agent_id="orch-1",
                target_agent_id="nonexistent",
                command_type=CommandType.GET_STATUS,
            )

    def test_broadcast_command(self) -> None:
        coord = self._make_coordinator()
        received: dict[str, list[Command]] = {"node-1": [], "node-2": [], "node-3": []}

        def make_handler(agent_id: str) -> Callable:
            def handler(cmd: Command) -> Response:
                received[agent_id].append(cmd)
                return Response(
                    source_agent_id=agent_id,
                    success=True,
                )
            return handler

        coord.register_agent("orch-1", AgentType.ORCHESTRATOR)
        for node_id in ["node-1", "node-2", "node-3"]:
            coord.register_agent(
                node_id, AgentType.NODE_AGENT, command_handler=make_handler(node_id)
            )

        commands = coord.broadcast_command(
            source_agent_id="orch-1",
            agent_type=AgentType.NODE_AGENT,
            command_type=CommandType.SWITCH_MODE,
            parameters={"mode": "honest"},
        )

        assert len(commands) == 3
        for node_id in ["node-1", "node-2", "node-3"]:
            assert len(received[node_id]) == 1

    def test_broadcast_to_subset(self) -> None:
        coord = self._make_coordinator()
        received: dict[str, list[Command]] = {"node-1": [], "node-2": [], "node-3": []}

        def make_handler(agent_id: str) -> Callable:
            def handler(cmd: Command) -> Response:
                received[agent_id].append(cmd)
                return Response(source_agent_id=agent_id, success=True)
            return handler

        coord.register_agent("orch-1", AgentType.ORCHESTRATOR)
        for node_id in ["node-1", "node-2", "node-3"]:
            coord.register_agent(
                node_id, AgentType.NODE_AGENT, command_handler=make_handler(node_id)
            )

        commands = coord.broadcast_command(
            source_agent_id="orch-1",
            agent_type=AgentType.NODE_AGENT,
            command_type=CommandType.SET_BEHAVIOR,
            target_agent_ids=["node-1", "node-3"],
        )

        assert len(commands) == 2
        assert len(received["node-1"]) == 1
        assert len(received["node-2"]) == 0
        assert len(received["node-3"]) == 1

    def test_emit_event(self) -> None:
        coord = self._make_coordinator()
        received_events: list[Event] = []

        coord.register_agent("observer-1", AgentType.OBSERVER)

        coord.subscribe_to_events(
            subscriber_id="listener-1",
            handler=lambda ev: received_events.append(ev),
            agent_type=AgentType.OBSERVER,
        )

        coord.emit_event(
            source_agent_id="observer-1",
            event_type=EventType.ANOMALY_DETECTED,
            severity="warning",
            details={"metric": "finality_delay", "value": 600.0},
        )

        assert len(received_events) == 1
        assert received_events[0].event_type == EventType.ANOMALY_DETECTED
        assert received_events[0].severity == "warning"

    def test_emit_experiment_scoped_event(self) -> None:
        coord = self._make_coordinator()
        received_events: list[Event] = []

        coord.register_agent("orch-1", AgentType.ORCHESTRATOR)

        coord.subscribe_to_events(
            subscriber_id="listener-1",
            handler=lambda ev: received_events.append(ev),
            experiment_id="exp-001",
        )

        coord.emit_event(
            source_agent_id="orch-1",
            event_type=EventType.EXPERIMENT_STARTED,
            experiment_id="exp-001",
            details={"scenario": "finality_loss"},
        )

        assert len(received_events) == 1
        assert received_events[0].experiment_id == "exp-001"

    def test_send_status_update(self) -> None:
        coord = self._make_coordinator()
        coord.register_agent("node-1", AgentType.NODE_AGENT)

        update = coord.send_status_update(
            agent_id="node-1",
            agent_state="running",
            metrics={"uptime": 300.0},
        )

        assert update.agent_state == "running"

        # Registry should be updated
        agent = coord.registry.get_agent("node-1")
        assert agent is not None
        assert agent.state == "running"

    def test_get_fleet_status(self) -> None:
        coord = self._make_coordinator()
        coord.register_agent("orch-1", AgentType.ORCHESTRATOR)
        coord.register_agent("node-1", AgentType.NODE_AGENT)
        coord.register_agent("node-2", AgentType.NODE_AGENT)
        coord.register_agent("observer-1", AgentType.OBSERVER)

        status = coord.get_fleet_status()
        assert status["total_agents"] == 4
        assert status["by_type"]["node_agent"] == 2
        assert status["by_type"]["orchestrator"] == 1
        assert status["by_type"]["observer"] == 1

    def test_get_fleet_status_by_type(self) -> None:
        coord = self._make_coordinator()
        coord.register_agent("node-1", AgentType.NODE_AGENT)
        coord.register_agent("node-2", AgentType.NODE_AGENT)
        coord.register_agent("orch-1", AgentType.ORCHESTRATOR)

        status = coord.get_fleet_status(agent_type=AgentType.NODE_AGENT)
        assert status["total_agents"] == 2

    def test_command_response_correlation(self) -> None:
        coord = self._make_coordinator()
        responses: list[Message] = []

        def handle_cmd(cmd: Command) -> Response:
            return Response(
                source_agent_id="node-1",
                success=True,
                result={"mode": "adversarial"},
            )

        coord.register_agent("orch-1", AgentType.ORCHESTRATOR)
        coord.register_agent("node-1", AgentType.NODE_AGENT, command_handler=handle_cmd)

        # Subscribe to responses
        coord.bus.subscribe(
            "agents.node_agent.node-1.responses",
            lambda msg: responses.append(msg),
            "orch-1",
        )

        cmd = coord.send_command(
            source_agent_id="orch-1",
            target_agent_id="node-1",
            command_type=CommandType.SWITCH_MODE,
        )

        assert len(responses) == 1
        assert responses[0].correlation_id == cmd.message_id

    def test_reset(self) -> None:
        coord = self._make_coordinator()
        coord.register_agent("node-1", AgentType.NODE_AGENT)
        coord.reset()
        assert coord.registry.agent_count == 0
        assert coord.bus.subscription_count == 0


# Need Callable type for test helpers
from typing import Callable
