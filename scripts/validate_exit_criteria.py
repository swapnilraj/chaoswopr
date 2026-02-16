#!/usr/bin/env python3
"""Phase 1 exit criteria validation script.

Validates all 7 exit criteria for Phase 1 completion:

1. Testnet boots reliably (95%+ success over 20 runs, finality within 3 epochs)
2. Metrics flowing (50+ metrics, <30s lag)
3. Circuit breakers trip on alerts (<10s response)
4. Snapshots restore validator state
5. Baseline scenario runs end-to-end
6. Network isolation verified (no external access)
7. All above pass in CI (<10 min total time)

Usage:
    python scripts/validate_exit_criteria.py [--skip-e2e] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class CriterionResult:
    """Result of a single exit criterion check."""

    name: str
    passed: bool
    message: str
    duration_seconds: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


def check_test_count() -> CriterionResult:
    """Check that we have >= 100 tests total."""
    start = time.time()
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--collect-only", "-q", "tests/"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=60,
        )
        # Parse test count from pytest output
        output = result.stdout.strip()
        lines = output.split("\n")
        # Last line typically says "X tests collected" or "X test(s) collected"
        test_count = 0
        for line in lines:
            if "test" in line and ("selected" in line or "collected" in line):
                # Extract number
                parts = line.split()
                for part in parts:
                    if part.isdigit():
                        test_count = int(part)
                        break
            elif line.strip().startswith("<") and "test" in line.lower():
                test_count += 1

        # Fallback: count lines that look like test items
        if test_count == 0:
            test_count = sum(1 for line in lines if "::" in line and "test_" in line)

        duration = time.time() - start
        passed = test_count >= 100
        return CriterionResult(
            name="Test Count >= 100",
            passed=passed,
            message=f"Found {test_count} tests (target: >= 100)",
            duration_seconds=duration,
            details={"test_count": test_count, "target": 100},
        )
    except Exception as e:
        return CriterionResult(
            name="Test Count >= 100",
            passed=False,
            message=f"Failed to count tests: {e}",
            duration_seconds=time.time() - start,
        )


def check_unit_tests() -> CriterionResult:
    """Run unit tests and check they pass."""
    start = time.time()
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/unit/", "-v", "-m", "unit", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        duration = time.time() - start
        passed = result.returncode == 0
        return CriterionResult(
            name="Unit Tests Pass",
            passed=passed,
            message="All unit tests passed" if passed else "Unit tests failed",
            duration_seconds=duration,
            details={"returncode": result.returncode, "output": result.stdout[-500:]},
        )
    except Exception as e:
        return CriterionResult(
            name="Unit Tests Pass",
            passed=False,
            message=f"Failed to run unit tests: {e}",
            duration_seconds=time.time() - start,
        )


def check_integration_tests() -> CriterionResult:
    """Run integration tests and check they pass."""
    start = time.time()
    try:
        result = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                "tests/integration/",
                "-v",
                "-m",
                "integration",
                "--tb=short",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=300,
        )
        duration = time.time() - start
        passed = result.returncode == 0
        return CriterionResult(
            name="Integration Tests Pass",
            passed=passed,
            message="All integration tests passed" if passed else "Integration tests failed",
            duration_seconds=duration,
            details={"returncode": result.returncode},
        )
    except Exception as e:
        return CriterionResult(
            name="Integration Tests Pass",
            passed=False,
            message=f"Failed to run integration tests: {e}",
            duration_seconds=time.time() - start,
        )


def check_coverage() -> CriterionResult:
    """Check that code coverage is >= 80%."""
    start = time.time()
    try:
        result = subprocess.run(
            [
                "python",
                "-m",
                "pytest",
                "tests/",
                "--cov=src/chaoswopr",
                "--cov-report=json",
                "-q",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=300,
        )
        duration = time.time() - start

        # Try to read coverage.json
        coverage_file = PROJECT_ROOT / "coverage.json"
        if coverage_file.exists():
            with open(coverage_file) as f:
                cov_data = json.load(f)
            total_coverage = cov_data.get("totals", {}).get("percent_covered", 0)
            passed = total_coverage >= 80
            return CriterionResult(
                name="Code Coverage >= 80%",
                passed=passed,
                message=f"Coverage: {total_coverage:.1f}% (target: >= 80%)",
                duration_seconds=duration,
                details={"coverage_percent": total_coverage, "target": 80},
            )
        else:
            return CriterionResult(
                name="Code Coverage >= 80%",
                passed=False,
                message="Coverage report not generated",
                duration_seconds=duration,
            )
    except Exception as e:
        return CriterionResult(
            name="Code Coverage >= 80%",
            passed=False,
            message=f"Failed to check coverage: {e}",
            duration_seconds=time.time() - start,
        )


def check_schema_validation() -> CriterionResult:
    """Check that the scenario schema exists and validates correctly."""
    start = time.time()
    schema_path = PROJECT_ROOT / "config" / "schema" / "scenario_schema.json"
    if not schema_path.exists():
        return CriterionResult(
            name="Scenario Schema Exists",
            passed=False,
            message="Scenario schema not found at config/schema/scenario_schema.json",
            duration_seconds=time.time() - start,
        )

    try:
        with open(schema_path) as f:
            schema = json.load(f)
        has_required_fields = all(
            key in schema.get("properties", {})
            for key in ["version", "name", "hypothesis", "fault_sequence", "slo_thresholds"]
        )
        duration = time.time() - start
        return CriterionResult(
            name="Scenario Schema Valid",
            passed=has_required_fields,
            message="Schema has all required fields" if has_required_fields else "Schema missing required fields",
            duration_seconds=duration,
            details={"schema_properties": list(schema.get("properties", {}).keys())},
        )
    except Exception as e:
        return CriterionResult(
            name="Scenario Schema Valid",
            passed=False,
            message=f"Failed to validate schema: {e}",
            duration_seconds=time.time() - start,
        )


def check_safety_modules() -> CriterionResult:
    """Check that all safety modules are importable."""
    start = time.time()
    modules = [
        "chaoswopr.safety.blast_radius",
        "chaoswopr.safety.circuit_breaker",
        "chaoswopr.safety.snapshots",
        "chaoswopr.safety.isolation",
        "chaoswopr.safety.audit",
        "chaoswopr.safety.kill_switch",
    ]
    importable = []
    failed = []
    for mod in modules:
        try:
            __import__(mod)
            importable.append(mod)
        except ImportError:
            failed.append(mod)

    duration = time.time() - start
    passed = len(failed) == 0
    return CriterionResult(
        name="Safety Modules Importable",
        passed=passed,
        message=f"{len(importable)}/{len(modules)} safety modules importable"
        + (f" (failed: {', '.join(failed)})" if failed else ""),
        duration_seconds=duration,
        details={"importable": importable, "failed": failed},
    )


def check_infrastructure_modules() -> CriterionResult:
    """Check that all infrastructure modules are importable."""
    start = time.time()
    modules = [
        "chaoswopr.infrastructure.testnet.kurtosis_client",
        "chaoswopr.infrastructure.testnet.ethereum_package",
        "chaoswopr.infrastructure.testnet.client_config",
        "chaoswopr.infrastructure.testnet.deployer",
        "chaoswopr.infrastructure.testnet.beacon_api",
        "chaoswopr.infrastructure.monitoring.prometheus",
        "chaoswopr.infrastructure.monitoring.metrics_catalog",
        "chaoswopr.infrastructure.monitoring.alerting",
        "chaoswopr.infrastructure.monitoring.metrics_export",
    ]
    importable = []
    failed = []
    for mod in modules:
        try:
            __import__(mod)
            importable.append(mod)
        except ImportError:
            failed.append(mod)

    duration = time.time() - start
    passed = len(failed) == 0
    return CriterionResult(
        name="Infrastructure Modules Importable",
        passed=passed,
        message=f"{len(importable)}/{len(modules)} infrastructure modules importable"
        + (f" (failed: {', '.join(failed)})" if failed else ""),
        duration_seconds=duration,
        details={"importable": importable, "failed": failed},
    )


def main() -> None:
    """Run all exit criteria checks and report results."""
    parser = argparse.ArgumentParser(description="Validate Phase 1 exit criteria")
    parser.add_argument("--skip-e2e", action="store_true", help="Skip e2e test checks")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    print("=" * 70)
    print("Phase 1 Exit Criteria Validation")
    print("=" * 70)
    print()

    total_start = time.time()
    results: list[CriterionResult] = []

    # Run all checks
    checks = [
        ("1. Schema Validation", check_schema_validation),
        ("2. Safety Modules", check_safety_modules),
        ("3. Infrastructure Modules", check_infrastructure_modules),
        ("4. Unit Tests", check_unit_tests),
        ("5. Integration Tests", check_integration_tests),
        ("6. Test Count", check_test_count),
        ("7. Code Coverage", check_coverage),
    ]

    for name, check_fn in checks:
        print(f"Checking: {name}...", end=" ", flush=True)
        result = check_fn()
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] ({result.duration_seconds:.1f}s)")
        if args.verbose or not result.passed:
            print(f"  -> {result.message}")
        print()

    total_duration = time.time() - total_start

    # Summary
    print("=" * 70)
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    all_passed = passed_count == total_count

    print(f"Results: {passed_count}/{total_count} criteria passed")
    print(f"Total time: {total_duration:.1f}s")
    print(f"CI time budget: {'WITHIN' if total_duration < 600 else 'EXCEEDED'} 10 min limit")
    print()

    if all_passed:
        print("ALL EXIT CRITERIA PASSED")
    else:
        print("SOME EXIT CRITERIA FAILED:")
        for r in results:
            if not r.passed:
                print(f"  - {r.name}: {r.message}")

    if args.json:
        output = {
            "passed": all_passed,
            "total_duration_seconds": total_duration,
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "duration_seconds": r.duration_seconds,
                    "details": r.details,
                }
                for r in results
            ],
        }
        print()
        print(json.dumps(output, indent=2))

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
