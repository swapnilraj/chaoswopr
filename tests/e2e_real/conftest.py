"""Conftest for real E2E tests.

These tests deploy full Ethereum testnets with monitoring and run
real scenarios end-to-end. They require Docker, Kurtosis, and
significant system resources (8GB+ RAM, 4+ CPU cores).
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark all tests in this directory as e2e_real."""
    for item in items:
        if "e2e_real" in str(item.fspath):
            item.add_marker(pytest.mark.e2e_real)
            item.add_marker(pytest.mark.timeout(900))
