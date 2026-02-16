"""Unit tests for Node Agent REST API and orchestrator command interface.

Tests the HTTP API for controlling node agents, including switch_mode(),
get_status(), and batch commands.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from chaoswopr.agents.node_agent import AgentMode, NodeAgent, NodeAgentConfig
from chaoswopr.agents.node_agent_api import (
    BatchCommand,
    BatchCommandRequest,
    ModeSwitch,
    NodeAgentAPI,
    create_app,
)


class TestNodeAgentAPI:
    """Test Node Agent API server."""

    @pytest.fixture
    def agent(self) -> NodeAgent:
        """Create a test node agent."""
        config = NodeAgentConfig(
            node_id="validator-1",
            beacon_api_url="http://localhost:5052",
        )
        return NodeAgent(config=config, dry_run=True)

    @pytest.fixture
    def api(self, agent: NodeAgent) -> NodeAgentAPI:
        """Create a test API instance."""
        return NodeAgentAPI(agent=agent)

    @pytest.fixture
    def client(self, api: NodeAgentAPI) -> TestClient:
        """Create a test client."""
        app = create_app(api.agent)
        return TestClient(app, raise_server_exceptions=True)

    def test_api_creation(self, agent: NodeAgent) -> None:
        """Test API creation."""
        api = NodeAgentAPI(agent=agent)
        assert api.agent == agent

    def test_get_status(self, client: TestClient, agent: NodeAgent) -> None:
        """Test GET /status endpoint."""
        agent.start()

        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["node_id"] == "validator-1"
        assert data["mode"] == "honest"
        assert data["status"] == "running"

    def test_switch_mode(self, client: TestClient, agent: NodeAgent) -> None:
        """Test POST /switch_mode endpoint."""
        agent.start()

        response = client.post(
            "/switch_mode",
            json={"mode": "adversarial"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["new_mode"] == "adversarial"
        assert agent.mode == AgentMode.ADVERSARIAL

    def test_switch_mode_invalid(self, client: TestClient, agent: NodeAgent) -> None:
        """Test switch_mode with invalid mode."""
        agent.start()

        response = client.post(
            "/switch_mode",
            json={"mode": "invalid_mode"},
        )

        assert response.status_code == 422  # Validation error

    def test_set_behavior(self, client: TestClient, agent: NodeAgent) -> None:
        """Test POST /set_behavior endpoint."""
        agent.start()
        agent.switch_mode(AgentMode.ADVERSARIAL)

        response = client.post(
            "/set_behavior",
            json={
                "behavior_type": "attestation_withholding",
                "parameters": {"withhold_probability": 0.5},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["behavior_type"] == "attestation_withholding"

    def test_set_behavior_honest_mode(self, client: TestClient, agent: NodeAgent) -> None:
        """Test that set_behavior fails in honest mode."""
        agent.start()

        response = client.post(
            "/set_behavior",
            json={
                "behavior_type": "attestation_withholding",
                "parameters": {"withhold_probability": 0.5},
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "Cannot set behavior in honest mode"

    def test_health_check(self, client: TestClient) -> None:
        """Test GET /health endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_start_agent(self, client: TestClient, agent: NodeAgent) -> None:
        """Test POST /start endpoint."""
        response = client.post("/start")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert agent.status.value == "running"

    def test_stop_agent(self, client: TestClient, agent: NodeAgent) -> None:
        """Test POST /stop endpoint."""
        agent.start()

        response = client.post("/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert agent.status.value == "stopped"


class TestBatchCommands:
    """Test batch command functionality."""

    @pytest.fixture
    def agents(self) -> list[NodeAgent]:
        """Create multiple test agents."""
        agents = []
        for i in range(3):
            config = NodeAgentConfig(
                node_id=f"validator-{i}",
                beacon_api_url=f"http://localhost:{5052 + i}",
                proxy_port=6000 + i,
            )
            agent = NodeAgent(config=config, dry_run=True)
            agent.start()
            agents.append(agent)
        return agents

    def test_batch_mode_switch(self, agents: list[NodeAgent]) -> None:
        """Test batch mode switching."""
        from chaoswopr.agents.node_agent_api import batch_mode_switch

        # Switch all to adversarial
        results = batch_mode_switch(
            agents=agents,
            mode=AgentMode.ADVERSARIAL,
        )

        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert all(r["new_mode"] == "adversarial" for r in results)
        assert all(agent.mode == AgentMode.ADVERSARIAL for agent in agents)

    def test_batch_set_behavior(self, agents: list[NodeAgent]) -> None:
        """Test batch behavior setting."""
        from chaoswopr.agents.node_agent_api import batch_set_behavior

        # Switch all to adversarial first
        for agent in agents:
            agent.switch_mode(AgentMode.ADVERSARIAL)

        # Set behavior on all
        results = batch_set_behavior(
            agents=agents,
            behavior_type="attestation_withholding",
            parameters={"withhold_probability": 0.8},
        )

        assert len(results) == 3
        assert all(r["success"] for r in results)

    def test_batch_get_status(self, agents: list[NodeAgent]) -> None:
        """Test batch status retrieval."""
        from chaoswopr.agents.node_agent_api import batch_get_status

        statuses = batch_get_status(agents=agents)

        assert len(statuses) == 3
        assert all(s["node_id"].startswith("validator-") for s in statuses)
        assert all(s["status"] == "running" for s in statuses)

    def test_batch_command_request(self) -> None:
        """Test BatchCommandRequest model."""
        request = BatchCommandRequest(
            node_ids=["validator-1", "validator-2"],
            command=BatchCommand.SWITCH_MODE,
            parameters={"mode": "adversarial"},
        )

        assert len(request.node_ids) == 2
        assert request.command == BatchCommand.SWITCH_MODE
        assert request.parameters["mode"] == "adversarial"


class TestModeSwitch:
    """Test ModeSwitch request model."""

    def test_mode_switch_valid(self) -> None:
        """Test valid mode switch request."""
        request = ModeSwitch(mode="adversarial")
        assert request.mode == "adversarial"

    def test_mode_switch_enum(self) -> None:
        """Test mode switch with enum."""
        request = ModeSwitch(mode=AgentMode.HONEST.value)
        assert request.mode == "honest"


class TestAPIIntegration:
    """Integration tests for the API."""

    def test_full_workflow(self) -> None:
        """Test a complete workflow: start, switch mode, set behavior, stop."""
        config = NodeAgentConfig(
            node_id="validator-test",
            beacon_api_url="http://localhost:5052",
        )
        agent = NodeAgent(config=config, dry_run=True)
        app = create_app(agent)
        client = TestClient(app, raise_server_exceptions=True)

        # 1. Start agent
        response = client.post("/start")
        assert response.status_code == 200
        assert agent.status.value == "running"

        # 2. Check status
        response = client.get("/status")
        assert response.status_code == 200
        assert response.json()["mode"] == "honest"

        # 3. Switch to adversarial
        response = client.post("/switch_mode", json={"mode": "adversarial"})
        assert response.status_code == 200
        assert agent.mode == AgentMode.ADVERSARIAL

        # 4. Set behavior
        response = client.post(
            "/set_behavior",
            json={
                "behavior_type": "attestation_delay",
                "parameters": {"delay_seconds": 1.0},
            },
        )
        assert response.status_code == 200

        # 5. Check status again
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "adversarial"
        assert data["status"] == "running"

        # 6. Stop agent
        response = client.post("/stop")
        assert response.status_code == 200
        assert agent.status.value == "stopped"

    def test_concurrent_requests(self) -> None:
        """Test handling concurrent requests."""
        config = NodeAgentConfig(
            node_id="validator-concurrent",
            beacon_api_url="http://localhost:5052",
        )
        agent = NodeAgent(config=config, dry_run=True)
        app = create_app(agent)
        client = TestClient(app, raise_server_exceptions=True)

        agent.start()

        # Make multiple concurrent status requests
        responses = []
        for _ in range(10):
            response = client.get("/status")
            responses.append(response)

        assert all(r.status_code == 200 for r in responses)
        assert all(r.json()["node_id"] == "validator-concurrent" for r in responses)
