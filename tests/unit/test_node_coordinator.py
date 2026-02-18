"""Tests for the NodeAgentCoordinator.

Tests fleet creation, honest/adversarial split, batch commands,
and message bus integration.
"""

from __future__ import annotations

import pytest

from chaoswopr.agents.messaging.coordinator import MessageCoordinator
from chaoswopr.agents.messaging.message_bus import MessageBus
from chaoswopr.agents.messaging.protocol import (
    AgentType,
    Command,
    CommandType,
    Response,
)
from chaoswopr.agents.node_agent import AgentMode, NodeAgentStatus
from chaoswopr.agents.node_coordinator import FleetConfig, NodeAgentCoordinator


class TestFleetConfig:
    """Tests for FleetConfig."""

    def test_default_config(self) -> None:
        config = FleetConfig()
        assert config.num_agents == 10
        assert config.adversarial_ratio == 0.3

    def test_custom_config(self) -> None:
        config = FleetConfig(
            num_agents=20,
            adversarial_ratio=0.2,
            beacon_api_urls=["http://beacon1:5052", "http://beacon2:5052"],
        )
        assert config.num_agents == 20
        assert config.adversarial_ratio == 0.2
        assert len(config.beacon_api_urls) == 2


class TestNodeAgentCoordinator:
    """Tests for the NodeAgentCoordinator."""

    def _make_coordinator(
        self,
        num_agents: int = 10,
        adversarial_ratio: float = 0.3,
        with_messaging: bool = False,
    ) -> NodeAgentCoordinator:
        fleet_config = FleetConfig(
            num_agents=num_agents,
            adversarial_ratio=adversarial_ratio,
        )

        msg_coordinator = None
        if with_messaging:
            bus = MessageBus()
            msg_coordinator = MessageCoordinator(bus)
            msg_coordinator.register_agent("orchestrator", AgentType.ORCHESTRATOR)

        return NodeAgentCoordinator(
            fleet_config=fleet_config,
            message_coordinator=msg_coordinator,
            dry_run=True,
        )

    def test_create_fleet(self) -> None:
        coordinator = self._make_coordinator(num_agents=10, adversarial_ratio=0.3)
        result = coordinator.create_fleet()

        assert result["total_agents"] == 10
        assert result["adversarial_count"] == 3
        assert result["honest_count"] == 7
        assert coordinator.fleet_created
        assert coordinator.fleet_size == 10

    def test_fleet_split(self) -> None:
        coordinator = self._make_coordinator(num_agents=10, adversarial_ratio=0.3)
        coordinator.create_fleet()

        honest, adversarial = coordinator.get_split()
        assert len(honest) == 7
        assert len(adversarial) == 3

        # Verify modes
        for agent in honest:
            assert agent.mode == AgentMode.HONEST
        for agent in adversarial:
            assert agent.mode == AgentMode.ADVERSARIAL

    def test_fleet_split_20_percent(self) -> None:
        coordinator = self._make_coordinator(num_agents=10, adversarial_ratio=0.2)
        coordinator.create_fleet()

        honest, adversarial = coordinator.get_split()
        assert len(honest) == 8
        assert len(adversarial) == 2

    def test_fleet_split_zero_adversarial(self) -> None:
        coordinator = self._make_coordinator(num_agents=5, adversarial_ratio=0.0)
        coordinator.create_fleet()

        honest, adversarial = coordinator.get_split()
        assert len(honest) == 5
        assert len(adversarial) == 0

    def test_create_fleet_twice_raises(self) -> None:
        coordinator = self._make_coordinator()
        coordinator.create_fleet()
        with pytest.raises(RuntimeError, match="already created"):
            coordinator.create_fleet()

    def test_start_all(self) -> None:
        coordinator = self._make_coordinator(num_agents=5)
        coordinator.create_fleet()
        result = coordinator.start_all()

        assert result["started"] == 5
        assert result["failed"] == 0

        for agent in coordinator.get_all_agents():
            assert agent.status == NodeAgentStatus.RUNNING

    def test_start_before_create_raises(self) -> None:
        coordinator = self._make_coordinator()
        with pytest.raises(RuntimeError, match="not created"):
            coordinator.start_all()

    def test_stop_all(self) -> None:
        coordinator = self._make_coordinator(num_agents=5)
        coordinator.create_fleet()
        coordinator.start_all()
        result = coordinator.stop_all()

        assert result["stopped"] == 5
        assert result["failed"] == 0

        for agent in coordinator.get_all_agents():
            assert agent.status == NodeAgentStatus.STOPPED

    def test_destroy_fleet(self) -> None:
        coordinator = self._make_coordinator(num_agents=5)
        coordinator.create_fleet()
        coordinator.start_all()
        coordinator.destroy_fleet()

        assert coordinator.fleet_size == 0
        assert not coordinator.fleet_created

    def test_switch_mode(self) -> None:
        coordinator = self._make_coordinator(num_agents=5, adversarial_ratio=0.0)
        coordinator.create_fleet()
        coordinator.start_all()

        # Switch first two to adversarial
        results = coordinator.switch_mode(
            agent_ids=["node-000", "node-001"],
            mode=AgentMode.ADVERSARIAL,
        )

        assert len(results) == 2
        assert all(r["success"] for r in results)
        assert coordinator.adversarial_count == 2
        assert coordinator.honest_count == 3

    def test_switch_mode_nonexistent_agent(self) -> None:
        coordinator = self._make_coordinator(num_agents=3)
        coordinator.create_fleet()

        results = coordinator.switch_mode(
            agent_ids=["nonexistent"],
            mode=AgentMode.ADVERSARIAL,
        )

        assert len(results) == 1
        assert not results[0]["success"]
        assert "not found" in results[0]["error"]

    def test_set_behavior(self) -> None:
        coordinator = self._make_coordinator(num_agents=5, adversarial_ratio=0.4)
        coordinator.create_fleet()
        coordinator.start_all()

        adversarial_ids = [a.node_id for a in coordinator.get_adversarial_agents()]
        results = coordinator.set_behavior(
            agent_ids=adversarial_ids,
            behavior_type="attestation_delay",
            parameters={"delay_seconds": 2.0},
        )

        assert all(r["success"] for r in results)

    def test_set_behavior_on_honest_fails(self) -> None:
        coordinator = self._make_coordinator(num_agents=5, adversarial_ratio=0.0)
        coordinator.create_fleet()
        coordinator.start_all()

        results = coordinator.set_behavior(
            agent_ids=["node-000"],
            behavior_type="attestation_withholding",
            parameters={"withhold_probability": 1.0},
        )

        assert not results[0]["success"]
        assert "not in adversarial mode" in results[0]["error"]

    def test_get_fleet_status(self) -> None:
        coordinator = self._make_coordinator(num_agents=5, adversarial_ratio=0.4)
        coordinator.create_fleet()
        coordinator.start_all()

        status = coordinator.get_fleet_status()
        assert status["fleet_created"]
        assert status["total_agents"] == 5
        assert status["running_agents"] == 5
        assert status["honest_count"] == 3
        assert status["adversarial_count"] == 2

    def test_get_agent(self) -> None:
        coordinator = self._make_coordinator(num_agents=3)
        coordinator.create_fleet()

        agent = coordinator.get_agent("node-000")
        assert agent is not None
        assert agent.node_id == "node-000"

        assert coordinator.get_agent("nonexistent") is None

    def test_get_agent_ids(self) -> None:
        coordinator = self._make_coordinator(num_agents=3)
        coordinator.create_fleet()

        ids = coordinator.get_agent_ids()
        assert len(ids) == 3
        assert "node-000" in ids
        assert "node-001" in ids
        assert "node-002" in ids


class TestNodeCoordinatorMessaging:
    """Tests for NodeAgentCoordinator with message bus integration."""

    def test_agents_registered_with_coordinator(self) -> None:
        bus = MessageBus()
        msg_coordinator = MessageCoordinator(bus)
        msg_coordinator.register_agent("orchestrator", AgentType.ORCHESTRATOR)

        fleet_config = FleetConfig(num_agents=3, adversarial_ratio=0.3)
        coordinator = NodeAgentCoordinator(
            fleet_config=fleet_config,
            message_coordinator=msg_coordinator,
            dry_run=True,
        )
        coordinator.create_fleet()

        # Verify agents are registered in the message coordinator
        fleet_status = msg_coordinator.get_fleet_status(agent_type=AgentType.NODE_AGENT)
        assert fleet_status["total_agents"] == 3

    def test_command_via_message_bus(self) -> None:
        bus = MessageBus()
        msg_coordinator = MessageCoordinator(bus)
        msg_coordinator.register_agent("orchestrator", AgentType.ORCHESTRATOR)

        fleet_config = FleetConfig(num_agents=3, adversarial_ratio=0.0)
        coordinator = NodeAgentCoordinator(
            fleet_config=fleet_config,
            message_coordinator=msg_coordinator,
            dry_run=True,
        )
        coordinator.create_fleet()
        coordinator.start_all()

        # Send command via message bus
        responses: list = []
        bus.subscribe(
            "agents.node_agent.node-000.responses",
            lambda msg: responses.append(msg),
            "test-listener",
        )

        msg_coordinator.send_command(
            source_agent_id="orchestrator",
            target_agent_id="node-000",
            command_type=CommandType.GET_STATUS,
        )

        assert len(responses) == 1
        assert responses[0].success

    def test_broadcast_switch_mode_via_bus(self) -> None:
        bus = MessageBus()
        msg_coordinator = MessageCoordinator(bus)
        msg_coordinator.register_agent("orchestrator", AgentType.ORCHESTRATOR)

        fleet_config = FleetConfig(num_agents=5, adversarial_ratio=0.0)
        coordinator = NodeAgentCoordinator(
            fleet_config=fleet_config,
            message_coordinator=msg_coordinator,
            dry_run=True,
        )
        coordinator.create_fleet()
        coordinator.start_all()

        # Broadcast switch mode to subset
        responses: list = []
        bus.subscribe(
            "agents.node_agent.*.responses",
            lambda msg: responses.append(msg),
            "test-listener",
        )

        msg_coordinator.broadcast_command(
            source_agent_id="orchestrator",
            agent_type=AgentType.NODE_AGENT,
            command_type=CommandType.GET_STATUS,
        )

        assert len(responses) == 5

    def test_destroy_fleet_unregisters_agents(self) -> None:
        bus = MessageBus()
        msg_coordinator = MessageCoordinator(bus)
        msg_coordinator.register_agent("orchestrator", AgentType.ORCHESTRATOR)

        fleet_config = FleetConfig(num_agents=3)
        coordinator = NodeAgentCoordinator(
            fleet_config=fleet_config,
            message_coordinator=msg_coordinator,
            dry_run=True,
        )
        coordinator.create_fleet()
        coordinator.destroy_fleet()

        node_agents = msg_coordinator.registry.get_agents_by_type(AgentType.NODE_AGENT)
        assert len(node_agents) == 0
