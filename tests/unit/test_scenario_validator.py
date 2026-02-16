"""Unit tests for the scenario validator CLI and validation logic.

Tests the validator module's ability to:
- Load and validate scenarios against the JSON Schema
- Perform semantic validation (client distributions, blast radius, etc.)
- Parse time strings
- Report errors and warnings correctly
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from chaoswopr.scenarios.validator import (
    ValidationResult,
    load_schema,
    parse_time_string,
    validate_scenario,
    validate_scenario_file,
    validate_schema,
    validate_semantic,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sample_configs"


class TestParseTimeString:
    """Tests for the parse_time_string utility."""

    def test_parse_seconds(self) -> None:
        assert parse_time_string("0s") == 0
        assert parse_time_string("60s") == 60
        assert parse_time_string("300s") == 300

    def test_parse_minutes(self) -> None:
        assert parse_time_string("1m") == 60
        assert parse_time_string("5m") == 300
        assert parse_time_string("30m") == 1800

    def test_parse_hours(self) -> None:
        assert parse_time_string("1h") == 3600
        assert parse_time_string("2h") == 7200

    def test_invalid_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Empty time string"):
            parse_time_string("")

    def test_invalid_unit(self) -> None:
        with pytest.raises(ValueError, match="Invalid time unit"):
            parse_time_string("60d")

    def test_invalid_value(self) -> None:
        with pytest.raises(ValueError, match="Invalid time value"):
            parse_time_string("abcs")


class TestLoadSchema:
    """Tests for loading the JSON Schema."""

    def test_load_default_schema(self) -> None:
        """The default schema should load successfully."""
        schema = load_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema

    def test_load_nonexistent_schema_raises(self, tmp_path: Path) -> None:
        """Loading a nonexistent schema file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_schema(tmp_path / "nonexistent.json")


class TestValidateSchema:
    """Tests for JSON Schema validation."""

    @pytest.fixture
    def schema(self) -> dict[str, Any]:
        return load_schema()

    def test_valid_scenario_passes(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        errors = validate_schema(valid_scenario_yaml, schema)
        assert errors == []

    def test_missing_required_field_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        del valid_scenario_yaml["hypothesis"]
        errors = validate_schema(valid_scenario_yaml, schema)
        assert len(errors) > 0
        assert any("hypothesis" in e for e in errors)

    def test_invalid_type_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        valid_scenario_yaml["fault_sequence"] = "not an array"
        errors = validate_schema(valid_scenario_yaml, schema)
        assert len(errors) > 0


class TestValidateSemantic:
    """Tests for semantic validation beyond JSON Schema."""

    def test_valid_scenario_passes(self, valid_scenario_yaml: dict[str, Any]) -> None:
        result = validate_semantic(valid_scenario_yaml)
        assert result.valid
        assert len(result.errors) == 0

    def test_client_distribution_not_summing_to_one_fails(
        self, valid_scenario_yaml: dict[str, Any]
    ) -> None:
        valid_scenario_yaml["network_config"]["client_distribution"]["execution"] = {
            "nethermind": 0.5,
            "geth": 0.6,
        }
        result = validate_semantic(valid_scenario_yaml)
        assert not result.valid
        assert any("execution" in e and "sums to" in e for e in result.errors)

    def test_consensus_distribution_not_summing_to_one_fails(
        self, valid_scenario_yaml: dict[str, Any]
    ) -> None:
        valid_scenario_yaml["network_config"]["client_distribution"]["consensus"] = {
            "prysm": 0.3,
            "lighthouse": 0.3,
        }
        result = validate_semantic(valid_scenario_yaml)
        assert not result.valid
        assert any("consensus" in e and "sums to" in e for e in result.errors)

    def test_phased_rollout_not_ascending_fails(
        self, valid_scenario_yaml: dict[str, Any]
    ) -> None:
        valid_scenario_yaml["blast_radius"]["phased_rollout"] = [20.0, 10.0, 5.0]
        valid_scenario_yaml["blast_radius"]["max_affected_percent"] = 20.0
        result = validate_semantic(valid_scenario_yaml)
        assert not result.valid
        assert any("ascending" in e for e in result.errors)

    def test_blast_radius_over_33_fails(
        self, valid_scenario_yaml: dict[str, Any]
    ) -> None:
        valid_scenario_yaml["blast_radius"]["max_affected_percent"] = 50.0
        result = validate_semantic(valid_scenario_yaml)
        assert not result.valid
        assert any("33%" in e for e in result.errors)

    def test_non_monotonic_times_fails(
        self, valid_scenario_yaml: dict[str, Any]
    ) -> None:
        valid_scenario_yaml["fault_sequence"] = [
            {"time": "60s", "action": "baseline"},
            {"time": "30s", "action": "observe"},
            {"time": "90s", "action": "complete"},
        ]
        result = validate_semantic(valid_scenario_yaml)
        assert not result.valid
        assert any("monotonically" in e for e in result.errors)

    def test_no_baseline_action_warns(
        self, valid_scenario_yaml: dict[str, Any]
    ) -> None:
        valid_scenario_yaml["fault_sequence"] = [
            {"time": "0s", "action": "inject_network_latency"},
            {"time": "60s", "action": "complete"},
        ]
        result = validate_semantic(valid_scenario_yaml)
        # This is a warning, not an error
        assert any("baseline" in w for w in result.warnings)

    def test_no_complete_action_warns(
        self, valid_scenario_yaml: dict[str, Any]
    ) -> None:
        valid_scenario_yaml["fault_sequence"] = [
            {"time": "0s", "action": "baseline"},
            {"time": "60s", "action": "observe"},
        ]
        result = validate_semantic(valid_scenario_yaml)
        assert any("complete" in w for w in result.warnings)


class TestValidateScenario:
    """Tests for the full validation pipeline."""

    def test_valid_scenario_passes(self, valid_scenario_yaml: dict[str, Any]) -> None:
        result = validate_scenario(valid_scenario_yaml)
        assert result.valid

    def test_invalid_scenario_fails(self, invalid_scenario_yaml: dict[str, Any]) -> None:
        result = validate_scenario(invalid_scenario_yaml)
        assert not result.valid
        assert len(result.errors) > 0


class TestValidateScenarioFile:
    """Tests for file-based validation."""

    def test_valid_file(self) -> None:
        result = validate_scenario_file(FIXTURES_DIR / "valid_scenario.yaml")
        assert result.valid

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        result = validate_scenario_file(tmp_path / "nonexistent.yaml")
        assert not result.valid
        assert any("not found" in e for e in result.errors)

    def test_invalid_yaml_file(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("{{invalid yaml: [}")
        result = validate_scenario_file(bad_yaml)
        assert not result.valid


class TestValidationResult:
    """Tests for the ValidationResult dataclass."""

    def test_initial_state(self) -> None:
        result = ValidationResult(valid=True)
        assert result.valid
        assert result.errors == []
        assert result.warnings == []

    def test_add_error(self) -> None:
        result = ValidationResult(valid=True)
        result.add_error("test error")
        assert not result.valid
        assert "test error" in result.errors

    def test_add_warning(self) -> None:
        result = ValidationResult(valid=True)
        result.add_warning("test warning")
        assert result.valid  # warnings don't invalidate
        assert "test warning" in result.warnings
