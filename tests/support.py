"""Shared test infrastructure.

The default test suite NEVER touches the network: all HTTP is served by
httpx.MockTransport. Sleeps and jitter are injected fakes so retry paths are
instant and deterministic.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from app.config.settings import Settings
from app.sources.greenhouse.client import GreenhouseClient
from app.sources.lever.client import LeverClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "greenhouse"
LEVER_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "lever"

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
LEVER_BASE_URL = "https://api.lever.co/v0/postings"

TOKEN = "example_corp"
SITE = "examplecorp"


def load_lever_fixture(name: str) -> Any:
    return json.loads((LEVER_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def load_fixture_text(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def load_fixture(name: str) -> Any:
    return json.loads(load_fixture_text(name))


def make_settings(**overrides: Any) -> Settings:
    unknown = set(overrides) - set(Settings.model_fields)
    if unknown:
        raise TypeError(f"unknown settings overrides: {sorted(unknown)}")
    values: dict[str, Any] = {
        "database_url": "postgresql+psycopg://user:secret@localhost:5432/jarvis",
        "greenhouse_base_url": BASE_URL,
        "lever_base_url": LEVER_BASE_URL,
        "greenhouse_timeout_seconds": 30.0,
        "lever_timeout_seconds": 30.0,
        "greenhouse_max_retries": 3,
        "lever_max_retries": 3,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(**values)


class FakeSleeper:
    """Records requested delays instead of actually sleeping."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)


def deterministic_jitter(factor: float = 0.5) -> Callable[[float], float]:
    """Maps delay -> delay * factor so backoff math is exactly predictable."""

    def _jitter(delay: float) -> float:
        return delay * factor

    return _jitter


class ScriptedRouter:
    """httpx.MockTransport handler executing a queued script of outcomes.

    Outcomes may be:
      - ``httpx.Response`` instances (returned verbatim),
      - ``Exception`` instances (raised),
      - callables ``request -> Response | Exception`` (invoked lazily).
    Records every request for later assertions.
    """

    Outcome = httpx.Response | Exception | Callable[[httpx.Request], "httpx.Response | Exception"]

    def __init__(self, *outcomes: Outcome) -> None:
        self._outcomes: list[Any] = list(outcomes)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("unexpected extra HTTP request")
        outcome = self._outcomes.pop(0)
        if callable(outcome):
            outcome = outcome(request)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def call_count(self) -> int:
        return len(self.requests)

    @property
    def last_request(self) -> httpx.Request | None:
        return self.requests[-1] if self.requests else None


def connect_timeout(request: httpx.Request) -> Exception:
    return httpx.ConnectTimeout("connection timed out", request=request)


def connection_refused(request: httpx.Request) -> Exception:
    return httpx.ConnectError("connection refused", request=request)


def make_client(
    router: ScriptedRouter,
    *,
    sleeper: FakeSleeper | None = None,
    jitter: Callable[[float], float] | None = None,
    **settings_overrides: Any,
) -> GreenhouseClient:
    settings = make_settings(**settings_overrides)
    return GreenhouseClient(
        settings,
        transport=httpx.MockTransport(router),
        sleep=sleeper.sleep if sleeper is not None else None,
        jitter_rng=jitter,
    )


def make_lever_client(
    router: ScriptedRouter,
    *,
    sleeper: FakeSleeper | None = None,
    jitter: Callable[[float], float] | None = None,
    **settings_overrides: Any,
) -> LeverClient:
    settings = make_settings(**settings_overrides)
    return LeverClient(
        settings,
        transport=httpx.MockTransport(router),
        sleep=sleeper.sleep if sleeper is not None else None,
        jitter_rng=jitter,
    )


def json_response(
    payload: Any,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
