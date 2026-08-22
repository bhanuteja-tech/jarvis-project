# AGENTS.md — Working Conventions for the Jarvis Project

## Project status / scope lock

Phase 1, Steps 1–3 (Greenhouse + Lever + SearchApi adapters) are the ONLY
implemented steps. Greenhouse and Lever are FROZEN; do not modify them
without reporting a genuine shared-infrastructure defect first.

Do not implement: Adzuna, career-page extraction, cross-source deduplication,
embeddings/semantics, ranking, resume tailoring, ATS scoring, auth, frontend,
queues/brokers. Phase order is locked; see README roadmap.

## Lever specifics

- Public Postings API ONLY (`GET /v0/postings/{site}?mode=json`); the
  authenticated Data API (`/v1`) is deliberately unused.
- Bare-array envelope; `{"data": ...}` (v1 shape) must be rejected as invalid.
- Offset pagination: stop on short/empty page, hard ceiling `lever_max_pages`,
  duplicate-id suppression across pages, `skip += len(page)`.
- `createdAt` is undocumented-but-observed epoch ms: parse defensively,
  treat as optional. No updated-at field exists → `source_updated_at` stays None.
- Lever `lists` are preserved verbatim in `extra`; NEVER promote them into
  requirements/responsibilities (Phase 2 owns semantic JD extraction).

## SearchApi specifics

- One endpoint serves both engines; the API key travels ONLY as an
  `Authorization: Bearer` header (`SecretStr` in settings, never logged,
  never in fixtures/examples). Retries burn paid quota → default retries=2.
- google_jobs request params are whitelisted to {q, gl, hl, location} plus
  the internal next_page_token. `time_period` is NOT documented for
  google_jobs and MUST NOT be sent (adapter drops it with a warning).
- google_search MAY use documented `time_period` values (last_30_minutes…)
  and paginates by numeric `page`. NEVER fetch the response's
  `pagination.next` URL (it is a raw google.com URL — SSRF-safe rule).
- Google Jobs provides NO job id and NO absolute timestamps. Identity:
  `gj:<htidocid>` extracted from sharing_link, else deterministic
  `derived:<uuid5(company|title|location)>`; recorded in
  `extra.identity_source`.
- `source_created_at` stays None for SearchApi jobs; relative display text
  ("1 day ago") is preserved verbatim as `extra.posted_at_display`, never
  converted to a datetime.
- Google Search results are discovery CANDIDATES for the future Career Page
  Extractor; they must never enter canonical jobs or `state.jobs`.

## Commands

```bash
pip install -e ".[dev]"          # setup
pytest                           # unit tests (NO network by default)
ruff check .                     # lint
alembic upgrade head             # apply migrations
uvicorn app.main:create_app --factory --reload
```

Opt-in extras:
- `JARVIS_TEST_DATABASE_URL=... pytest` — run DB persistence tests against a reachable PostgreSQL.
- `JARVIS_RUN_LIVE_SMOKE=1 pytest -m live` — single-request live Greenhouse smoke test.

## Architecture rules

- Layering is strict: `graph → sources → models`; `db` may import `models`,
  nothing in `models/` may import httpx/SQLAlchemy/LangGraph.
- Source adapters are the only components that talk to external APIs.
- All adapters share `app/sources/errors.py` + `app/sources/resilience.py`.
  Retry/backoff stays source-agnostic with injectable sleep/jitter.
- Canonical `Job` (`app/models/job.py`) never receives invented values;
  missing source data stays `None`. Internal timestamps are UTC-aware and
  distinct from `source_created_at`/`source_updated_at`.
- LangGraph state carries only canonical/generic structures.
- `(source, source_job_id)` is SOURCE-level identity. Cross-source
  deduplication belongs to Phase 1 Step 6 — do not add it to `upsert_jobs`.

## Conventions

- Python 3.11+; type hints everywhere; Pydantic v2 style models.
- Logging via stdlib; contextual `key=value` fragments; NEVER log secrets or credentials.
- Config only through `app/config/settings.py` + `.env` (see `.env.example`). No hardcoded secrets. `.env` is gitignored.
- Tests: behavior-focused, MockTransport-based, deterministic timing via injected fakes; fixtures under `tests/fixtures/greenhouse/`.
- Board tokens must match `^[A-Za-z0-9_-]{1,64}$` before URL construction
  (Greenhouse board tokens and Lever site names alike).

## Definition of done (per step)

ruff clean · pytest green (skips explicitly reported) · imports verified ·
FastAPI boots · Alembic migration applied · report lists created/modified
files, dependencies, test outcomes, deviations.
