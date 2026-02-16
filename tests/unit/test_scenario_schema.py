"""Unit tests for the scenario JSON Schema definition.

Tests that the schema itself is valid and correctly validates/rejects scenarios.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

SCHEMA_PATH = Path(__file__).parent.parent.parent / "config" / "schema" / "scenario_schema.json"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sample_configs"


@pytest.fixture
def schema() -> dict[str, Any]:
    """Load the scenario JSON Schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


class TestSchemaStructure:
    """Tests for the schema structure itself."""

    def test_schema_file_exists(self) -> None:
        """The scenario schema JSON file must exist."""
        assert SCHEMA_PATH.exists(), f"Schema not found at {SCHEMA_PATH}"

    def test_schema_is_valid_json(self) -> None:
        """The schema file must be valid JSON."""
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        assert isinstance(schema, dict)

    def test_schema_has_required_fields(self, schema: dict[str, Any]) -> None:
        """The schema must define all required top-level properties."""
        required = schema.get("required", [])
        assert "version" in required
        assert "name" in required
        assert "hypothesis" in required
        assert "fault_sequence" in required
        assert "slo_thresholds" in required
        assert "blast_radius" in required
        assert "success_criteria" in required

    def test_schema_has_property_definitions(self, schema: dict[str, Any]) -> None:
        """The schema must define properties for all required fields."""
        props = schema.get("properties", {})
        assert "version" in props
        assert "name" in props
        assert "hypothesis" in props
        assert "fault_sequence" in props
        assert "slo_thresholds" in props
        assert "blast_radius" in props
        assert "success_criteria" in props

    def test_schema_defines_network_config(self, schema: dict[str, Any]) -> None:
        """The schema must define the network_config property."""
        props = schema.get("properties", {})
        assert "network_config" in props
        net_props = props["network_config"].get("properties", {})
        assert "node_count" in net_props
        assert "client_distribution" in net_props

    def test_schema_defines_slo_thresholds(self, schema: dict[str, Any]) -> None:
        """The schema must define all SLO threshold properties."""
        slo_props = schema["properties"]["slo_thresholds"].get("properties", {})
        assert "finality_delay_max_epochs" in slo_props
        assert "slashing_rate_max_percent" in slo_props
        assert "participation_rate_min_percent" in slo_props

    def test_schema_blast_radius_max_33(self, schema: dict[str, Any]) -> None:
        """The blast radius max_affected_percent must cap at 33%."""
        br_props = schema["properties"]["blast_radius"]["properties"]
        max_affected = br_props["max_affected_percent"]
        assert max_affected.get("maximum") == 33

    def test_schema_defines_fault_actions(self, schema: dict[str, Any]) -> None:
        """The schema must define the valid fault action types."""
        fault_items = schema["properties"]["fault_sequence"]["items"]
        action_enum = fault_items["properties"]["action"]["enum"]
        assert "baseline" in action_enum
        assert "inject_network_latency" in action_enum
        assert "inject_packet_drops" in action_enum
        assert "kill_nodes" in action_enum
        assert "withhold_attestations" in action_enum
        assert "remove_faults" in action_enum
        assert "complete" in action_enum

    def test_schema_no_additional_properties(self, schema: dict[str, Any]) -> None:
        """The schema must not allow additional top-level properties."""
        assert schema.get("additionalProperties") is False


class TestSchemaValidation:
    """Tests for validating scenarios against the schema."""

    def test_valid_scenario_passes(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A valid scenario must pass schema validation."""
        jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_valid_scenario_file_passes(self, schema: dict[str, Any]) -> None:
        """The sample valid_scenario.yaml file must pass validation."""
        with open(FIXTURES_DIR / "valid_scenario.yaml") as f:
            scenario = yaml.safe_load(f)
        jsonschema.validate(instance=scenario, schema=schema)

    def test_network_partition_scenario_passes(self, schema: dict[str, Any]) -> None:
        """The network partition scenario must pass validation."""
        with open(FIXTURES_DIR / "network_partition_scenario.yaml") as f:
            scenario = yaml.safe_load(f)
        jsonschema.validate(instance=scenario, schema=schema)

    def test_missing_version_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario missing 'version' must fail validation."""
        del valid_scenario_yaml["version"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_missing_hypothesis_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario missing 'hypothesis' must fail validation."""
        del valid_scenario_yaml["hypothesis"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_missing_fault_sequence_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario missing 'fault_sequence' must fail validation."""
        del valid_scenario_yaml["fault_sequence"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_missing_slo_thresholds_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario missing 'slo_thresholds' must fail validation."""
        del valid_scenario_yaml["slo_thresholds"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_missing_blast_radius_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario missing 'blast_radius' must fail validation."""
        del valid_scenario_yaml["blast_radius"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_invalid_version_format_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario with invalid version format must fail validation."""
        valid_scenario_yaml["version"] = "v1"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_invalid_name_format_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario with invalid name format must fail validation."""
        valid_scenario_yaml["name"] = "Invalid Name With Spaces"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_blast_radius_over_33_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario with blast radius over 33% must fail validation."""
        valid_scenario_yaml["blast_radius"]["max_affected_percent"] = 50.0
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_empty_fault_sequence_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario with empty fault sequence must fail validation."""
        valid_scenario_yaml["fault_sequence"] = []
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_invalid_fault_action_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario with an invalid fault action must fail validation."""
        valid_scenario_yaml["fault_sequence"][0]["action"] = "invalid_action"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_negative_node_count_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario with negative node count must fail validation."""
        valid_scenario_yaml["network_config"]["node_count"] = -1
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_node_count_over_500_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario with node count over 500 must fail validation."""
        valid_scenario_yaml["network_config"]["node_count"] = 501
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_additional_properties_fail(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A scenario with additional undefined properties must fail."""
        valid_scenario_yaml["unknown_field"] = "should fail"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_hypothesis_too_short_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A hypothesis shorter than 10 characters must fail."""
        valid_scenario_yaml["hypothesis"] = "Too short"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)

    def test_invalid_time_format_fails(
        self, schema: dict[str, Any], valid_scenario_yaml: dict[str, Any]
    ) -> None:
        """A fault sequence entry with invalid time format must fail."""
        valid_scenario_yaml["fault_sequence"][0]["time"] = "invalid"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=valid_scenario_yaml, schema=schema)
