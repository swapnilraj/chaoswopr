"""Scenario loader for experiment execution.

Loads scenario YAML files and converts them to the dictionary format
expected by the ExperimentRunner. Also provides programmatic scenario
builders for common chaos engineering patterns.

The loader integrates with the existing scenario validator to ensure
all loaded scenarios are valid before execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from chaoswopr.scenarios.validator import (
    ValidationResult,
    parse_time_string,
    validate_semantic,
)

logger = logging.getLogger(__name__)


@dataclass
class ScenarioDefinition:
    """A fully parsed scenario ready for experiment execution.

    Attributes:
        name: Scenario name.
        hypothesis: Hypothesis statement.
        fault_sequence: List of fault injection steps.
        slo_thresholds: SLO threshold definitions.
        blast_radius: Blast radius configuration.
        network_config: Network configuration (optional).
        success_criteria: Success criteria description.
        tags: Scenario tags.
        timeout: Timeout string.
        raw: The raw parsed YAML dictionary.
    """

    name: str = ""
    hypothesis: str = ""
    fault_sequence: list[dict[str, Any]] = field(default_factory=list)
    slo_thresholds: dict[str, Any] = field(default_factory=dict)
    blast_radius: dict[str, Any] = field(default_factory=dict)
    network_config: dict[str, Any] = field(default_factory=dict)
    success_criteria: str = ""
    tags: list[str] = field(default_factory=list)
    timeout: str = "15m"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for ExperimentRunner."""
        return {
            "name": self.name,
            "hypothesis": self.hypothesis,
            "fault_sequence": self.fault_sequence,
            "slo_thresholds": self.slo_thresholds,
            "blast_radius": self.blast_radius,
            "network_config": self.network_config,
            "success_criteria": self.success_criteria,
            "tags": self.tags,
            "timeout": self.timeout,
        }


def load_scenario_file(path: Path) -> ScenarioDefinition:
    """Load a scenario from a YAML file.

    Args:
        path: Path to the scenario YAML file.

    Returns:
        ScenarioDefinition parsed from the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        ValueError: If the scenario fails semantic validation.
    """
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Scenario file must contain a YAML mapping, got {type(raw).__name__}")

    # Semantic validation (skip schema validation since it needs the schema file)
    validation = validate_semantic(raw)
    if not validation.valid:
        raise ValueError(
            f"Scenario validation failed: {'; '.join(validation.errors)}"
        )

    return _parse_scenario(raw)


def load_scenario_string(yaml_content: str) -> ScenarioDefinition:
    """Load a scenario from a YAML string.

    Args:
        yaml_content: YAML content as a string.

    Returns:
        ScenarioDefinition parsed from the string.

    Raises:
        yaml.YAMLError: If the content is not valid YAML.
        ValueError: If the scenario fails validation.
    """
    raw = yaml.safe_load(yaml_content)

    if not isinstance(raw, dict):
        raise ValueError(f"Scenario must be a YAML mapping, got {type(raw).__name__}")

    return _parse_scenario(raw)


def _parse_scenario(raw: dict[str, Any]) -> ScenarioDefinition:
    """Parse a raw YAML dictionary into a ScenarioDefinition.

    Args:
        raw: Parsed YAML dictionary.

    Returns:
        ScenarioDefinition.
    """
    return ScenarioDefinition(
        name=raw.get("name", "unnamed"),
        hypothesis=raw.get("hypothesis", "").strip(),
        fault_sequence=raw.get("fault_sequence", []),
        slo_thresholds=raw.get("slo_thresholds", {}),
        blast_radius=raw.get("blast_radius", {}),
        network_config=raw.get("network_config", {}),
        success_criteria=raw.get("success_criteria", "").strip(),
        tags=raw.get("tags", []),
        timeout=raw.get("timeout", "15m"),
        raw=raw,
    )


class ScenarioBuilder:
    """Programmatic builder for common chaos scenarios.

    Provides factory methods for creating scenario definitions
    without writing YAML files. Useful for testing, demos, and
    dynamically generated experiments.

    Examples:
        >>> builder = ScenarioBuilder()
        >>> scenario = builder.attestation_withholding(
        ...     target_percent=30,
        ...     duration_seconds=300,
        ... )
        >>> assert scenario.name == "attestation_withholding"
    """

    @staticmethod
    def baseline_observation(
        duration_seconds: int = 600,
        node_count: int = 50,
    ) -> ScenarioDefinition:
        """Create a no-fault baseline observation scenario.

        Args:
            duration_seconds: Total observation duration.
            node_count: Number of nodes in the network.

        Returns:
            ScenarioDefinition for baseline observation.
        """
        return ScenarioDefinition(
            name="baseline_observation",
            hypothesis=(
                "The Ethereum testnet maintains healthy finality and high "
                "participation rate with no faults injected"
            ),
            fault_sequence=[
                {"time": "0s", "action": "baseline", "description": "Begin baseline observation"},
                {"time": f"{duration_seconds // 2}s", "action": "observe", "description": "Mid-point check"},
                {"time": f"{duration_seconds}s", "action": "complete", "description": "End observation"},
            ],
            slo_thresholds={
                "finality_delay_max_epochs": 5,
                "slashing_rate_max_percent": 5.0,
                "participation_rate_min_percent": 66.0,
            },
            blast_radius={"max_affected_percent": 0.0, "phased_rollout": []},
            network_config={"node_count": node_count},
            success_criteria="Finality maintained and participation rate stays above 95%",
            tags=["baseline", "smoke-test"],
            timeout=f"{duration_seconds + 300}s",
        )

    @staticmethod
    def attestation_withholding(
        target_percent: float = 30.0,
        withhold_probability: float = 1.0,
        duration_seconds: int = 600,
        node_count: int = 10,
    ) -> ScenarioDefinition:
        """Create an attestation withholding scenario.

        Args:
            target_percent: Percentage of validators to withhold attestations.
            withhold_probability: Probability of each targeted validator withholding.
            duration_seconds: Duration of fault injection.
            node_count: Number of nodes.

        Returns:
            ScenarioDefinition for attestation withholding.
        """
        target_percent = min(target_percent, 33.0)

        return ScenarioDefinition(
            name="attestation_withholding",
            hypothesis=(
                f"Ethereum testnet maintains finality when {target_percent:.0f}% "
                f"of validators withhold attestations"
            ),
            fault_sequence=[
                {"time": "0s", "action": "baseline", "description": "Establish baseline"},
                {
                    "time": "60s",
                    "action": "attestation_withholding",
                    "params": {
                        "target_percent": target_percent,
                        "withhold_probability": withhold_probability,
                    },
                    "description": f"Begin withholding attestations from {target_percent:.0f}% of validators",
                },
                {
                    "time": f"{60 + duration_seconds}s",
                    "action": "remove_faults",
                    "description": "Remove attestation withholding",
                },
                {
                    "time": f"{60 + duration_seconds + 300}s",
                    "action": "complete",
                    "description": "Collect final metrics and complete",
                },
            ],
            slo_thresholds={
                "finality_delay_max_epochs": 5,
                "slashing_rate_max_percent": 5.0,
            },
            blast_radius={
                "max_affected_percent": target_percent,
                "phased_rollout": [5, 10, target_percent] if target_percent > 10 else [target_percent],
            },
            network_config={"node_count": node_count},
            success_criteria=f"Finality maintained with {target_percent:.0f}% attestation withholding",
            tags=["attestation", "protocol-level", "finality"],
            timeout=f"{60 + duration_seconds + 600}s",
        )

    @staticmethod
    def network_latency(
        target_percent: float = 20.0,
        latency_ms: int = 200,
        jitter_ms: int = 50,
        duration_seconds: int = 600,
        node_count: int = 10,
    ) -> ScenarioDefinition:
        """Create a network latency injection scenario.

        Args:
            target_percent: Percentage of nodes to apply latency to.
            latency_ms: Additional latency in milliseconds.
            jitter_ms: Latency jitter in milliseconds.
            duration_seconds: Duration of fault injection.
            node_count: Number of nodes.

        Returns:
            ScenarioDefinition for network latency.
        """
        target_percent = min(target_percent, 33.0)

        return ScenarioDefinition(
            name="network_latency_injection",
            hypothesis=(
                f"Ethereum testnet maintains finality with {latency_ms}ms "
                f"additional latency on {target_percent:.0f}% of nodes"
            ),
            fault_sequence=[
                {"time": "0s", "action": "baseline", "description": "Establish baseline"},
                {
                    "time": "60s",
                    "action": "inject_network_latency",
                    "params": {
                        "nodes": f"{target_percent:.0f}%",
                        "latency": f"{latency_ms}ms",
                        "jitter": f"{jitter_ms}ms",
                    },
                    "description": f"Inject {latency_ms}ms latency on {target_percent:.0f}% of nodes",
                },
                {
                    "time": f"{60 + duration_seconds}s",
                    "action": "remove_faults",
                    "description": "Remove latency injection",
                },
                {
                    "time": f"{60 + duration_seconds + 300}s",
                    "action": "complete",
                    "description": "Collect final metrics and complete",
                },
            ],
            slo_thresholds={
                "finality_delay_max_epochs": 5,
                "slashing_rate_max_percent": 5.0,
            },
            blast_radius={
                "max_affected_percent": target_percent,
            },
            network_config={"node_count": node_count},
            success_criteria=f"Finality maintained with {latency_ms}ms latency on {target_percent:.0f}% of nodes",
            tags=["network", "latency", "infrastructure"],
            timeout=f"{60 + duration_seconds + 600}s",
        )

    @staticmethod
    def node_failure(
        target_percent: float = 20.0,
        duration_seconds: int = 600,
        node_count: int = 10,
    ) -> ScenarioDefinition:
        """Create a node failure scenario.

        Args:
            target_percent: Percentage of nodes to kill.
            duration_seconds: Duration before recovery.
            node_count: Number of nodes.

        Returns:
            ScenarioDefinition for node failure.
        """
        target_percent = min(target_percent, 33.0)

        return ScenarioDefinition(
            name="node_failure",
            hypothesis=(
                f"Ethereum testnet maintains finality when "
                f"{target_percent:.0f}% of validator nodes are killed"
            ),
            fault_sequence=[
                {"time": "0s", "action": "baseline", "description": "Establish baseline"},
                {
                    "time": "60s",
                    "action": "kill_nodes",
                    "params": {"percent": target_percent},
                    "description": f"Kill {target_percent:.0f}% of nodes",
                },
                {
                    "time": f"{60 + duration_seconds}s",
                    "action": "restart_nodes",
                    "description": "Restart killed nodes",
                },
                {
                    "time": f"{60 + duration_seconds + 300}s",
                    "action": "complete",
                    "description": "Collect final metrics and complete",
                },
            ],
            slo_thresholds={
                "finality_delay_max_epochs": 5,
                "slashing_rate_max_percent": 5.0,
            },
            blast_radius={
                "max_affected_percent": target_percent,
            },
            network_config={"node_count": node_count},
            success_criteria=f"Finality maintained or recovered within 5 minutes after {target_percent:.0f}% node failure",
            tags=["node-failure", "recovery", "resilience"],
            timeout=f"{60 + duration_seconds + 600}s",
        )

    @staticmethod
    def finality_stress_test(
        adversarial_ratio: float = 0.3,
        node_count: int = 10,
        duration_seconds: int = 600,
    ) -> ScenarioDefinition:
        """Create a finality stress test combining multiple fault types.

        Injects network latency followed by attestation withholding
        to stress the consensus mechanism.

        Args:
            adversarial_ratio: Fraction of adversarial nodes.
            node_count: Number of nodes.
            duration_seconds: Duration of each fault phase.

        Returns:
            ScenarioDefinition for finality stress test.
        """
        target_percent = min(adversarial_ratio * 100, 33.0)

        return ScenarioDefinition(
            name="finality_stress_test",
            hypothesis=(
                f"Ethereum testnet recovers finality after combined "
                f"network latency and {target_percent:.0f}% attestation withholding"
            ),
            fault_sequence=[
                {"time": "0s", "action": "baseline", "description": "Establish baseline"},
                {
                    "time": "60s",
                    "action": "inject_network_latency",
                    "params": {"nodes": "20%", "latency": "200ms"},
                    "description": "Phase 1: Inject 200ms latency on 20% of nodes",
                },
                {
                    "time": f"{60 + duration_seconds // 2}s",
                    "action": "attestation_withholding",
                    "params": {
                        "withhold_probability": 1.0,
                        "target_percent": target_percent,
                    },
                    "description": f"Phase 2: Begin attestation withholding on {target_percent:.0f}% of validators",
                },
                {
                    "time": f"{60 + duration_seconds}s",
                    "action": "remove_faults",
                    "description": "Remove all faults",
                },
                {
                    "time": f"{60 + duration_seconds + 300}s",
                    "action": "complete",
                    "description": "Collect final metrics and complete",
                },
            ],
            slo_thresholds={
                "finality_delay_max_epochs": 5,
                "slashing_rate_max_percent": 5.0,
            },
            blast_radius={
                "max_affected_percent": target_percent,
                "phased_rollout": [10, 20, target_percent] if target_percent > 20 else [target_percent],
            },
            network_config={"node_count": node_count},
            success_criteria=(
                "Finality recovers within 5 minutes after fault removal, "
                "no slashing events during recovery"
            ),
            tags=["finality", "stress-test", "multi-fault", "combined"],
            timeout=f"{60 + duration_seconds + 600}s",
        )
