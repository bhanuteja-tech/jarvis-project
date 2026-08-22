"""robots.txt gate: strict default, permissive opt-out, TTL cache."""

from __future__ import annotations

import httpx
import pytest

from app.sources.career.errors import (
    RobotsDisallowedError,
    RobotsUnavailableError,
)
from app.sources.career.fetch import GuardedFetcher
from app.sources.career.robots import RobotsGate
from tests.support import (
    FakeSleeper,
    ScriptedRouter,
    fake_resolver,
    make_settings,
)

URL = "https://jobs.example.com/jobs/ml-engineer-123"


def make_gate(
    router: ScriptedRouter,
    *,
    permissive: bool = False,
    attempts: int = 1,
) -> RobotsGate:
    settings = make_settings(
        career_robots_permissive=permissive, career_max_attempts=attempts
    )
    fetcher = GuardedFetcher(
        settings,
        transport=httpx.MockTransport(router),
        resolver=fake_resolver(),
    )
    return RobotsGate(fetcher, settings)


class TestVerdicts:
    async def test_disallowed_path_rejected(self) -> None:
        router = ScriptedRouter(
            httpx.Response(
                200,
                content=(
                    b"User-agent: jarvis-job-discovery\nDisallow: /\n"
                    "User-agent: *\nAllow: /\n"
                ),
                headers={"Content-Type": "text/plain"},
            )
        )
        gate = make_gate(router)

        with pytest.raises(RobotsDisallowedError):
            await gate.ensure_allowed(URL)

        assert router.call_count == 1  # page never requested

    async def test_allowed_path_passes(self) -> None:
        router = ScriptedRouter(
            httpx.Response(
                200,
                content=b"User-agent: *\nDisallow:",
                headers={"Content-Type": "text/plain"},
            )
        )
        gate = make_gate(router)

        warnings = await gate.ensure_allowed(URL)

        assert warnings == []

    async def test_missing_robots_treated_as_allowed(self) -> None:
        router = ScriptedRouter(httpx.Response(404, content=b"nope"))
        gate = make_gate(router)

        warnings = await gate.ensure_allowed(URL)

        assert warnings == []


class TestCorrection3FailureModes:
    async def test_strict_mode_rejects_when_robots_unavailable(self) -> None:
        router = ScriptedRouter(httpx.Response(500, content=b"boom"))
        gate = make_gate(router, permissive=False)

        with pytest.raises(RobotsUnavailableError) as excinfo:
            await gate.ensure_allowed(URL)

        assert excinfo.value.reason == "robots_unavailable"

    async def test_permissive_mode_proceeds_with_warning(self) -> None:
        router = ScriptedRouter(httpx.Response(500, content=b"boom"))
        gate = make_gate(router, permissive=True, attempts=1)
        sleeper = FakeSleeper()

        # Rebuild gate/fetcher pair with the injected sleeper for determinism.
        settings = make_settings(career_robots_permissive=True, career_max_attempts=1)
        from tests.support import deterministic_jitter

        fetcher = GuardedFetcher(
            settings,
            transport=httpx.MockTransport(router),
            sleep=sleeper.sleep,
            jitter_rng=deterministic_jitter(0.5),
            resolver=fake_resolver(),
        )
        gate = RobotsGate(fetcher, settings)

        warnings = await gate.ensure_allowed(URL)

        codes = [w.code for w in warnings]
        assert "robots_unavailable_proceeded" in codes


class TestCaching:
    async def test_verdict_cached_within_ttl(self) -> None:
        robots = httpx.Response(
            200,
            content=b"User-agent: *\nDisallow:",
            headers={"Content-Type": "text/plain"},
        )
        router = ScriptedRouter(robots)
        gate = make_gate(router)

        await gate.ensure_allowed(URL)
        await gate.ensure_allowed("https://jobs.example.com/jobs/other-role")

        assert router.call_count == 1  # second call served from cache
