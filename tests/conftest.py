"""Pytest configuration. Shared helpers live in ``tests.support``."""

from __future__ import annotations

import pytest

from tests.support import FakeSleeper


@pytest.fixture
def fake_sleeper() -> FakeSleeper:
    """A sleep double that records delays instead of blocking."""
    return FakeSleeper()
