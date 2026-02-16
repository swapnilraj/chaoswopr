"""Prometheus alerting rules for chaoswopr circuit breaker integration.

Defines alerting rules that feed the safety system:
- finality_delay > 10 min
- slashing_count > 5%
- participation_rate < 66%

In Phase 1 these fire alerts. In Phase 2 they trigger automated circuit breakers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chaoswopr.infrastructure.monitoring.metrics_catalog import (
    MetricsCatalog,
)


@dataclass
class AlertRule:
    """A single Prometheus alerting rule.

    Attributes:
        name: Alert name.
        expression: PromQL expression that triggers the alert.
        duration: How long the condition must hold before firing.
        severity: Alert severity (critical, warning, info).
        description: Human-readable description.
        labels: Additional labels for the alert.
        annotations: Alert annotations.
    """

    name: str
    expression: str
    duration: str = "1m"
    severity: str = "critical"
    description: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)

    def to_prometheus_rule(self) -> dict[str, Any]:
        """Convert to Prometheus alerting rule format.

        Returns:
            Dictionary in Prometheus rule file format.
        """
        rule: dict[str, Any] = {
            "alert": self.name,
            "expr": self.expression,
            "for": self.duration,
            "labels": {
                "severity": self.severity,
                **self.labels,
            },
            "annotations": {
                "description": self.description,
                **self.annotations,
            },
        }
        return rule


# Default circuit breaker alert rules
DEFAULT_ALERT_RULES: list[AlertRule] = [
    AlertRule(
        name="FinalityDelayHigh",
        expression="(beacon_head_slot / 32 - beacon_finalized_epoch) > 5",
        duration="2m",
        severity="critical",
        description="Finality delay has exceeded 5 epochs for more than 2 minutes",
        labels={"component": "circuit_breaker", "action": "trip"},
    ),
    AlertRule(
        name="FinalityLost",
        expression="(beacon_head_slot / 32 - beacon_finalized_epoch) > 15",
        duration="30s",
        severity="critical",
        description="Finality has been lost for more than 15 epochs - immediate halt required",
        labels={"component": "circuit_breaker", "action": "kill_switch"},
    ),
    AlertRule(
        name="SlashingRateHigh",
        expression="beacon_slashings_total / beacon_validator_count_active * 100 > 5",
        duration="30s",
        severity="critical",
        description="Slashing rate exceeds 5% of active validators",
        labels={"component": "circuit_breaker", "action": "trip"},
    ),
    AlertRule(
        name="ParticipationRateLow",
        expression="beacon_participation_rate < 66",
        duration="2m",
        severity="critical",
        description="Participation rate has dropped below 66% (finality threshold)",
        labels={"component": "circuit_breaker", "action": "trip"},
    ),
    AlertRule(
        name="ParticipationRateCritical",
        expression="beacon_participation_rate < 50",
        duration="30s",
        severity="critical",
        description="Participation rate below 50% - network may be partitioned",
        labels={"component": "circuit_breaker", "action": "kill_switch"},
    ),
    AlertRule(
        name="NodeDown",
        expression="up == 0",
        duration="1m",
        severity="warning",
        description="A monitored node is not responding to health checks",
        labels={"component": "monitoring"},
    ),
    AlertRule(
        name="HighCPUUsage",
        expression="rate(process_cpu_seconds_total[5m]) * 100 > 90",
        duration="5m",
        severity="warning",
        description="Node CPU usage exceeds 90% for 5 minutes",
        labels={"component": "resource"},
    ),
    AlertRule(
        name="HighMemoryUsage",
        expression="process_resident_memory_bytes / node_memory_MemTotal_bytes * 100 > 90",
        duration="5m",
        severity="warning",
        description="Node memory usage exceeds 90% for 5 minutes",
        labels={"component": "resource"},
    ),
    AlertRule(
        name="DiskSpaceLow",
        expression="node_filesystem_avail_bytes / node_filesystem_size_bytes * 100 < 10",
        duration="5m",
        severity="warning",
        description="Disk space below 10% on a node",
        labels={"component": "resource"},
    ),
    AlertRule(
        name="PeerCountLow",
        expression="avg(p2p_peers) < 5",
        duration="2m",
        severity="warning",
        description="Average peer count is below 5 - possible network connectivity issue",
        labels={"component": "network"},
    ),
    AlertRule(
        name="ChainReorg",
        expression="increase(beacon_reorgs_total[5m]) > 0",
        duration="0s",
        severity="warning",
        description="Chain reorganization detected",
        labels={"component": "consensus"},
    ),
    AlertRule(
        name="MissedProposals",
        expression="increase(beacon_missed_proposals_total[5m]) > 3",
        duration="0s",
        severity="warning",
        description="Multiple missed block proposals in the last 5 minutes",
        labels={"component": "consensus"},
    ),
]


class AlertRuleSet:
    """Collection of Prometheus alerting rules.

    Manages the set of rules and generates the Prometheus rule file format.
    """

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        group_name: str = "chaoswopr_alerts",
    ) -> None:
        """Initialize the rule set.

        Args:
            rules: Custom rules. Defaults to DEFAULT_ALERT_RULES.
            group_name: Prometheus rule group name.
        """
        self._rules = rules if rules is not None else DEFAULT_ALERT_RULES.copy()
        self._group_name = group_name

    @property
    def rules(self) -> list[AlertRule]:
        """Get all rules."""
        return self._rules.copy()

    @property
    def count(self) -> int:
        """Get the number of rules."""
        return len(self._rules)

    def get_circuit_breaker_rules(self) -> list[AlertRule]:
        """Get rules that trigger circuit breaker actions."""
        return [
            r for r in self._rules
            if r.labels.get("component") == "circuit_breaker"
        ]

    def get_by_severity(self, severity: str) -> list[AlertRule]:
        """Get rules by severity level."""
        return [r for r in self._rules if r.severity == severity]

    def add_rule(self, rule: AlertRule) -> None:
        """Add a new alerting rule."""
        self._rules.append(rule)

    def to_prometheus_rules(self) -> dict[str, Any]:
        """Generate Prometheus rules file content.

        Returns:
            Dictionary in Prometheus rule file format.
        """
        return {
            "groups": [
                {
                    "name": self._group_name,
                    "rules": [r.to_prometheus_rule() for r in self._rules],
                }
            ]
        }

    def validate(self) -> list[str]:
        """Validate the rule set.

        Returns:
            List of validation errors.
        """
        errors: list[str] = []

        # Check for duplicate rule names
        names = [r.name for r in self._rules]
        duplicates = [n for n in names if names.count(n) > 1]
        if duplicates:
            errors.append(f"Duplicate rule names: {set(duplicates)}")

        # Check circuit breaker rules exist
        cb_rules = self.get_circuit_breaker_rules()
        if len(cb_rules) < 3:
            errors.append(
                f"Only {len(cb_rules)} circuit breaker rules, need at least 3 "
                "(finality, slashing, participation)"
            )

        # Check all rules have expressions
        for rule in self._rules:
            if not rule.expression.strip():
                errors.append(f"Rule '{rule.name}' has empty expression")

        return errors
