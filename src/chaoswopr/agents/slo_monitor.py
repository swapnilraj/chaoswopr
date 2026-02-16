"""SLO (Service Level Objective) monitoring and breach detection.

Monitors real-time metrics against scenario-defined SLO thresholds,
tracks error budgets, and generates structured alerts when SLOs are breached.

Used by the Observer Agent to detect when experiments violate acceptable
performance boundaries.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class SLODefinition:
    """Definition of a Service Level Objective.

    Attributes:
        metric_name: Name of the metric to monitor.
        threshold: Threshold value for the SLO.
        comparison: Comparison operator ("less_than" or "greater_than").
        error_budget_percent: Allowed percentage of breaches (0-100).
        description: Human-readable description.
    """

    metric_name: str
    threshold: float
    comparison: Literal["less_than", "greater_than"] = "less_than"
    error_budget_percent: float = 1.0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "metric_name": self.metric_name,
            "threshold": self.threshold,
            "comparison": self.comparison,
            "error_budget_percent": self.error_budget_percent,
            "description": self.description,
        }


@dataclass
class SLOBreach:
    """A detected SLO breach.

    Attributes:
        slo_name: Name of the breached SLO.
        metric_name: Name of the metric.
        threshold: SLO threshold value.
        actual_value: Actual metric value that breached.
        timestamp: When the breach occurred.
        severity: Breach severity (info, warning, critical).
    """

    slo_name: str
    metric_name: str
    threshold: float
    actual_value: float
    timestamp: datetime
    severity: str = "warning"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "slo_name": self.slo_name,
            "metric_name": self.metric_name,
            "threshold": self.threshold,
            "actual_value": self.actual_value,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
        }


@dataclass
class SLOStatus:
    """Status of an SLO over time.

    Attributes:
        slo_name: Name of the SLO.
        total_checks: Total number of checks performed.
        breach_count: Number of breaches detected.
        error_budget_percent: Allowed error budget.
        consumed_budget_percent: Percentage of budget consumed.
        status: Overall status (compliant, warning, critical).
    """

    slo_name: str
    total_checks: int
    breach_count: int
    error_budget_percent: float
    consumed_budget_percent: float = 0.0
    status: str = "compliant"


class SLOMonitor:
    """Real-time SLO monitoring and breach detection.

    Tracks metrics against defined SLOs, calculates error budgets,
    and generates breach events when thresholds are exceeded.

    Examples:
        >>> monitor = SLOMonitor()
        >>> slo = SLODefinition(
        ...     metric_name="finality_delay_seconds",
        ...     threshold=600.0,
        ...     comparison="less_than",
        ... )
        >>> monitor.add_slo("finality_slo", slo)
        >>> breaches = monitor.check_breaches({"finality_delay_seconds": 700.0})
        >>> if breaches:
        ...     print(f"SLO breach detected: {breaches[0]}")
    """

    def __init__(self) -> None:
        """Initialize the SLO monitor."""
        # SLO definitions: slo_name -> SLODefinition
        self._slos: dict[str, SLODefinition] = {}

        # Breach tracking: slo_name -> list of breach counts
        self._breach_history: dict[str, list[bool]] = defaultdict(list)

        # Total checks per SLO
        self._check_counts: dict[str, int] = defaultdict(int)

    @property
    def slos(self) -> dict[str, SLODefinition]:
        """Get all SLO definitions."""
        return self._slos

    def add_slo(self, slo_name: str, slo: SLODefinition) -> None:
        """Add an SLO to monitor.

        Args:
            slo_name: Unique name for this SLO.
            slo: SLO definition.
        """
        self._slos[slo_name] = slo

    def remove_slo(self, slo_name: str) -> bool:
        """Remove an SLO.

        Args:
            slo_name: Name of the SLO to remove.

        Returns:
            True if removed, False if not found.
        """
        if slo_name in self._slos:
            del self._slos[slo_name]
            if slo_name in self._breach_history:
                del self._breach_history[slo_name]
            if slo_name in self._check_counts:
                del self._check_counts[slo_name]
            return True
        return False

    def check_breaches(self, current_metrics: dict[str, float]) -> list[dict[str, Any]]:
        """Check current metrics for SLO breaches.

        Args:
            current_metrics: Dictionary of metric_name -> current_value.

        Returns:
            List of breach dictionaries (compatible with ObservationEvent details).
        """
        breaches: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for slo_name, slo in self._slos.items():
            metric_value = current_metrics.get(slo.metric_name)
            if metric_value is None:
                # Metric not present in current batch
                continue

            self._check_counts[slo_name] += 1

            # Check if threshold is breached
            is_breach = False
            if slo.comparison == "less_than":
                is_breach = metric_value > slo.threshold
            elif slo.comparison == "greater_than":
                is_breach = metric_value < slo.threshold

            # Track breach in history
            self._breach_history[slo_name].append(is_breach)

            if is_breach:
                # Calculate severity based on how much threshold is exceeded
                excess_percent = abs(
                    (metric_value - slo.threshold) / slo.threshold * 100
                )
                if excess_percent > 50:
                    severity = "critical"
                elif excess_percent > 20:
                    severity = "warning"
                else:
                    severity = "info"

                breach = {
                    "slo_name": slo_name,
                    "metric_name": slo.metric_name,
                    "threshold": slo.threshold,
                    "actual_value": metric_value,
                    "timestamp": now.isoformat(),
                    "severity": severity,
                    "excess_percent": excess_percent,
                }
                breaches.append(breach)

        return breaches

    def get_error_budget(self, slo_name: str) -> dict[str, Any] | None:
        """Calculate error budget for an SLO.

        Args:
            slo_name: Name of the SLO.

        Returns:
            Error budget information, or None if SLO not found.
        """
        if slo_name not in self._slos:
            return None

        slo = self._slos[slo_name]
        breach_history = self._breach_history.get(slo_name, [])

        if not breach_history:
            return {
                "slo_name": slo_name,
                "error_budget_percent": slo.error_budget_percent,
                "consumed_percent": 0.0,
                "remaining_percent": slo.error_budget_percent,
                "status": "compliant",
                "total_checks": 0,
                "breach_count": 0,
            }

        total_checks = len(breach_history)
        breach_count = sum(1 for b in breach_history if b)
        breach_rate = (breach_count / total_checks) * 100 if total_checks > 0 else 0.0

        consumed_percent = breach_rate
        remaining_percent = slo.error_budget_percent - consumed_percent

        # Determine status
        if remaining_percent < 0:
            status = "critical"
        elif remaining_percent < slo.error_budget_percent * 0.2:
            status = "warning"
        else:
            status = "compliant"

        return {
            "slo_name": slo_name,
            "error_budget_percent": slo.error_budget_percent,
            "consumed_percent": consumed_percent,
            "remaining_percent": remaining_percent,
            "status": status,
            "total_checks": total_checks,
            "breach_count": breach_count,
        }

    def get_status(self) -> dict[str, Any]:
        """Get overall SLO monitor status.

        Returns:
            Dictionary with monitor statistics.
        """
        total_checks = sum(self._check_counts.values())
        total_breaches = sum(
            sum(1 for b in history if b)
            for history in self._breach_history.values()
        )

        return {
            "slo_count": len(self._slos),
            "total_checks": total_checks,
            "total_breaches": total_breaches,
            "slo_names": list(self._slos.keys()),
        }

    def clear_history(self) -> None:
        """Clear all breach history."""
        self._breach_history.clear()
        self._check_counts.clear()
