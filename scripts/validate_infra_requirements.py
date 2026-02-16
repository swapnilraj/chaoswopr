#!/usr/bin/env python3
"""Infrastructure requirements validation for real integration tests.

Checks that all prerequisites are available before running real
infrastructure tests (tests/integration_real/ and tests/e2e_real/).

Prerequisites:
- Docker daemon running
- Kurtosis CLI installed (>= 1.0.0)
- Kurtosis engine running
- Sufficient system resources (4+ GB RAM available, 2+ CPU cores)

Usage:
    python scripts/validate_infra_requirements.py [--verbose] [--json]
    python scripts/validate_infra_requirements.py --check docker
    python scripts/validate_infra_requirements.py --check kurtosis
    python scripts/validate_infra_requirements.py --check all

Exit codes:
    0 - All requirements met
    1 - One or more requirements not met
    2 - Script error
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    """Result of an infrastructure check."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    required: bool = True


def check_docker_installed() -> CheckResult:
    """Check if Docker CLI is installed."""
    docker_path = shutil.which("docker")
    if docker_path is None:
        return CheckResult(
            name="Docker CLI",
            passed=False,
            message="Docker CLI not found in PATH",
        )

    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() if result.returncode == 0 else "unknown"
        return CheckResult(
            name="Docker CLI",
            passed=result.returncode == 0,
            message=f"Docker CLI available: {version}",
            details={"path": docker_path, "version": version},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return CheckResult(
            name="Docker CLI",
            passed=False,
            message=f"Docker CLI check failed: {e}",
        )


def check_docker_running() -> CheckResult:
    """Check if Docker daemon is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return CheckResult(
                name="Docker Daemon",
                passed=True,
                message="Docker daemon is running",
            )
        else:
            return CheckResult(
                name="Docker Daemon",
                passed=False,
                message="Docker daemon not running (try: docker start / open Docker Desktop)",
                details={"stderr": result.stderr[:200]},
            )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return CheckResult(
            name="Docker Daemon",
            passed=False,
            message=f"Docker daemon check failed: {e}",
        )


def check_kurtosis_installed() -> CheckResult:
    """Check if Kurtosis CLI is installed."""
    kurtosis_path = shutil.which("kurtosis")
    if kurtosis_path is None:
        return CheckResult(
            name="Kurtosis CLI",
            passed=False,
            message="Kurtosis CLI not found in PATH (install: https://docs.kurtosis.com/install)",
        )

    try:
        result = subprocess.run(
            ["kurtosis", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() if result.returncode == 0 else "unknown"
        return CheckResult(
            name="Kurtosis CLI",
            passed=result.returncode == 0,
            message=f"Kurtosis CLI available: {version}",
            details={"path": kurtosis_path, "version": version},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return CheckResult(
            name="Kurtosis CLI",
            passed=False,
            message=f"Kurtosis CLI check failed: {e}",
        )


def check_kurtosis_engine() -> CheckResult:
    """Check if the Kurtosis engine is running."""
    try:
        result = subprocess.run(
            ["kurtosis", "engine", "status"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        is_running = result.returncode == 0 and "RUNNING" in result.stdout.upper()
        if is_running:
            return CheckResult(
                name="Kurtosis Engine",
                passed=True,
                message="Kurtosis engine is running",
            )
        else:
            return CheckResult(
                name="Kurtosis Engine",
                passed=False,
                message="Kurtosis engine not running (try: kurtosis engine start)",
                details={"stdout": result.stdout[:200], "stderr": result.stderr[:200]},
            )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return CheckResult(
            name="Kurtosis Engine",
            passed=False,
            message=f"Kurtosis engine check failed: {e}",
        )


def check_system_resources() -> CheckResult:
    """Check if system has sufficient resources for testnet deployment."""
    details: dict[str, Any] = {}

    try:
        cpu_count = os.cpu_count() or 0
        details["cpu_count"] = cpu_count
    except Exception:
        cpu_count = 0

    # Check available memory (platform-specific)
    available_gb = 0.0
    try:
        if platform.system() == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                total_bytes = int(result.stdout.strip())
                available_gb = total_bytes / (1024**3)
        elif platform.system() == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if "MemAvailable" in line:
                        kb = int(line.split()[1])
                        available_gb = kb / (1024**2)
                        break
        details["available_memory_gb"] = round(available_gb, 1)
    except Exception:
        pass

    has_enough_cpu = cpu_count >= 2
    has_enough_memory = available_gb >= 4.0

    if has_enough_cpu and has_enough_memory:
        return CheckResult(
            name="System Resources",
            passed=True,
            message=f"Sufficient resources: {cpu_count} CPUs, {available_gb:.1f}GB RAM",
            details=details,
            required=False,
        )
    else:
        issues = []
        if not has_enough_cpu:
            issues.append(f"Need 2+ CPUs (found {cpu_count})")
        if not has_enough_memory:
            issues.append(f"Need 4+ GB RAM (found {available_gb:.1f}GB)")
        return CheckResult(
            name="System Resources",
            passed=False,
            message=f"Insufficient resources: {'; '.join(issues)}",
            details=details,
            required=False,
        )


def check_python_packages() -> CheckResult:
    """Check if required Python test packages are installed."""
    required = ["pytest", "requests", "testcontainers"]
    installed = []
    missing = []

    for pkg in required:
        try:
            __import__(pkg)
            installed.append(pkg)
        except ImportError:
            missing.append(pkg)

    passed = len(missing) == 0
    return CheckResult(
        name="Python Test Packages",
        passed=passed,
        message=f"{len(installed)}/{len(required)} packages installed"
        + (f" (missing: {', '.join(missing)})" if missing else ""),
        details={"installed": installed, "missing": missing},
    )


def run_all_checks(check_type: str = "all") -> list[CheckResult]:
    """Run all infrastructure checks.

    Args:
        check_type: Which checks to run ("all", "docker", "kurtosis").

    Returns:
        List of CheckResult objects.
    """
    results = []

    if check_type in ("all", "docker"):
        results.append(check_docker_installed())
        results.append(check_docker_running())

    if check_type in ("all", "kurtosis"):
        results.append(check_kurtosis_installed())
        results.append(check_kurtosis_engine())

    if check_type == "all":
        results.append(check_system_resources())
        results.append(check_python_packages())

    return results


def main() -> None:
    """Run infrastructure requirement checks."""
    parser = argparse.ArgumentParser(description="Validate infrastructure requirements")
    parser.add_argument(
        "--check",
        choices=["all", "docker", "kurtosis"],
        default="all",
        help="Which checks to run",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = run_all_checks(args.check)

    if args.json:
        output = {
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "required": r.required,
                    "details": r.details,
                }
                for r in results
            ],
            "all_passed": all(r.passed for r in results if r.required),
        }
        print(json.dumps(output, indent=2))
    else:
        print("Infrastructure Requirements Check")
        print("=" * 50)
        for r in results:
            status = "PASS" if r.passed else ("FAIL" if r.required else "WARN")
            marker = "[x]" if r.passed else ("[ ]" if r.required else "[~]")
            print(f"  {marker} {r.name}: {status}")
            if args.verbose or not r.passed:
                print(f"      {r.message}")
        print()

        required_results = [r for r in results if r.required]
        all_required_pass = all(r.passed for r in required_results)

        if all_required_pass:
            print("All required infrastructure checks passed.")
            print("Real infrastructure tests can be run.")
        else:
            print("Some required checks failed.")
            print("Real infrastructure tests will be skipped.")
            failed = [r for r in required_results if not r.passed]
            print(f"\nFix these {len(failed)} issue(s):")
            for r in failed:
                print(f"  - {r.name}: {r.message}")

    all_required_pass = all(r.passed for r in results if r.required)
    sys.exit(0 if all_required_pass else 1)


if __name__ == "__main__":
    main()
