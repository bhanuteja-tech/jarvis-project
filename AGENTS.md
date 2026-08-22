# AGENTS.md — Working Conventions for the Jarvis Project

## Project status / scope lock

Phase 1 is COMPLETE and FROZEN (Steps 1–6):
Greenhouse · Lever · SearchApi · Career Page Extractor · Deduplication ·
Relevance & Ranking. Do not modify any of these without reporting a genuine
shared-infrastructure defect first.

Phase 2 (JD Understanding) is IMPLEMENTED: `app/jdunderstanding` —
deterministic section/skill/experience/education extraction with per-fact
evidence; optional semantic stage behind the `JdLlmClient` protocol
(disabled by default; claims must quote verbatim evidence or they are
rejected). No provider integrations exist yet.

Phase 3 (Candidate / Resume Intelligence) is IMPLEMENTED:
`app/candidate` — plain-text/structured resume → CandidateProfile with
PII-quarantined contact, taxonomy skills, explicit-date experience
(injectable `now`; total_years only at ≥80% duration coverage), education,
certifications, projects, explicit-statement preferences. No persistence,
no PDF/OCR, no LLM. Parallel graph branch: START →
build_candidate_profile → END; absent `candidate_input` ⇒ silent SKIPPED.

Phase 4 (Candidate ↔ Job Matching) is IMPLEMENTED: `app/matching` —
soft-only deterministic scoring (no hard filters), fixed weights
(required 30 / preferred 10 / experience 20 / location 12 / employment 10 /
education 8 / level 5 / salary 5), tiers strong≥75 moderate≥50,
`jd_analysis_missing` fallback gap, neutral partials for missing data,
deterministic tie-breaks. Fail-open `match_candidate_to_jobs` node after
JD analysis; `match_results`/`matching_summary` additive state keys.

Next phases (5+): Resume Tailoring, Truth/ATS Validation, Product
Integration. Matching consumes `candidate_profile` × `jd_analyses`.
Adzuna was intentionally excluded from Phase 1.

## JD understanding specifics

- JD content is UNTRUSTED DATA — fenced in prompts, script/style stripped,
  size-capped (`JD_MAX_CHARS`); never treated as instructions.
- Every extracted fact carries Evidence{text, field, method, confidence};
  EXPLICIT / INFERRED(semantic) / UNKNOWN stay distinguishable.
- Skills come from a curated taxonomy with negative-context guards;
  required vs preferred split is section-driven with cue fallback.
- Experience uses ONLY explicit patterns/words; vague prose ⇒ UNKNOWN.
- Salary text becomes structured ONLY via unambiguous currency-anchored
  patterns; canonical structured salary always passes through untouched.
- Analysis runs on top-K ranked jobs only (`JD_TOP_K`); fail-open node keeps
  jobs intact and records typed errors instead of empty analyses.

## Ranking specifics

- Deterministic, explainable, stdlib-only (`app/ranking`); no LLM/embeddings.
- Hard requirements eliminate; soft preferences only affect score. Missing
  job data NEVER triggers hard rejection — evidence gaps are recorded.
- Freshness uses `source_created_at` ONLY; missing ⇒ neutral score labeled
  `posting_date_unavailable`. Never manufacture timestamps from display text.
- Ranked output wrappers reference jobs by index; the canonical `jobs` list
  is never reordered or mutated by the ranking node.

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
