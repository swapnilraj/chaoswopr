"""Unit tests for Prometheus alerting rules."""

from __future__ import annotations

import pytest

from chaoswopr.infrastructure.monitoring.alerting import (
    DEFAULT_ALERT_RULES,
    AlertRule,
    AlertRuleSet,
)


class TestAlertRule:
    """Tests for AlertRule."""

    def test_create_rule(self) -> None:
        rule = AlertRule(
            name="TestAlert",
            expression="test_metric > 100",
            severity="warning",
            description="Test alert description",
        )
        assert rule.name == "TestAlert"
        assert rule.severity == "warning"

    def test_to_prometheus_rule(self) -> None:
        rule = AlertRule(
            name="TestAlert",
            expression="test > 100",
            duration="5m",
            severity="critical",
            description="Test description",
            labels={"component": "test"},
        )
        prom_rule = rule.to_prometheus_rule()
        assert prom_rule["alert"] == "TestAlert"
        assert prom_rule["expr"] == "test > 100"
        assert prom_rule["for"] == "5m"
        assert prom_rule["labels"]["severity"] == "critical"
        assert prom_rule["labels"]["component"] == "test"


class TestAlertRuleSet:
    """Tests for AlertRuleSet."""

    @pytest.fixture
    def ruleset(self) -> AlertRuleSet:
        return AlertRuleSet()

    def test_default_rules_loaded(self, ruleset: AlertRuleSet) -> None:
        assert ruleset.count > 0
        assert ruleset.count == len(DEFAULT_ALERT_RULES)

    def test_validates(self, ruleset: AlertRuleSet) -> None:
        errors = ruleset.validate()
        assert errors == [], f"Validation errors: {errors}"

    def test_has_circuit_breaker_rules(self, ruleset: AlertRuleSet) -> None:
        """Must have rules for finality, slashing, and participation."""
        cb_rules = ruleset.get_circuit_breaker_rules()
        assert len(cb_rules) >= 3

        rule_names = [r.name for r in cb_rules]
        assert any("Finality" in n for n in rule_names)
        assert any("Slashing" in n for n in rule_names)
        assert any("Participation" in n for n in rule_names)

    def test_has_critical_rules(self, ruleset: AlertRuleSet) -> None:
        critical = ruleset.get_by_severity("critical")
        assert len(critical) >= 3

    def test_has_warning_rules(self, ruleset: AlertRuleSet) -> None:
        warnings = ruleset.get_by_severity("warning")
        assert len(warnings) >= 2

    def test_no_duplicate_names(self, ruleset: AlertRuleSet) -> None:
        names = [r.name for r in ruleset.rules]
        assert len(names) == len(set(names))

    def test_add_rule(self, ruleset: AlertRuleSet) -> None:
        initial_count = ruleset.count
        ruleset.add_rule(
            AlertRule(name="CustomAlert", expression="custom > 0")
        )
        assert ruleset.count == initial_count + 1

    def test_to_prometheus_rules(self, ruleset: AlertRuleSet) -> None:
        output = ruleset.to_prometheus_rules()
        assert "groups" in output
        assert len(output["groups"]) == 1
        group = output["groups"][0]
        assert group["name"] == "chaoswopr_alerts"
        assert len(group["rules"]) == ruleset.count

    def test_finality_delay_rule(self, ruleset: AlertRuleSet) -> None:
        """FinalityDelayHigh rule must be present and correctly configured."""
        rules = [r for r in ruleset.rules if r.name == "FinalityDelayHigh"]
        assert len(rules) == 1
        rule = rules[0]
        assert rule.severity == "critical"
        assert "finalized" in rule.expression.lower() or "finality" in rule.expression.lower()

    def test_slashing_rule(self, ruleset: AlertRuleSet) -> None:
        rules = [r for r in ruleset.rules if r.name == "SlashingRateHigh"]
        assert len(rules) == 1
        assert rules[0].severity == "critical"

    def test_participation_rule(self, ruleset: AlertRuleSet) -> None:
        rules = [r for r in ruleset.rules if r.name == "ParticipationRateLow"]
        assert len(rules) == 1
        assert rules[0].severity == "critical"

    def test_custom_ruleset(self) -> None:
        rules = [
            AlertRule(name="Custom1", expression="a > 1"),
            AlertRule(name="Custom2", expression="b > 2"),
        ]
        ruleset = AlertRuleSet(rules=rules, group_name="custom")
        assert ruleset.count == 2

    def test_validate_duplicate_names(self) -> None:
        rules = [
            AlertRule(name="Same", expression="a > 1"),
            AlertRule(name="Same", expression="b > 2"),
        ]
        ruleset = AlertRuleSet(rules=rules)
        errors = ruleset.validate()
        assert any("Duplicate" in e for e in errors)

    def test_validate_empty_expression(self) -> None:
        rules = [
            AlertRule(name="Empty", expression=""),
        ]
        ruleset = AlertRuleSet(rules=rules)
        errors = ruleset.validate()
        assert any("empty expression" in e for e in errors)
