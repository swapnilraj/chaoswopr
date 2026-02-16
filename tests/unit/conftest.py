"""Unit test conftest - lightweight fixtures with no external dependencies."""

from __future__ import annotations

import pytest


# All unit tests are automatically marked
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Automatically mark all tests in this directory as unit tests."""
    for item in items:
        item.add_marker(pytest.mark.unit)
