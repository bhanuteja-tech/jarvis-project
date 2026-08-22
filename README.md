# Jarvis Project

Production-oriented AI Job Discovery and Resume Tailoring System.

**Current status: Phase 1, Step 1 — Greenhouse source adapter.**

## Stack

Python 3.11+ · FastAPI · LangGraph · Pydantic v2 · httpx · SQLAlchemy 2.x · PostgreSQL · pytest

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows (source .venv/bin/activate on POSIX)
pip install -e ".[dev]"

copy .env.example .env              # then edit values (never commit .env)

alembic upgrade head                # create the schema
uvicorn app.main:create_app --factory --reload
```

Health probes: `GET /healthz` (liveness), `GET /readyz` (database check).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | local dev DSN | PostgreSQL SQLAlchemy URL |
| `GREENHOUSE_TIMEOUT_SECONDS` | `30` | per-attempt read/write timeout budget |
| `GREENHOUSE_MAX_RETRIES` | `3` | retries after the first attempt (hard ceiling) |
| `GREENHOUSE_BOARD_REGISTRY_PATH` | unset | JSON file mapping board token → company name |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR/CRITICAL |

### Board registry

The Greenhouse jobs-list endpoint does not include the company name, and we
never invent it from API responses. Company identity comes from an operator-
maintained, configuration-backed registry (`greenhouse_boards.example.json`):

```json
{"examplecorp": "Example Corp"}
```

Unknown boards simply produce jobs with `company = null`. The registry is a
small Protocol (`app/sources/greenhouse/registry.py`) designed to be replaced
by persistent storage later without adapter changes.

## Testing

```bash
pytest            # no network access; HTTP via httpx.MockTransport
ruff check .
```

- **DB persistence tests** run only when PostgreSQL is reachable; otherwise
  they SKIP with an explicit reason. Target a specific DB with
  `JARVIS_TEST_DATABASE_URL`.
- **Live smoke test** (one real request, one public board) is opt-in:

```bash
set JARVIS_RUN_LIVE_SMOKE=1
pytest -m live tests/test_greenhouse_live_smoke.py
```

## Architecture boundaries

- `sources/greenhouse/client.py` — HTTP transport, timeouts, retries, JSON decoding.
- `sources/greenhouse/schemas.py` — documented upstream response models.
- `sources/greenhouse/adapter.py` — validation + normalization to canonical `Job`.
- `sources/resilience.py` — shared retry/backoff engine (all future sources).
- `graph/workflow.py` — minimal LangGraph foundation; adapters are injected.
- `db/` — SQLAlchemy persistence; `upsert_jobs` is source-level identity only.

Canonical flow: `Greenhouse API → raw schema → validate → normalize → Job → upsert`.

## Roadmap

Phase 1 remaining: Lever → Adzuna → SearchApi → career-page extractor → dedup.
Later phases: JD/candidate intelligence, matching, tailoring, truth/ATS
validation, product integration.
