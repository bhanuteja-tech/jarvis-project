"""Explicitly opt-in live smoke test against the real Greenhouse API.

This test is EXCLUDED from normal pytest runs twice over:

1. The ``live`` marker is deselected by default (see pyproject ``addopts``).
2. Even with ``-m live``, it requires the environment variable
   ``JARVIS_RUN_LIVE_SMOKE=1``.

Run it explicitly with::

    JARVIS_RUN_LIVE_SMOKE=1 pytest -m live tests/test_greenhouse_live_smoke.py

It makes exactly ONE request to one public board and never mutates anything.
"""

from __future__ import annotations

import os

import pytest

from app.sources.greenhouse.client import GreenhouseClient
from tests.support import make_settings

pytestmark = [pytest.mark.live]

DEFAULT_SMOKE_BOARD_TOKEN = "stripe"


def _smoke_enabled() -> bool:
    return os.environ.get("JARVIS_RUN_LIVE_SMOKE") == "1"


async def test_live_greenhouse_smoke() -> None:
    if not _smoke_enabled():
        pytest.skip(
            "live smoke disabled by default; run explicitly with "
            "JARVIS_RUN_LIVE_SMOKE=1 pytest -m live"
        )

    token = os.environ.get("JARVIS_LIVE_SMOKE_BOARD_TOKEN", DEFAULT_SMOKE_BOARD_TOKEN)
    settings = make_settings(greenhouse_max_retries=1)

    async with GreenhouseClient(settings) as client:
        payload = await client.list_jobs(token)

    jobs = payload.get("jobs")
    assert isinstance(jobs, list)
    total = (payload.get("meta") or {}).get("total")
    print(f"\nlive smoke OK: board={token!r} posts_returned={len(jobs)} meta_total={total}")
