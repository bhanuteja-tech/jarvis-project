# Jarvis Project

Production-oriented AI Job Discovery and Resume Tailoring System.

**Current status: Phase 1 COMPLETE (Steps 1–6): Greenhouse · Lever · SearchApi ·
Career Page Extractor · Deduplication · Relevance Ranking.**

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
| `LEVER_BASE_URL` | official global API | Postings API base (EU: `https://api.eu.lever.co/v0/postings`) |
| `LEVER_TIMEOUT_SECONDS` / `LEVER_MAX_RETRIES` | `30` / `3` | same semantics as Greenhouse |
| `LEVER_PAGE_SIZE` | `50` | postings per page request (≤100) |
| `LEVER_MAX_PAGES` | `200` | hard pagination ceiling per site |
| `LEVER_SITE_REGISTRY_PATH` | unset | JSON file mapping site → company name |
| `SEARCHAPI_API_KEY` | empty | SearchApi key (`SecretStr`; Bearer header only; empty = disabled) |
| `SEARCHAPI_TIMEOUT_SECONDS` / `SEARCHAPI_MAX_RETRIES` | `30` / `2` | retries consume paid quota — keep small |
| `SEARCHAPI_MAX_PAGES` | `5` | hard pagination ceiling per engine run |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR/CRITICAL |

### Registries

Neither the Greenhouse boards endpoint nor the public Lever Postings API
provides company display names, and we never invent them from API responses.
Company identity comes from operator-maintained, configuration-backed
registries (`greenhouse_boards.example.json`, `lever_sites.example.json`):

```json
{"leverdemo": "Lever Demo Co"}
```

Unknown boards/sites produce jobs with `company = null`. Both registries are
small Protocols designed to be replaced by persistent storage later without
adapter changes.

### SearchApi specifics

Two engines under one provider, schemas deliberately separate:

- **google_jobs** (primary discovery): request params restricted to
  `{q, gl, hl, location}` + internal `next_page_token` — `time_period` is
  not documented for this engine and is never sent. Google provides no job
  id and no absolute timestamps: identity is `gj:<htidocid>` from the
  sharing_link (fallback: deterministic `derived:<uuid5>`), and
  `source_created_at` stays null — relative text ("1 day ago") is preserved
  verbatim in `extra.posted_at_display`, never converted.
- **google** (discovery candidates for the future Career Page Extractor):
  may use documented `time_period` freshness filters; paginates via numeric
  `page`; the response's `pagination.next` google.com URL is never fetched.
  Results become `SearchCandidateResult` objects — never canonical jobs.

### Lever specifics

Public Postings API only (`GET /v0/postings/{site}?mode=json`) — the
authenticated Data API (`/v1`) is deliberately unused. Offset pagination with
duplicate-ID suppression and a hard page ceiling; `createdAt` (epoch ms,
undocumented-but-observed) maps defensively to `source_created_at`; there is
no updated-at field, so `source_updated_at` stays null. Lever's free-form
`lists` are preserved verbatim in `extra` — never heuristically promoted into
requirements/responsibilities.

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

- `sources/{greenhouse,lever,searchapi}/client.py` — HTTP transport, timeouts, status classification.
- `sources/{greenhouse,lever}/*.py`, `sources/searchapi/*` — documented upstream schemas + normalization to canonical `Job` (SearchApi google engine → candidate URLs instead).
- `sources/resilience.py` — shared retry/backoff engine (all sources).
- `graph/workflow.py` — minimal LangGraph foundation; adapters are injected.
- `db/` — SQLAlchemy persistence; `upsert_jobs` is source-level identity only.

Canonical flow per source: `API → raw schema → validate → normalize → Job → upsert`.

## Roadmap

Phase 1 remaining: Adzuna → career-page extractor → dedup.
Later phases: JD/candidate intelligence, matching, tailoring, truth/ATS
validation, product integration.
