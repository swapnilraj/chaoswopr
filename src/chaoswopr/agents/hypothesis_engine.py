"""Hypothesis generation engine for the Orchestrator Agent.

Generates structured, testable hypotheses from scenario YAML files,
current cluster state, and historical experiment results.

The engine produces JSON-conforming hypotheses with:
  - Prediction: What will happen under fault conditions
  - Blast radius: Scope of the experiment
  - Fault timeline: Sequence of fault injection actions
  - Expected metrics: Predicted metric ranges
  - Success criteria: How to determine if the hypothesis was confirmed

Hypothesis output is validated against a strict schema to ensure
the experiment plan compiler can process it deterministically.

Supports two modes:
  - LLM mode: Uses an LLM API for intelligent hypothesis generation
  - Template mode: Uses pre-defined templates (dry-run, testing)
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HypothesisStatus(str, Enum):
    """Status of a generated hypothesis."""

    GENERATED = "generated"
    VALIDATED = "validated"
    REJECTED = "rejected"
    TESTED = "tested"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"


class FaultLevel(str, Enum):
    """Level at which a fault operates."""

    NETWORK = "network"
    NODE = "node"
    PROTOCOL = "protocol"


@dataclass
class FaultAction:
    """A single fault injection action in a hypothesis timeline.

    Attributes:
        time_offset_seconds: When to execute this action (relative to experiment start).
        action_type: Type of fault to inject.
        fault_level: Level (network, node, protocol).
        target_percent: Percentage of nodes to target.
        parameters: Fault-specific parameters.
        description: Human-readable description of this action.
    """

    time_offset_seconds: int
    action_type: str
    fault_level: FaultLevel
    target_percent: float = 5.0
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def validate(self) -> list[str]:
        """Validate this fault action.

        Returns:
            List of validation error messages.
        """
        errors: list[str] = []
        if self.time_offset_seconds < 0:
            errors.append("time_offset_seconds must be >= 0")
        if self.target_percent < 0 or self.target_percent > 33:
            errors.append(f"target_percent {self.target_percent} must be 0-33%")
        if not self.action_type:
            errors.append("action_type is required")
        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "time_offset_seconds": self.time_offset_seconds,
            "action_type": self.action_type,
            "fault_level": self.fault_level.value,
            "target_percent": self.target_percent,
            "parameters": self.parameters,
            "description": self.description,
        }


@dataclass
class ExpectedMetric:
    """Expected metric range during/after fault injection.

    Attributes:
        metric_name: Name of the metric.
        baseline_value: Expected value without faults.
        expected_min: Minimum expected value during fault.
        expected_max: Maximum expected value during fault.
        recovery_time_seconds: Expected time to recover after fault removal.
    """

    metric_name: str
    baseline_value: float = 0.0
    expected_min: float = 0.0
    expected_max: float = float("inf")
    recovery_time_seconds: int = 300

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "expected_min": self.expected_min,
            "expected_max": self.expected_max,
            "recovery_time_seconds": self.recovery_time_seconds,
        }


@dataclass
class Hypothesis:
    """A structured, testable hypothesis for a chaos experiment.

    This is the core output of the hypothesis generation engine.
    It must conform to a strict schema so that the experiment plan
    compiler can process it deterministically.

    Attributes:
        hypothesis_id: Unique identifier.
        prediction: What we predict will happen under fault conditions.
        rationale: Why we expect this outcome.
        fault_timeline: Ordered sequence of fault actions.
        expected_metrics: Predicted metric ranges.
        blast_radius_percent: Maximum percentage of nodes affected.
        success_criteria: Conditions that confirm the hypothesis.
        failure_criteria: Conditions that refute the hypothesis.
        scenario_name: Name of the source scenario.
        status: Current status of the hypothesis.
        confidence: Confidence level (0.0-1.0).
        tags: Classification tags.
        created_at: When the hypothesis was generated.
    """

    hypothesis_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    prediction: str = ""
    rationale: str = ""
    fault_timeline: list[FaultAction] = field(default_factory=list)
    expected_metrics: list[ExpectedMetric] = field(default_factory=list)
    blast_radius_percent: float = 5.0
    success_criteria: str = ""
    failure_criteria: str = ""
    scenario_name: str = ""
    status: HypothesisStatus = HypothesisStatus.GENERATED
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate(self) -> list[str]:
        """Validate the hypothesis structure.

        Returns:
            List of validation error messages. Empty means valid.
        """
        errors: list[str] = []

        if not self.prediction:
            errors.append("prediction is required")
        if not self.fault_timeline:
            errors.append("fault_timeline must have at least one action")
        if self.blast_radius_percent > 33.0:
            errors.append(
                f"blast_radius_percent {self.blast_radius_percent}% exceeds safety limit of 33%"
            )
        if self.blast_radius_percent < 0:
            errors.append("blast_radius_percent must be >= 0")
        if self.confidence < 0 or self.confidence > 1:
            errors.append("confidence must be between 0.0 and 1.0")
        if not self.success_criteria:
            errors.append("success_criteria is required")

        # Validate each fault action
        for i, action in enumerate(self.fault_timeline):
            action_errors = action.validate()
            for err in action_errors:
                errors.append(f"fault_timeline[{i}]: {err}")

        # Validate timeline is in chronological order
        for i in range(1, len(self.fault_timeline)):
            if self.fault_timeline[i].time_offset_seconds < self.fault_timeline[i - 1].time_offset_seconds:
                errors.append(
                    f"fault_timeline not chronological: action {i} "
                    f"({self.fault_timeline[i].time_offset_seconds}s) < "
                    f"action {i-1} ({self.fault_timeline[i-1].time_offset_seconds}s)"
                )
                break

        # Validate no action exceeds blast radius
        for i, action in enumerate(self.fault_timeline):
            if action.target_percent > self.blast_radius_percent:
                errors.append(
                    f"fault_timeline[{i}].target_percent ({action.target_percent}%) "
                    f"exceeds blast_radius_percent ({self.blast_radius_percent}%)"
                )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "prediction": self.prediction,
            "rationale": self.rationale,
            "fault_timeline": [a.to_dict() for a in self.fault_timeline],
            "expected_metrics": [m.to_dict() for m in self.expected_metrics],
            "blast_radius_percent": self.blast_radius_percent,
            "success_criteria": self.success_criteria,
            "failure_criteria": self.failure_criteria,
            "scenario_name": self.scenario_name,
            "status": self.status.value,
            "confidence": self.confidence,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }


# Pre-defined hypothesis templates for common scenarios
HYPOTHESIS_TEMPLATES: dict[str, dict[str, Any]] = {
    "network_latency": {
        "prediction": (
            "The Ethereum testnet will maintain finality with degraded latency "
            "when {target_percent}% of nodes experience {latency_ms}ms additional latency"
        ),
        "rationale": (
            "Consensus protocols are designed to tolerate network delays. "
            "Latency below slot time (12s) should not prevent finality, "
            "but may increase attestation inclusion delay."
        ),
        "fault_level": FaultLevel.NETWORK,
        "action_type": "inject_network_latency",
        "default_params": {"latency_ms": 200, "jitter_ms": 50},
        "expected_metrics": [
            {"metric_name": "finality_delay_seconds", "expected_max": 120.0},
            {"metric_name": "attestation_inclusion_delay", "expected_max": 5.0},
            {"metric_name": "participation_rate_percent", "expected_min": 80.0},
        ],
    },
    "packet_loss": {
        "prediction": (
            "The Ethereum testnet will maintain finality but with reduced participation "
            "when {target_percent}% of nodes experience {loss_percent}% packet loss"
        ),
        "rationale": (
            "Packet loss degrades P2P gossip reliability. Moderate loss (<30%) "
            "should not prevent finality but will reduce attestation counts."
        ),
        "fault_level": FaultLevel.NETWORK,
        "action_type": "inject_packet_loss",
        "default_params": {"loss_percent": 20},
        "expected_metrics": [
            {"metric_name": "finality_delay_seconds", "expected_max": 300.0},
            {"metric_name": "participation_rate_percent", "expected_min": 70.0},
        ],
    },
    "node_failure": {
        "prediction": (
            "The Ethereum testnet will maintain finality when {target_percent}% "
            "of validator nodes are killed"
        ),
        "rationale": (
            "Ethereum consensus tolerates up to 1/3 offline validators. "
            "Killing {target_percent}% should not prevent finality but may "
            "temporarily reduce participation rate."
        ),
        "fault_level": FaultLevel.NODE,
        "action_type": "kill_nodes",
        "default_params": {},
        "expected_metrics": [
            {"metric_name": "finality_delay_seconds", "expected_max": 600.0},
            {"metric_name": "participation_rate_percent", "expected_min": 66.0},
        ],
    },
    "attestation_withholding": {
        "prediction": (
            "The Ethereum testnet will experience finality delay but eventually "
            "recover when {target_percent}% of validators withhold attestations"
        ),
        "rationale": (
            "Attestation withholding reduces the number of attestations per epoch. "
            "Below the 2/3 threshold, finality will stall. Above it, finality "
            "continues with degraded performance."
        ),
        "fault_level": FaultLevel.PROTOCOL,
        "action_type": "attestation_withholding",
        "default_params": {"withhold_probability": 1.0},
        "expected_metrics": [
            {"metric_name": "finality_delay_seconds", "expected_max": 600.0},
            {"metric_name": "participation_rate_percent", "expected_min": 60.0},
        ],
    },
    "cpu_stress": {
        "prediction": (
            "The Ethereum testnet will maintain finality but with increased latency "
            "when {target_percent}% of nodes experience CPU stress"
        ),
        "rationale": (
            "CPU stress increases processing time for blocks and attestations. "
            "This may cause missed slots but should not prevent finality unless "
            "validators cannot process within slot boundaries."
        ),
        "fault_level": FaultLevel.NODE,
        "action_type": "cpu_stress",
        "default_params": {"cpu_load": 90, "cpu_workers": 4},
        "expected_metrics": [
            {"metric_name": "finality_delay_seconds", "expected_max": 120.0},
            {"metric_name": "block_proposal_rate", "expected_min": 0.05},
        ],
    },
}


class HypothesisEngine:
    """Engine for generating structured chaos experiment hypotheses.

    Generates hypotheses from scenario YAML definitions, current cluster state,
    and historical experiment results. Supports template-based generation for
    deterministic testing and LLM-based generation for intelligent hypothesis
    creation.

    Examples:
        >>> engine = HypothesisEngine(dry_run=True)
        >>> scenario = {"name": "test", "hypothesis": "Test prediction"}
        >>> hypothesis = engine.generate(scenario=scenario)
        >>> errors = hypothesis.validate()
        >>> assert not errors
    """

    def __init__(
        self,
        experiment_history: list[dict[str, Any]] | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the hypothesis engine.

        Args:
            experiment_history: Historical experiment results for adaptive learning.
            dry_run: If True, use template-based generation only.
        """
        self._experiment_history = experiment_history or []
        self._dry_run = dry_run
        self._generated_count = 0

    @property
    def generated_count(self) -> int:
        """Get the total number of hypotheses generated."""
        return self._generated_count

    def generate(
        self,
        scenario: dict[str, Any],
        cluster_state: dict[str, float] | None = None,
        target_percent: float | None = None,
    ) -> Hypothesis:
        """Generate a hypothesis from a scenario.

        Args:
            scenario: Loaded scenario dictionary (from YAML).
            cluster_state: Current cluster metrics (from Prometheus).
            target_percent: Override target percentage for the blast radius.

        Returns:
            A validated Hypothesis ready for the experiment plan compiler.
        """
        cluster_state = cluster_state or {}

        # Determine target percent from scenario if not overridden
        if target_percent is None:
            blast_radius = scenario.get("blast_radius", {})
            target_percent = blast_radius.get("max_affected_percent", 10.0)
            # Enforce safety limit
            target_percent = min(target_percent, 33.0)

        # Extract scenario metadata
        scenario_name = scenario.get("name", "unknown")
        scenario_hypothesis = scenario.get("hypothesis", "")
        fault_sequence = scenario.get("fault_sequence", [])
        slo_thresholds = scenario.get("slo_thresholds", {})

        # Select template based on fault sequence analysis
        template_key = self._select_template(fault_sequence, scenario)

        # Generate hypothesis
        hypothesis = self._generate_from_template(
            template_key=template_key,
            scenario=scenario,
            cluster_state=cluster_state,
            target_percent=target_percent,
        )

        # Enrich with scenario-specific SLO thresholds
        hypothesis = self._enrich_with_slo(hypothesis, slo_thresholds, cluster_state)

        # Add adaptive adjustments from history
        hypothesis = self._apply_adaptive_learning(hypothesis, scenario_name)

        # Validate
        errors = hypothesis.validate()
        if errors:
            logger.warning(
                "Generated hypothesis has validation errors: %s",
                errors,
            )
            hypothesis.status = HypothesisStatus.REJECTED
        else:
            hypothesis.status = HypothesisStatus.VALIDATED

        self._generated_count += 1

        logger.info(
            "Generated hypothesis %s for scenario '%s' (status=%s, confidence=%.2f)",
            hypothesis.hypothesis_id,
            scenario_name,
            hypothesis.status.value,
            hypothesis.confidence,
        )

        return hypothesis

    def generate_from_template(
        self,
        template_key: str,
        target_percent: float = 10.0,
        custom_params: dict[str, Any] | None = None,
    ) -> Hypothesis:
        """Generate a hypothesis from a specific template.

        Args:
            template_key: Template name (from HYPOTHESIS_TEMPLATES).
            target_percent: Percentage of nodes to target.
            custom_params: Override template default parameters.

        Returns:
            A Hypothesis built from the template.

        Raises:
            ValueError: If template_key is not found.
        """
        if template_key not in HYPOTHESIS_TEMPLATES:
            raise ValueError(
                f"Unknown template: {template_key}. "
                f"Available: {list(HYPOTHESIS_TEMPLATES.keys())}"
            )

        template = HYPOTHESIS_TEMPLATES[template_key]
        params = dict(template.get("default_params", {}))
        if custom_params:
            params.update(custom_params)

        # Format prediction with parameters
        format_vars = {"target_percent": target_percent, **params}
        prediction = template["prediction"].format(**format_vars)
        rationale = template["rationale"].format(**format_vars)

        # Build fault timeline
        baseline_action = FaultAction(
            time_offset_seconds=0,
            action_type="baseline",
            fault_level=template["fault_level"],
            target_percent=0,
            description="Establish baseline metrics",
        )

        inject_action = FaultAction(
            time_offset_seconds=60,
            action_type=template["action_type"],
            fault_level=template["fault_level"],
            target_percent=target_percent,
            parameters=params,
            description=f"Inject {template_key} fault at {target_percent}%",
        )

        observe_action = FaultAction(
            time_offset_seconds=360,
            action_type="observe",
            fault_level=template["fault_level"],
            target_percent=0,
            description="Observe system behavior under fault",
        )

        remove_action = FaultAction(
            time_offset_seconds=600,
            action_type="remove_faults",
            fault_level=template["fault_level"],
            target_percent=0,
            description="Remove all injected faults",
        )

        recovery_action = FaultAction(
            time_offset_seconds=900,
            action_type="complete",
            fault_level=template["fault_level"],
            target_percent=0,
            description="Complete experiment and collect final metrics",
        )

        # Build expected metrics
        expected_metrics = [
            ExpectedMetric(
                metric_name=m["metric_name"],
                expected_min=m.get("expected_min", 0.0),
                expected_max=m.get("expected_max", float("inf")),
            )
            for m in template.get("expected_metrics", [])
        ]

        hypothesis = Hypothesis(
            prediction=prediction,
            rationale=rationale,
            fault_timeline=[
                baseline_action,
                inject_action,
                observe_action,
                remove_action,
                recovery_action,
            ],
            expected_metrics=expected_metrics,
            blast_radius_percent=min(target_percent, 33.0),
            success_criteria=f"System maintains acceptable metrics under {template_key} fault",
            failure_criteria=f"System fails to maintain SLOs under {template_key} fault",
            scenario_name=template_key,
            confidence=0.7,
            tags=[template_key, template["fault_level"].value],
        )

        self._generated_count += 1
        return hypothesis

    def add_experiment_result(self, result: dict[str, Any]) -> None:
        """Add an experiment result for adaptive learning.

        Args:
            result: Experiment result dictionary with hypothesis, metrics, outcome.
        """
        self._experiment_history.append(result)
        logger.info(
            "Added experiment result to history (total: %d)",
            len(self._experiment_history),
        )

    def _select_template(
        self,
        fault_sequence: list[dict[str, Any]],
        scenario: dict[str, Any],
    ) -> str:
        """Select the best template for a scenario.

        Analyzes the fault sequence to determine which template to use.

        Args:
            fault_sequence: Fault sequence from scenario YAML.
            scenario: Full scenario dictionary.

        Returns:
            Template key string.
        """
        # Look for specific fault types in the sequence
        for step in fault_sequence:
            action = step.get("action", "")
            params = step.get("params", {})

            if "latency" in action.lower():
                return "network_latency"
            if "packet" in action.lower() or "loss" in action.lower():
                return "packet_loss"
            if "kill" in action.lower() or "failure" in action.lower():
                return "node_failure"
            if "withhold" in action.lower() or "attestation" in action.lower():
                return "attestation_withholding"
            if "cpu" in action.lower() or "stress" in action.lower():
                return "cpu_stress"

        # Check scenario name for hints
        name = scenario.get("name", "").lower()
        if "latency" in name or "network" in name:
            return "network_latency"
        if "partition" in name:
            return "packet_loss"
        if "finality" in name:
            return "attestation_withholding"
        if "exit" in name or "kill" in name:
            return "node_failure"

        # Default to network latency (safest)
        return "network_latency"

    def _generate_from_template(
        self,
        template_key: str,
        scenario: dict[str, Any],
        cluster_state: dict[str, float],
        target_percent: float,
    ) -> Hypothesis:
        """Generate a hypothesis from a template with scenario enrichment.

        Args:
            template_key: Template to use.
            scenario: Scenario dictionary for enrichment.
            cluster_state: Current cluster state for calibration.
            target_percent: Blast radius percentage.

        Returns:
            Generated Hypothesis.
        """
        hypothesis = self.generate_from_template(
            template_key=template_key,
            target_percent=target_percent,
        )

        # Override prediction with scenario hypothesis if available
        scenario_hypothesis = scenario.get("hypothesis", "")
        if scenario_hypothesis:
            hypothesis.prediction = scenario_hypothesis

        hypothesis.scenario_name = scenario.get("name", template_key)

        # Set baseline values from cluster state
        for metric in hypothesis.expected_metrics:
            baseline_value = cluster_state.get(metric.metric_name)
            if baseline_value is not None:
                metric.baseline_value = baseline_value

        # Decrement generated count since generate_from_template already counted
        self._generated_count -= 1

        return hypothesis

    def _enrich_with_slo(
        self,
        hypothesis: Hypothesis,
        slo_thresholds: dict[str, Any],
        cluster_state: dict[str, float],
    ) -> Hypothesis:
        """Enrich hypothesis with SLO-derived expected metrics.

        Args:
            hypothesis: Hypothesis to enrich.
            slo_thresholds: SLO thresholds from scenario YAML.
            cluster_state: Current cluster metrics.

        Returns:
            Enriched hypothesis.
        """
        existing_metrics = {m.metric_name for m in hypothesis.expected_metrics}

        # Map SLO thresholds to expected metrics
        slo_metric_map = {
            "finality_delay_max_epochs": (
                "finality_delay_seconds",
                lambda v: v * 6.4 * 60,  # epochs to seconds (6.4 min per epoch)
            ),
            "slashing_rate_max_percent": (
                "slashing_rate_percent",
                lambda v: v,
            ),
            "participation_rate_min_percent": (
                "participation_rate_percent",
                lambda v: v,
            ),
        }

        for slo_key, (metric_name, transform) in slo_metric_map.items():
            if slo_key in slo_thresholds and metric_name not in existing_metrics:
                threshold = transform(slo_thresholds[slo_key])
                baseline = cluster_state.get(metric_name, 0.0)

                if "min" in slo_key:
                    hypothesis.expected_metrics.append(
                        ExpectedMetric(
                            metric_name=metric_name,
                            baseline_value=baseline,
                            expected_min=threshold,
                        )
                    )
                else:
                    hypothesis.expected_metrics.append(
                        ExpectedMetric(
                            metric_name=metric_name,
                            baseline_value=baseline,
                            expected_max=threshold,
                        )
                    )

        return hypothesis

    def _apply_adaptive_learning(
        self,
        hypothesis: Hypothesis,
        scenario_name: str,
    ) -> Hypothesis:
        """Apply adaptive adjustments from historical experiment results.

        If previous experiments with similar scenarios showed specific outcomes,
        adjust the hypothesis accordingly.

        Args:
            hypothesis: Hypothesis to adjust.
            scenario_name: Name of the current scenario.

        Returns:
            Adjusted hypothesis.
        """
        if not self._experiment_history:
            return hypothesis

        # Find relevant historical results
        relevant = [
            h for h in self._experiment_history
            if h.get("scenario_name") == scenario_name
        ]

        if not relevant:
            return hypothesis

        # Adjust confidence based on historical success rate
        successes = sum(1 for h in relevant if h.get("outcome") == "success")
        total = len(relevant)
        if total > 0:
            historical_success_rate = successes / total
            # Blend current confidence with historical rate
            hypothesis.confidence = (hypothesis.confidence + historical_success_rate) / 2

        # If the last experiment showed the boundary, suggest testing slightly beyond
        last_result = relevant[-1]
        last_target = last_result.get("target_percent")
        if last_target is not None and last_result.get("outcome") == "success":
            suggested_target = min(last_target * 1.15, 33.0)  # 15% increase
            if suggested_target > hypothesis.blast_radius_percent:
                hypothesis.rationale += (
                    f" (Adaptive: previous test at {last_target:.0f}% succeeded, "
                    f"trying {suggested_target:.0f}%)"
                )

        return hypothesis
