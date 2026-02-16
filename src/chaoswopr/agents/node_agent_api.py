"""REST API for Node Agent orchestrator control.

Provides HTTP endpoints for the Orchestrator Agent to control node agents:
- GET /status - Get agent status
- POST /switch_mode - Switch between honest/adversarial modes
- POST /set_behavior - Set adversarial behavior
- POST /start - Start the agent
- POST /stop - Stop the agent
- GET /health - Health check

Also provides batch command functions for controlling multiple agents simultaneously.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from chaoswopr.agents.node_agent import AgentMode, NodeAgent
from chaoswopr.agents.node_agent_behaviors import (
    AttestationDelay,
    AttestationWithholding,
    BlockEquivocation,
    CoordinatedExit,
    TransactionCensoring,
)

logger = logging.getLogger(__name__)


class ModeSwitch(BaseModel):
    """Request to switch agent mode."""

    mode: str  # "honest" or "adversarial"


class BehaviorSet(BaseModel):
    """Request to set adversarial behavior."""

    behavior_type: str
    parameters: dict[str, Any]


class BatchCommand(str, Enum):
    """Batch command types."""

    SWITCH_MODE = "switch_mode"
    SET_BEHAVIOR = "set_behavior"
    START = "start"
    STOP = "stop"


class BatchCommandRequest(BaseModel):
    """Batch command request."""

    node_ids: list[str]
    command: BatchCommand
    parameters: dict[str, Any]


class NodeAgentAPI:
    """API server for a single node agent.

    Wraps a NodeAgent instance with HTTP endpoints for remote control
    by the Orchestrator Agent.
    """

    def __init__(self, agent: NodeAgent) -> None:
        """Initialize the API.

        Args:
            agent: NodeAgent instance to control.
        """
        self._agent = agent

    @property
    def agent(self) -> NodeAgent:
        """Get the underlying node agent."""
        return self._agent


def create_app(agent: NodeAgent) -> FastAPI:
    """Create a FastAPI application for a node agent.

    Args:
        agent: NodeAgent instance to control.

    Returns:
        FastAPI application.
    """
    app = FastAPI(title=f"NodeAgent API - {agent.node_id}")

    @app.get("/health")
    def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    @app.get("/status")
    def get_status() -> dict[str, Any]:
        """Get agent status.

        Returns:
            Status dictionary with agent state.
        """
        return agent.get_status()

    @app.post("/switch_mode")
    def switch_mode(request: ModeSwitch) -> dict[str, Any]:
        """Switch agent operating mode.

        Args:
            request: Mode switch request.

        Returns:
            Success response with new mode.
        """
        try:
            new_mode = AgentMode(request.mode)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid mode: {request.mode}. Must be 'honest' or 'adversarial'",
            )

        agent.switch_mode(new_mode)

        return {
            "success": True,
            "node_id": agent.node_id,
            "new_mode": new_mode.value,
        }

    @app.post("/set_behavior")
    def set_behavior(request: BehaviorSet) -> dict[str, Any]:
        """Set adversarial behavior.

        Args:
            request: Behavior configuration.

        Returns:
            Success response.

        Raises:
            HTTPException: If agent is not in adversarial mode.
        """
        if agent.mode != AgentMode.ADVERSARIAL:
            raise HTTPException(
                status_code=400,
                detail="Cannot set behavior in honest mode",
            )

        # Create behavior instance based on type
        behavior = _create_behavior(request.behavior_type, request.parameters)

        agent.set_behavior(behavior)

        return {
            "success": True,
            "node_id": agent.node_id,
            "behavior_type": request.behavior_type,
        }

    @app.post("/start")
    def start_agent() -> dict[str, Any]:
        """Start the agent.

        Returns:
            Success response.
        """
        agent.start()
        return {
            "success": True,
            "node_id": agent.node_id,
            "status": agent.status.value,
        }

    @app.post("/stop")
    def stop_agent() -> dict[str, Any]:
        """Stop the agent.

        Returns:
            Success response.
        """
        agent.stop()
        return {
            "success": True,
            "node_id": agent.node_id,
            "status": agent.status.value,
        }

    return app


def _create_behavior(behavior_type: str, parameters: dict[str, Any]) -> Any:
    """Create a behavior instance from type and parameters.

    Args:
        behavior_type: Behavior type name.
        parameters: Behavior-specific parameters.

    Returns:
        Behavior instance.

    Raises:
        ValueError: If behavior type is unknown.
    """
    behavior_map = {
        "attestation_withholding": AttestationWithholding,
        "attestation_delay": AttestationDelay,
        "block_equivocation": BlockEquivocation,
        "transaction_censoring": TransactionCensoring,
        "coordinated_exit": CoordinatedExit,
    }

    behavior_class = behavior_map.get(behavior_type)
    if not behavior_class:
        raise ValueError(f"Unknown behavior type: {behavior_type}")

    return behavior_class(**parameters)


# Batch command functions for orchestrator


def batch_mode_switch(agents: list[NodeAgent], mode: AgentMode) -> list[dict[str, Any]]:
    """Switch multiple agents to a new mode.

    Args:
        agents: List of agents to switch.
        mode: New mode.

    Returns:
        List of results for each agent.
    """
    results = []
    for agent in agents:
        try:
            agent.switch_mode(mode)
            results.append({
                "success": True,
                "node_id": agent.node_id,
                "new_mode": mode.value,
            })
        except Exception as e:
            results.append({
                "success": False,
                "node_id": agent.node_id,
                "error": str(e),
            })
            logger.error("Failed to switch mode for %s: %s", agent.node_id, e)

    return results


def batch_set_behavior(
    agents: list[NodeAgent],
    behavior_type: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Set behavior on multiple agents.

    Args:
        agents: List of agents to configure.
        behavior_type: Behavior type name.
        parameters: Behavior parameters.

    Returns:
        List of results for each agent.
    """
    results = []
    for agent in agents:
        try:
            if agent.mode != AgentMode.ADVERSARIAL:
                results.append({
                    "success": False,
                    "node_id": agent.node_id,
                    "error": "Agent not in adversarial mode",
                })
                continue

            behavior = _create_behavior(behavior_type, parameters)
            agent.set_behavior(behavior)

            results.append({
                "success": True,
                "node_id": agent.node_id,
                "behavior_type": behavior_type,
            })
        except Exception as e:
            results.append({
                "success": False,
                "node_id": agent.node_id,
                "error": str(e),
            })
            logger.error("Failed to set behavior for %s: %s", agent.node_id, e)

    return results


def batch_get_status(agents: list[NodeAgent]) -> list[dict[str, Any]]:
    """Get status from multiple agents.

    Args:
        agents: List of agents to query.

    Returns:
        List of status dictionaries.
    """
    return [agent.get_status() for agent in agents]
