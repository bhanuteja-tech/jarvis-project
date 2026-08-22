"""Explicitly opt-in live smoke test against the public Lever Postings API.

Excluded from normal runs twice over:
1. The ``live`` marker is deselected by default (see pyproject ``addopts``).
2. Even with ``-m live``, it requires ``JARVIS_RUN_LIVE_SMOKE=1``.

Run explicitly with::

    JARVIS_RUN_LIVE_SMOKE=1 pytest -m live tests/test_lever_live_smoke.py

Exactly ONE request against the PUBLIC Postings API (no credentials exist);
default site ``leverdemo``, overridable via ``JARVIS_LEVER_SMOKE_SITE``.
"""

from __future__ import annotations

import os

import pytest

from app.sources.lever.client import LeverClient
from tests.support import make_settings

pytestmark = [pytest.mark.live]

DEFAULT_SMOKE_SITE = "leverdemo"


def _smoke_enabled() -> bool:
    return os.environ.get("JARVIS_RUN_LIVE_SMOKE") == "1"


async def test_live_lever_smoke() -> None:
    if not _smoke_enabled():
        pytest.skip(
            "live smoke disabled by default; run explicitly with "
            "JARVIS_RUN_LIVE_SMOKE=1 pytest -m live"
        )

    site = os.environ.get("JARVIS_LEVER_SMOKE_SITE", DEFAULT_SMOKE_SITE)
    settings = make_settings(lever_max_retries=1)

    async with LeverClient(settings) as client:
        payload = await client.fetch_postings_page(site, limit=5)

    assert isinstance(payload, list)
    print(f"\nlive smoke OK: site={site!r} postings_returned={len(payload)} (limit=5)")
