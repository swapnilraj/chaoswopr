#!/usr/bin/env python3
"""MCP Server for ChaosWopr Chat Interface.

Exposes chaos engineering tools via Model Context Protocol for LLM interaction.
Implements 3-tier safety model: Read-Only, Design, Execute.
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class SafetyLevel(str, Enum):
    """Safety level for tools."""

    READ_ONLY = "read-only"  # No approval needed
    DESIGN = "design"  # Generates artifacts, no execution
    EXECUTE = "execute"  # Requires user approval


class ApprovalRequired(Exception):
    """Raised when a tool requires user approval before execution."""

    def __init__(self, tool_name: str, impact_summary: dict[str, Any]):
        self.tool_name = tool_name
        self.impact_summary = impact_summary
        super().__init__(f"Tool '{tool_name}' requires approval")


class ChaosWoprMCPServer:
    """MCP Server for ChaosWopr tools.

    Provides LLM-accessible tools for chaos engineering with built-in
    safety mechanisms and approval workflows.

    Example:
        >>> server = ChaosWoprMCPServer()
        >>> server.register_tools()
        >>> # Use with Claude Desktop or any MCP client
    """

    def __init__(
        self,
        max_blast_radius: float = 33.0,
        max_experiment_duration: int = 1800,  # 30 minutes
        max_cost_per_run: float = 1.00,
        require_approval_callback: Callable[[str, dict], bool] | None = None,
    ):
        """Initialize the MCP server.

        Args:
            max_blast_radius: Maximum percentage of nodes that can be affected.
            max_experiment_duration: Maximum experiment duration in seconds.
            max_cost_per_run: Maximum cost per experiment run in USD.
            require_approval_callback: Function to call for approval requests.
                If None, auto-approves all (use for testing only).
        """
        self.max_blast_radius = max_blast_radius
        self.max_experiment_duration = max_experiment_duration
        self.max_cost_per_run = max_cost_per_run
        self._require_approval = require_approval_callback or self._auto_approve

        # Tool registry
        self._tools: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _auto_approve(tool_name: str, impact: dict) -> bool:
        """Auto-approve all requests (TESTING ONLY)."""
        logger.warning(f"Auto-approving {tool_name} (testing mode)")
        return True

    def tool(
        self,
        name: str,
        description: str,
        safety_level: SafetyLevel,
        parameters: dict[str, Any],
    ):
        """Decorator to register a tool.

        Example:
            @server.tool(
                name="explain_scenario",
                description="Explain a chaos scenario in plain English",
                safety_level=SafetyLevel.READ_ONLY,
                parameters={
                    "scenario_name": {
                        "type": "string",
                        "description": "Name of the scenario"
                    }
                }
            )
            def explain_scenario(scenario_name: str) -> str:
                return f"Explanation of {scenario_name}..."
        """

        def decorator(func: Callable) -> Callable:
            self._tools[name] = {
                "function": func,
                "description": description,
                "safety_level": safety_level,
                "parameters": parameters,
            }
            return func

        return decorator

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool with safety checks.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments.

        Returns:
            Tool execution result.

        Raises:
            ApprovalRequired: If tool requires approval and user denies.
        """
        if tool_name not in self._tools:
            return {"error": f"Tool '{tool_name}' not found"}

        tool = self._tools[tool_name]
        safety_level = tool["safety_level"]

        # Execute read-only and design tools directly
        if safety_level in (SafetyLevel.READ_ONLY, SafetyLevel.DESIGN):
            try:
                result = tool["function"](**arguments)
                return {"status": "success", "result": result}
            except Exception as e:
                logger.exception(f"Tool {tool_name} failed")
                return {"status": "error", "error": str(e)}

        # Execute tools require approval
        if safety_level == SafetyLevel.EXECUTE:
            # Calculate impact
            impact = self._calculate_impact(tool_name, arguments)

            # Check hard limits
            violations = self._check_limits(impact)
            if violations:
                return {
                    "status": "error",
                    "error": "Safety limit violated",
                    "violations": violations,
                }

            # Request approval
            approved = self._require_approval(tool_name, impact)
            if not approved:
                return {
                    "status": "cancelled",
                    "message": "User denied approval",
                    "impact_summary": impact,
                }

            # Execute with approval
            try:
                result = tool["function"](**arguments)
                return {"status": "success", "result": result}
            except Exception as e:
                logger.exception(f"Tool {tool_name} failed")
                return {"status": "error", "error": str(e)}

        return {"error": "Unknown safety level"}

    def _calculate_impact(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate the impact of executing a tool.

        Returns:
            Impact summary with:
                - blast_radius_percent
                - estimated_duration_seconds
                - estimated_cost_usd
                - affected_resources
                - risks
        """
        impact = {
            "tool_name": tool_name,
            "blast_radius_percent": 0.0,
            "estimated_duration_seconds": 0,
            "estimated_cost_usd": 0.0,
            "affected_resources": [],
            "risks": [],
        }

        # Tool-specific impact calculations
        if tool_name == "deploy_testnet":
            num_validators = arguments.get("num_validators", 256)
            impact.update(
                {
                    "blast_radius_percent": 0.0,  # New testnet, no existing nodes
                    "estimated_duration_seconds": 300,  # ~5 min
                    "estimated_cost_usd": 0.0,  # Infrastructure only
                    "affected_resources": [f"{num_validators} validators", "2 execution clients", "2 consensus clients"],
                    "risks": ["Resource allocation"],
                }
            )

        elif tool_name == "run_experiment":
            impact.update(
                {
                    "blast_radius_percent": 20.0,  # Default scenario
                    "estimated_duration_seconds": 540,  # Default plan
                    "estimated_cost_usd": 0.05,  # LLM calls
                    "affected_resources": ["Testnet nodes", "Prometheus metrics"],
                    "risks": ["Temporary finality delay", "Increased CPU usage"],
                }
            )

        elif tool_name == "inject_fault":
            target_percent = arguments.get("target_percent", 20.0)
            duration = arguments.get("duration_seconds", 180)
            impact.update(
                {
                    "blast_radius_percent": target_percent,
                    "estimated_duration_seconds": duration,
                    "estimated_cost_usd": 0.0,
                    "affected_resources": [f"{target_percent}% of validators"],
                    "risks": ["Finality delay", "Reduced participation"],
                }
            )

        return impact

    def _check_limits(self, impact: dict[str, Any]) -> list[str]:
        """Check if impact violates safety limits.

        Returns:
            List of violations (empty if all checks pass).
        """
        violations = []

        if impact["blast_radius_percent"] > self.max_blast_radius:
            violations.append(
                f"Blast radius {impact['blast_radius_percent']}% exceeds limit {self.max_blast_radius}%"
            )

        if impact["estimated_duration_seconds"] > self.max_experiment_duration:
            violations.append(
                f"Duration {impact['estimated_duration_seconds']}s exceeds limit {self.max_experiment_duration}s"
            )

        if impact["estimated_cost_usd"] > self.max_cost_per_run:
            violations.append(
                f"Cost ${impact['estimated_cost_usd']} exceeds limit ${self.max_cost_per_run}"
            )

        return violations

    def list_tools(self) -> list[dict[str, Any]]:
        """List all available tools with their metadata."""
        return [
            {
                "name": name,
                "description": tool["description"],
                "safety_level": tool["safety_level"].value,
                "parameters": tool["parameters"],
            }
            for name, tool in self._tools.items()
        ]


def create_chaoswopr_mcp_server() -> ChaosWoprMCPServer:
    """Create and configure the ChaosWopr MCP server with all tools."""
    server = ChaosWoprMCPServer()

    # ========================================================================
    # 🟢 READ-ONLY TOOLS (Tier 1: No Approval Needed)
    # ========================================================================

    @server.tool(
        name="explain_scenario",
        description="Explain what a chaos engineering scenario does in plain English",
        safety_level=SafetyLevel.READ_ONLY,
        parameters={
            "scenario_name": {
                "type": "string",
                "description": "Name of the scenario (e.g., 'attestation_withholding')",
                "required": True,
            }
        },
    )
    def explain_scenario(scenario_name: str) -> str:
        """Explain a chaos scenario in plain English."""
        # In real implementation, load from scenario library
        explanations = {
            "attestation_withholding": """
**Attestation Withholding Attack**

This scenario simulates validators failing to submit attestations to the beacon chain.

**What happens:**
- Selected validators stop broadcasting attestations
- Network participation rate drops
- Finality may be delayed if participation < 66%

**Real-world analogs:**
- Prysm bug in May 2023 (caused similar symptoms)
- Network connectivity issues
- Validator misconfiguration

**Expected outcome:**
- If <33% withhold: Network maintains finality
- If >33% withhold: Finality delays occur
- Circuit breakers trigger if finality >10 minutes
            """,
            "network_partition": """
**Network Partition**

Simulates network split where some validators can't communicate.

**What happens:**
- Network divided into isolated groups
- Each group may form its own consensus
- Risk of chain splits

**Expected outcome:**
- Minority partition stops finalizing
- Majority partition continues
- Automatic recovery when partition heals
            """,
        }

        return explanations.get(
            scenario_name, f"Scenario '{scenario_name}' not found. Available: {list(explanations.keys())}"
        )

    @server.tool(
        name="analyze_experiment",
        description="Analyze a past experiment and explain what happened",
        safety_level=SafetyLevel.READ_ONLY,
        parameters={
            "experiment_id": {
                "type": "string",
                "description": "Experiment ID (e.g., '9a32f00c')",
                "required": True,
            }
        },
    )
    def analyze_experiment(experiment_id: str) -> dict:
        """Analyze experiment results."""
        # In real implementation, query from database
        return {
            "experiment_id": experiment_id,
            "summary": f"Experiment {experiment_id} tested attestation withholding with 20% of validators",
            "outcome": "success",
            "key_findings": [
                "Network maintained finality throughout",
                "Participation rate: 80% (above 66% threshold)",
                "No slashing events occurred",
                "Average block time: 12.1s (within normal range)",
            ],
            "metrics": {
                "participation_rate": 0.80,
                "finality_delay_slots": 0,
                "slashing_events": 0,
            },
            "explanation": """
The network successfully maintained consensus despite 20% of validators
withholding attestations. This is expected because the 2/3 supermajority
threshold (66%) was still met with 80% participation.

The circuit breakers did not trigger because finality was never delayed.
            """,
        }

    @server.tool(
        name="list_experiments",
        description="List past chaos engineering experiments",
        safety_level=SafetyLevel.READ_ONLY,
        parameters={
            "status": {
                "type": "string",
                "description": "Filter by status: 'all', 'success', 'failed', 'running'",
                "default": "all",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results",
                "default": 10,
            },
        },
    )
    def list_experiments(status: str = "all", limit: int = 10) -> list[dict]:
        """List past experiments."""
        # In real implementation, query from database
        experiments = [
            {
                "id": "9a32f00c",
                "scenario": "attestation_withholding",
                "status": "success",
                "timestamp": "2026-02-16T23:21:21Z",
                "duration_seconds": 540,
                "blast_radius_percent": 20.0,
            },
            {
                "id": "a446b411",
                "scenario": "attestation_withholding",
                "status": "success",
                "timestamp": "2026-02-16T23:04:08Z",
                "duration_seconds": 540,
                "blast_radius_percent": 20.0,
            },
        ]

        if status != "all":
            experiments = [e for e in experiments if e["status"] == status]

        return experiments[:limit]

    # ========================================================================
    # 🟡 DESIGN TOOLS (Tier 2: Generates Artifacts)
    # ========================================================================

    @server.tool(
        name="design_scenario",
        description="Generate a chaos scenario YAML from natural language description",
        safety_level=SafetyLevel.DESIGN,
        parameters={
            "description": {
                "type": "string",
                "description": "Natural language description of what you want to test",
                "required": True,
            },
            "max_blast_radius_percent": {
                "type": "number",
                "description": "Maximum percentage of nodes to affect",
                "default": 20.0,
            },
        },
    )
    def design_scenario(description: str, max_blast_radius_percent: float = 20.0) -> dict:
        """Design a scenario from natural language."""
        # In real implementation, use LLM to generate scenario
        return {
            "scenario_yaml": f"""
name: custom_scenario
description: {description}
hypothesis: Network maintains finality under {max_blast_radius_percent}% node failure
blast_radius:
  max_affected_percent: {max_blast_radius_percent}

fault_sequence:
  - time: 0s
    action: baseline
  - time: 60s
    action: inject_fault
    params:
      target_percent: {max_blast_radius_percent}
      duration: 180s

slo_thresholds:
  finality_delay_max: 5 epochs
  slashing_rate_max: 5%
            """,
            "estimated_impact": {
                "blast_radius": f"{max_blast_radius_percent}%",
                "duration": "~5 minutes",
                "cost": "~$0.05",
            },
            "safety_analysis": {
                "safe_to_run": max_blast_radius_percent <= 33.0,
                "warnings": [] if max_blast_radius_percent <= 20.0 else ["High blast radius"],
            },
        }

    @server.tool(
        name="estimate_impact",
        description="Estimate the impact of a scenario before running it",
        safety_level=SafetyLevel.DESIGN,
        parameters={
            "scenario_yaml": {
                "type": "string",
                "description": "Scenario YAML content",
                "required": True,
            }
        },
    )
    def estimate_impact(scenario_yaml: str) -> dict:
        """Estimate scenario impact."""
        # In real implementation, parse YAML and analyze
        return {
            "blast_radius": "Will affect 51/256 nodes (20%)",
            "duration": "~12 minutes total (540s experiment + overhead)",
            "cost": "~$0.05 in LLM API calls",
            "risks": [
                "Temporary finality delay possible",
                "Increased CPU usage on affected nodes",
                "No permanent data loss expected",
            ],
            "mitigation": [
                "Circuit breakers will trigger if finality >10min",
                "Auto-rollback after 180s",
                "Snapshots available for recovery",
            ],
        }

    # ========================================================================
    # 🔴 EXECUTE TOOLS (Tier 3: Requires Approval)
    # ========================================================================

    @server.tool(
        name="run_demo_experiment",
        description="Run a pre-approved demo experiment (attestation withholding, 20%, 3min)",
        safety_level=SafetyLevel.EXECUTE,
        parameters={
            "auto_cleanup": {
                "type": "boolean",
                "description": "Automatically clean up testnet after experiment",
                "default": True,
            }
        },
    )
    def run_demo_experiment(auto_cleanup: bool = True) -> dict:
        """Run a safe demo experiment."""
        # In real implementation, call ExperimentRunner
        return {
            "experiment_id": "demo_" + "abc123",
            "status": "running",
            "progress_url": "http://localhost:3000/experiments/demo_abc123",
            "estimated_completion": "~12 minutes",
            "message": "Experiment started. You can monitor progress in the dashboard.",
        }

    return server


if __name__ == "__main__":
    # Example usage
    server = create_chaoswopr_mcp_server()

    print("🔧 ChaosWopr MCP Server")
    print("=" * 60)
    print(f"Registered {len(server.list_tools())} tools:\n")

    for tool in server.list_tools():
        safety_icon = {"read-only": "🟢", "design": "🟡", "execute": "🔴"}[
            tool["safety_level"]
        ]
        print(f"{safety_icon} {tool['name']}")
        print(f"   {tool['description']}")
        print()
