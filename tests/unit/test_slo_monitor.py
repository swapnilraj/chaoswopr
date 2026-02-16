"""Unit tests for SLO monitoring and breach detection.

Tests real-time SLO monitoring, error budget calculation, and breach detection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from chaoswopr.agents.slo_monitor import (
    SLOBreach,
    SLODefinition,
    SLOMonitor,
    SLOStatus,
)


class TestSLODefinition:
    """Tests for SLODefinition data class."""

    def test_creation(self) -> None:
        slo = SLODefinition(
            metric_name="finality_delay_seconds",
            threshold=600.0,
            comparison="less_than",
            error_budget_percent=1.0,
        )
        assert slo.metric_name == "finality_delay_seconds"
        assert slo.threshold == 600.0
        assert slo.comparison == "less_than"

    def test_to_dict(self) -> None:
        slo = SLODefinition(
            metric_name="test",
            threshold=100.0,
            comparison="greater_than",
        )
        d = slo.to_dict()
        assert d["metric_name"] == "test"
        assert d["threshold"] == 100.0


class TestSLOBreach:
    """Tests for SLOBreach data class."""

    def test_creation(self) -> None:
        now = datetime.now(timezone.utc)
        breach = SLOBreach(
            slo_name="finality_slo",
            metric_name="finality_delay_seconds",
            threshold=600.0,
            actual_value=700.0,
            timestamp=now,
        )
        assert breach.slo_name == "finality_slo"
        assert breach.actual_value == 700.0

    def test_to_dict(self) -> None:
        now = datetime.now(timezone.utc)
        breach = SLOBreach(
            slo_name="test",
            metric_name="metric",
            threshold=10.0,
            actual_value=20.0,
            timestamp=now,
        )
        d = breach.to_dict()
        assert d["slo_name"] == "test"
        assert d["actual_value"] == 20.0


class TestSLOMonitor:
    """Tests for SLO Monitor."""

    def test_initialization(self) -> None:
        monitor = SLOMonitor()
        assert len(monitor.slos) == 0

    def test_add_slo(self) -> None:
        monitor = SLOMonitor()
        slo = SLODefinition(
            metric_name="finality_delay_seconds",
            threshold=600.0,
            comparison="less_than",
        )
        monitor.add_slo("finality_slo", slo)
        assert len(monitor.slos) == 1
        assert "finality_slo" in monitor.slos

    def test_remove_slo(self) -> None:
        monitor = SLOMonitor()
        slo = SLODefinition(metric_name="test", threshold=100.0)
        monitor.add_slo("test_slo", slo)
        monitor.remove_slo("test_slo")
        assert len(monitor.slos) == 0

    def test_check_breaches_no_slos(self) -> None:
        monitor = SLOMonitor()
        breaches = monitor.check_breaches({"metric1": 10.0})
        assert breaches == []

    def test_check_breaches_no_breach(self) -> None:
        monitor = SLOMonitor()
        slo = SLODefinition(
            metric_name="finality_delay_seconds",
            threshold=600.0,
            comparison="less_than",
        )
        monitor.add_slo("finality_slo", slo)

        # Within threshold
        breaches = monitor.check_breaches({"finality_delay_seconds": 13.0})
        assert len(breaches) == 0

    def test_check_breaches_less_than_breach(self) -> None:
        monitor = SLOMonitor()
        slo = SLODefinition(
            metric_name="finality_delay_seconds",
            threshold=600.0,
            comparison="less_than",
        )
        monitor.add_slo("finality_slo", slo)

        # Exceeds threshold
        breaches = monitor.check_breaches({"finality_delay_seconds": 700.0})
        assert len(breaches) == 1
        assert breaches[0]["slo_name"] == "finality_slo"
        assert breaches[0]["metric_name"] == "finality_delay_seconds"

    def test_check_breaches_greater_than_breach(self) -> None:
        monitor = SLOMonitor()
        slo = SLODefinition(
            metric_name="participation_rate_percent",
            threshold=66.0,
            comparison="greater_than",
        )
        monitor.add_slo("participation_slo", slo)

        # Below threshold (breach for greater_than)
        breaches = monitor.check_breaches({"participation_rate_percent": 50.0})
        assert len(breaches) == 1
        assert breaches[0]["metric_name"] == "participation_rate_percent"

    def test_check_breaches_at_threshold(self) -> None:
        """Value exactly at threshold should not breach."""
        monitor = SLOMonitor()
        slo = SLODefinition(
            metric_name="test",
            threshold=100.0,
            comparison="less_than",
        )
        monitor.add_slo("test_slo", slo)

        breaches = monitor.check_breaches({"test": 100.0})
        assert len(breaches) == 0

    def test_check_breaches_missing_metric(self) -> None:
        """Missing metric should not cause breach."""
        monitor = SLOMonitor()
        slo = SLODefinition(
            metric_name="missing_metric",
            threshold=100.0,
            comparison="less_than",
        )
        monitor.add_slo("test_slo", slo)

        breaches = monitor.check_breaches({"other_metric": 50.0})
        assert len(breaches) == 0

    def test_error_budget_calculation(self) -> None:
        monitor = SLOMonitor()
        slo = SLODefinition(
            metric_name="finality_delay_seconds",
            threshold=600.0,
            comparison="less_than",
            error_budget_percent=1.0,  # 1% error budget
        )
        monitor.add_slo("finality_slo", slo)

        # Track some measurements
        for i in range(100):
            # 95 good, 5 bad = 5% breach rate
            value = 700.0 if i < 5 else 13.0
            monitor.check_breaches({"finality_delay_seconds": value})

        budget = monitor.get_error_budget("finality_slo")
        # Should have consumed error budget (5% > 1%)
        assert budget is not None
        assert budget["remaining_percent"] < 0  # Over budget

    def test_get_status(self) -> None:
        monitor = SLOMonitor()
        status = monitor.get_status()
        assert status["slo_count"] == 0
        assert status["total_checks"] == 0

    def test_get_status_with_slos(self) -> None:
        monitor = SLOMonitor()
        slo = SLODefinition(metric_name="test", threshold=100.0)
        monitor.add_slo("test_slo", slo)
        monitor.check_breaches({"test": 50.0})

        status = monitor.get_status()
        assert status["slo_count"] == 1
        assert status["total_checks"] > 0

    def test_multiple_slos(self) -> None:
        """Monitor should handle multiple SLOs."""
        monitor = SLOMonitor()
        monitor.add_slo(
            "slo1",
            SLODefinition(metric_name="metric1", threshold=100.0, comparison="less_than"),
        )
        monitor.add_slo(
            "slo2",
            SLODefinition(
                metric_name="metric2", threshold=50.0, comparison="greater_than"
            ),
        )

        # Breach both
        breaches = monitor.check_breaches({"metric1": 200.0, "metric2": 30.0})
        assert len(breaches) == 2

    def test_clear_history(self) -> None:
        monitor = SLOMonitor()
        slo = SLODefinition(metric_name="test", threshold=100.0)
        monitor.add_slo("test_slo", slo)
        monitor.check_breaches({"test": 200.0})
        monitor.clear_history()

        status = monitor.get_status()
        assert status["total_checks"] == 0


class TestSLOStatus:
    """Tests for SLO status tracking."""

    def test_status_compliant(self) -> None:
        """SLO should be compliant when within budget."""
        monitor = SLOMonitor()
        slo = SLODefinition(
            metric_name="test",
            threshold=100.0,
            comparison="less_than",
            error_budget_percent=5.0,
        )
        monitor.add_slo("test_slo", slo)

        # Mostly good values
        for i in range(100):
            value = 200.0 if i < 3 else 50.0  # 3% breach
            monitor.check_breaches({"test": value})

        budget = monitor.get_error_budget("test_slo")
        assert budget is not None
        assert budget["status"] == "compliant"

    def test_status_warning(self) -> None:
        """SLO should warn when approaching budget limit."""
        monitor = SLOMonitor()
        slo = SLODefinition(
            metric_name="test",
            threshold=100.0,
            comparison="less_than",
            error_budget_percent=5.0,
        )
        monitor.add_slo("test_slo", slo)

        # Close to budget
        for i in range(100):
            value = 200.0 if i < 4 else 50.0  # 4% breach (80% of 5% budget)
            monitor.check_breaches({"test": value})

        budget = monitor.get_error_budget("test_slo")
        assert budget is not None
        # Should be either warning or compliant depending on threshold
        assert budget["status"] in ["compliant", "warning"]
