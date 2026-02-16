"""End-to-end test conftest - fixtures for full system integration tests."""

from __future__ import annotations

import pytest


# All e2e tests are automatically marked
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Automatically mark all tests in this directory as e2e tests."""
    for item in items:
        item.add_marker(pytest.mark.e2e)
