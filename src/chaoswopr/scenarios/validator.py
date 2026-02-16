"""Scenario YAML validator for chaoswopr.

Validates scenario YAML files against the JSON Schema and performs
semantic validation (e.g., blast radius percentages, client distribution sums).

Usage:
    python -m chaoswopr.scenarios.validator path/to/scenario.yaml
    validate-scenario path/to/scenario.yaml
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
import jsonschema
import yaml

SCHEMA_PATH = Path(__file__).parent.parent.parent.parent / "config" / "schema" / "scenario_schema.json"


@dataclass
class ValidationResult:
    """Result of validating a scenario file."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scenario_name: str = ""

    def add_error(self, message: str) -> None:
        """Add a validation error."""
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a validation warning."""
        self.warnings.append(message)


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load the scenario JSON Schema from disk.

    Args:
        schema_path: Path to the schema file. Defaults to the built-in schema.

    Returns:
        The parsed JSON Schema dictionary.

    Raises:
        FileNotFoundError: If the schema file does not exist.
        json.JSONDecodeError: If the schema file is not valid JSON.
    """
    path = schema_path or SCHEMA_PATH
    if not path.exists():
        raise FileNotFoundError(f"Schema not found at {path}")
    with open(path) as f:
        return json.load(f)


def load_scenario(scenario_path: Path) -> dict[str, Any]:
    """Load a scenario YAML file from disk.

    Args:
        scenario_path: Path to the scenario YAML file.

    Returns:
        The parsed scenario dictionary.

    Raises:
        FileNotFoundError: If the scenario file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    if not scenario_path.exists():
        raise FileNotFoundError(f"Scenario file not found at {scenario_path}")
    with open(scenario_path) as f:
        return yaml.safe_load(f)


def validate_schema(scenario: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Validate a scenario against the JSON Schema.

    Args:
        scenario: The scenario dictionary to validate.
        schema: The JSON Schema to validate against.

    Returns:
        List of validation error messages. Empty list means valid.
    """
    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(scenario), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.path) or "(root)"
        errors.append(f"Schema error at {path}: {error.message}")
    return errors


def validate_semantic(scenario: dict[str, Any]) -> ValidationResult:
    """Perform semantic validation beyond JSON Schema.

    Checks:
    - Client distribution ratios sum to approximately 1.0
    - Blast radius phased rollout is in ascending order
    - Blast radius phased rollout values do not exceed max_affected_percent
    - Fault sequence has at least one 'baseline' or 'observe' action
    - Fault sequence has a 'complete' action as the last step
    - Time values in fault sequence are monotonically increasing

    Args:
        scenario: The scenario dictionary to validate.

    Returns:
        ValidationResult with semantic errors and warnings.
    """
    result = ValidationResult(valid=True, scenario_name=scenario.get("name", "unknown"))

    # Check client distribution sums
    network_config = scenario.get("network_config", {})
    client_dist = network_config.get("client_distribution", {})

    for layer in ["execution", "consensus"]:
        dist = client_dist.get(layer, {})
        if dist:
            total = sum(dist.values())
            if abs(total - 1.0) > 0.01:
                result.add_error(
                    f"Client distribution for '{layer}' sums to {total:.3f}, "
                    f"expected approximately 1.0"
                )

    # Check blast radius phased rollout
    blast_radius = scenario.get("blast_radius", {})
    max_affected = blast_radius.get("max_affected_percent", 0)
    phased_rollout = blast_radius.get("phased_rollout", [])

    if phased_rollout:
        # Check ascending order
        for i in range(1, len(phased_rollout)):
            if phased_rollout[i] <= phased_rollout[i - 1]:
                result.add_error(
                    f"Phased rollout must be in ascending order, "
                    f"but {phased_rollout[i]} <= {phased_rollout[i-1]}"
                )
                break

        # Check max value
        if phased_rollout and phased_rollout[-1] > max_affected and max_affected > 0:
            result.add_warning(
                f"Phased rollout final step ({phased_rollout[-1]}%) "
                f"exceeds max_affected_percent ({max_affected}%)"
            )

    # Check fault sequence structure
    fault_sequence = scenario.get("fault_sequence", [])
    if fault_sequence:
        # Check for baseline/observe action
        actions = [step.get("action") for step in fault_sequence]
        if "baseline" not in actions and "observe" not in actions:
            result.add_warning("Fault sequence has no 'baseline' or 'observe' action")

        # Check last action is 'complete'
        if actions[-1] != "complete":
            result.add_warning("Fault sequence does not end with 'complete' action")

        # Check time monotonicity
        times = []
        for step in fault_sequence:
            time_str = step.get("time", "0s")
            try:
                seconds = parse_time_string(time_str)
                times.append(seconds)
            except ValueError:
                result.add_error(f"Invalid time format: {time_str}")

        for i in range(1, len(times)):
            if times[i] < times[i - 1]:
                result.add_error(
                    f"Fault sequence times must be monotonically increasing, "
                    f"but step {i+1} ({fault_sequence[i].get('time')}) "
                    f"is before step {i} ({fault_sequence[i-1].get('time')})"
                )
                break

    # Safety check: blast radius must not exceed 33%
    if max_affected > 33.0:
        result.add_error(
            f"Blast radius max_affected_percent ({max_affected}%) exceeds safety limit of 33%"
        )

    return result


def parse_time_string(time_str: str) -> int:
    """Parse a time string (e.g., '60s', '5m', '1h') into seconds.

    Args:
        time_str: Time string to parse.

    Returns:
        Time value in seconds.

    Raises:
        ValueError: If the time string format is invalid.
    """
    if not time_str:
        raise ValueError("Empty time string")

    unit = time_str[-1]
    try:
        value = int(time_str[:-1])
    except ValueError:
        raise ValueError(f"Invalid time value: {time_str}")

    multipliers = {"s": 1, "m": 60, "h": 3600}
    if unit not in multipliers:
        raise ValueError(f"Invalid time unit: {unit} (expected s, m, or h)")

    return value * multipliers[unit]


def validate_scenario(
    scenario: dict[str, Any],
    schema: dict[str, Any] | None = None,
    schema_path: Path | None = None,
) -> ValidationResult:
    """Perform full validation of a scenario (schema + semantic).

    Args:
        scenario: The scenario dictionary to validate.
        schema: Pre-loaded JSON Schema (optional).
        schema_path: Path to the schema file (optional, uses default if not provided).

    Returns:
        ValidationResult with all errors and warnings.
    """
    if schema is None:
        schema = load_schema(schema_path)

    result = ValidationResult(valid=True, scenario_name=scenario.get("name", "unknown"))

    # Schema validation
    schema_errors = validate_schema(scenario, schema)
    for error in schema_errors:
        result.add_error(error)

    # Semantic validation (only if schema validation passes to avoid confusing errors)
    if result.valid:
        semantic_result = validate_semantic(scenario)
        result.errors.extend(semantic_result.errors)
        result.warnings.extend(semantic_result.warnings)
        if semantic_result.errors:
            result.valid = False

    return result


def validate_scenario_file(
    scenario_path: Path,
    schema_path: Path | None = None,
) -> ValidationResult:
    """Validate a scenario YAML file.

    Args:
        scenario_path: Path to the scenario YAML file.
        schema_path: Path to the schema file (optional).

    Returns:
        ValidationResult with all errors and warnings.
    """
    try:
        scenario = load_scenario(scenario_path)
    except FileNotFoundError as e:
        return ValidationResult(valid=False, errors=[str(e)])
    except yaml.YAMLError as e:
        return ValidationResult(valid=False, errors=[f"YAML parse error: {e}"])

    return validate_scenario(scenario, schema_path=schema_path)


@click.command()
@click.argument("scenario_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--schema",
    "schema_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to custom JSON Schema file",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def main(scenario_path: Path, schema_path: Path | None, verbose: bool) -> None:
    """Validate a scenario YAML file against the chaoswopr schema."""
    result = validate_scenario_file(scenario_path, schema_path)

    if result.valid:
        click.echo(f"VALID: {scenario_path}")
        if result.warnings:
            for warning in result.warnings:
                click.echo(f"  WARNING: {warning}")
    else:
        click.echo(f"INVALID: {scenario_path}")
        for error in result.errors:
            click.echo(f"  ERROR: {error}")
        if result.warnings:
            for warning in result.warnings:
                click.echo(f"  WARNING: {warning}")
        sys.exit(1)

    if verbose:
        click.echo(f"  Scenario: {result.scenario_name}")
        click.echo(f"  Errors: {len(result.errors)}")
        click.echo(f"  Warnings: {len(result.warnings)}")


if __name__ == "__main__":
    main()
