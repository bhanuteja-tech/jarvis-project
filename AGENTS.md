# AGENTS.md — Working Conventions for the Jarvis Project

## Project status / scope lock

Phase 1, Step 1 (Greenhouse adapter) is the ONLY implemented step.

Do not implement: Lever, Adzuna, SearchApi, career-page extraction,
deduplication, embeddings/semantics, ranking, resume tailoring, ATS scoring,
auth, frontend, queues/brokers. Phase order is locked; see README roadmap.

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
- Board tokens must match `^[A-Za-z0-9_-]{1,64}$` before URL construction.

## Definition of done (per step)

ruff clean · pytest green (skips explicitly reported) · imports verified ·
FastAPI boots · Alembic migration applied · report lists created/modified
files, dependencies, test outcomes, deviations.
