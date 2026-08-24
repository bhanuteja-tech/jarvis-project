# Phase 10 — LLM Provider Architecture & Ollama Deployment

The Jarvis assistant surface supports **Ollama**, **OpenAI**, and
**OpenRouter** behind one provider-agnostic client. The deterministic system
is the default and remains fully functional with `JARVIS_ASSISTANT_LLM_ENABLED=false`
(zero network calls to any provider).

```
Browser ──HTTPS──> FastAPI ──> Jarvis orchestrator
                                   │  AssistantLlmClient (only interface)
                                   │  optional Phase 10B router (select / order / fallback)
                                   ├─ OllamaClient     → local / remote / ngrok tunnel
                                   ├─ OpenAIClient     → api.openai.com
                                   ├─ OpenRouterClient → openrouter.ai
                                   ├─ DeepSeek / Moonshot (OpenAI-compatible)
                                   └─ Gemini / Anthropic (native adapters)
```

## 1. Local Ollama setup

1. Install Ollama: <https://ollama.com/download>
2. Verify the daemon: `curl http://localhost:11434/api/tags`
3. The app default base URL is `http://localhost:11434` (used when
   `JARVIS_LLM_BASE_URL` is empty).

## 2. Model installation

```bash
ollama pull llama3.1        # or any model you prefer
ollama list                 # exact names are what JARVIS_LLM_MODEL expects
```

`GET /api/llm/status` reports `model_available` via `/api/tags`; a configured
model that is not installed yields `reachable: true, model_available: false`,
and generation raises the typed `invalid_model` error.

## 3. API endpoints used

| Call | Endpoint | Notes |
|---|---|---|
| generate | `POST /api/chat` (`stream:false`) | JSON `{message:{content}}` |
| stream | `POST /api/chat` (`stream:true`) | NDJSON deltas, only real chunks become `token` events |
| health | `GET /api/tags` | reachability + installed-model check |

## 4. Remote / ngrok architecture

```
Browser ──HTTPS──> FastAPI (Render/VM) ──HTTPS──> ngrok tunnel ──> your machine ──> Ollama
                                                        (GPU/CPU)
```

1. Run Ollama locally (`OLLAMA_HOST=127.0.0.1`).
2. Expose it: `ngrok http 11434` → note the `https://<sub>.ngrok.app` URL.
3. Configure ONLY through environment:
   ```env
   JARVIS_ASSISTANT_LLM_ENABLED=true
   JARVIS_LLM_PROVIDER=ollama
   JARVIS_LLM_BASE_URL=https://<your-sub>.ngrok.app
   JARVIS_LLM_MODEL=llama3.1
   OLLAMA_API_KEY=<tunnel token if protected>
   ```
   The ngrok URL is never hardcoded in code.

## 5. Security considerations (read before exposing anything publicly)

* **Public ngrok exposure of Ollama is NOT automatically safe.** Protect it:
  * enable an authenticated tunnel / forward-auth and set `OLLAMA_API_KEY`
    (sent as `Authorization: Bearer …`);
  * restrict by IP allow-lists where possible;
  * keep Ollama bound to localhost on the host; expose ONLY the tunnel.
* Only the two inference endpoints are ever called by this app
  (`/api/chat`, `/api/tags`) — no administrative surface needed.
* Timeouts + token caps are enforced server-side
  (`JARVIS_LLM_TIMEOUT_SECONDS`, `JARVIS_LLM_MAX_TOKENS`).
* Keys live exclusively in server environment variables. They never reach
  REST responses, WS events, logs, snapshots, or the browser. There is no
  frontend key input by design.
* LLM prompts receive only verified facts JSON (narrator) or the user's own
  message (intent) — never GraphState, resume text, or credentials.

## 6–8. Configuration reference

See `.env.example`. Behaviour summary:

| Flag | Effect |
|---|---|
| `JARVIS_ASSISTANT_LLM_ENABLED=false` | deterministic intent + narrator, no provider I/O |
| enabled + unreachable provider | typed errors internally; deterministic fallback keeps UX intact |
| `JARVIS_LLM_STREAMING=true` | genuine provider deltas emitted as `token` events |

Failure semantics: any provider failure during narration/intent refinement
falls back to the deterministic path — the user always receives a valid
response; outages never fail runs.

## 9. Production deployment & migration

Moving from ngrok to a cloud VM / private-network GPU box / managed
inference service requires ONLY a `JARVIS_LLM_BASE_URL` change (plus
credentials if the new hop authenticates). No application code changes.

Checklist: HTTPS everywhere · bearer protection on the tunnel · timeouts ≤
60 s for interactive use · monitor `rate_limited` codes on metered vendors ·
keep `JARVIS_LLM_TEMPERATURE` low (≤0.3) for narration stability.

## 10. Troubleshooting

| Symptom | Cause |
|---|---|
| status `enabled:false` | master flag off, unknown provider, or missing vendor key |
| `reachable:false` | wrong `JARVIS_LLM_BASE_URL`, daemon down, tunnel closed |
| `model_available:false` | model not pulled on that server / name mismatch |
| `authentication_failed` | bad/absent bearer for a protected endpoint |
| No `token` events | streaming disabled or provider lacks delta support |

## 11. Phase 10B — intelligent model routing

Routing sits **on top of** the Phase 10A adapters. It never duplicates HTTP,
never invents completions, and never replaces the deterministic grammar /
narrator. Default is **off** (`JARVIS_LLM_ROUTING_ENABLED=false`): the factory
still returns the single `JARVIS_LLM_PROVIDER` client exactly as in 10A.

### Architecture

- `app/llm/catalog.py` — who is configured, model id, capability flags derived
  from the actual adapters (not vendor marketing).
- `app/llm/router.py` — `RouteRequest` → `RouteDecision` (provider, model,
  reason, fallback_chain). `decide()` is configuration-only: **zero network**.
- `RoutingAssistantClient` — implements the same generate/stream/health
  protocol. On a typed `LLMProviderError` it walks `fallback_chain`.
  `asyncio.CancelledError` is never turned into a fallback.
- Orchestrator binds task names (`intent`, `narration`) so future policy can
  differ per call without changing event envelopes.

### Provider selection

1. Drop any provider that is **not configured** (cloud: empty API key;
   Ollama: not named in provider / routing default / fallback, and no
   `OLLAMA_API_KEY`). Unknown names are never routed.
2. Drop providers missing required capabilities (task, streaming flag,
   native structured output, `privacy=local`).
3. **Explicit** `preferred_provider` on the request wins if that provider is
   still in the pool (even when cost/latency prefer someone cheaper).
4. Otherwise, `lowest` cost/latency reorders the pool using **config tiers**
   (not invoices). `balanced` / `ignore` pin
   `JARVIS_LLM_ROUTING_DEFAULT` or `JARVIS_LLM_PROVIDER`, then the
   fallback list, then a stable remainder.

### Capabilities (from Phase 10A adapters)

| Provider | streaming | native `json_mode` | other |
|---|---|---|---|
| ollama | yes (NDJSON `/api/chat`) | no (flag ignored on the wire) | local/private |
| openai / openrouter / deepseek / moonshot | yes (SSE) | yes (`response_format=json_object`) | deepseek: reasoning family; moonshot: long context |
| gemini | yes (`streamGenerateContent`) | no | long context |
| anthropic | yes (SSE content_block_delta) | no | reasoning family |

Intent and narration still send `json_mode=True` and parse JSON from text
(`parse_intent_json`). Native structured output is a **hard** filter only for
task `structured_json`.

### Fallback

- After a provider error on `generate`, the next name in `fallback_chain` is
  tried. If every name fails, `ProviderUnavailableError` is raised and the
  orchestrator keeps the **deterministic** intent/narration (unchanged 10A
  contract).
- Streaming fallback is allowed **only before the first real delta**. A
  partial stream is not continued on another vendor (that would mix or
  fabricate tokens). Deltas are forwarded verbatim.
- Health is **not** used to discover vendors. `/api/llm/status` probes only
  the selected primary client, bounded by `JARVIS_LLM_HEALTH_TIMEOUT_SECONDS`.

### Configuration

See `.env.example`. Conservative defaults: routing off, cost/latency
`balanced`, privacy `any`, empty fallback list.

### Security

Routing decisions and `/api/llm/status` may include provider names, model
ids, a reachability boolean, capability names, and `routing_enabled`. They
must never include API keys, authorization headers, prompts, or completions.
PII / resume contact still do not enter LLM prompts (facts-only narrator;
intent uses the user's chat text only).

### Deterministic fallback

`JARVIS_ASSISTANT_LLM_ENABLED=false` → disabled client, no provider I/O.
Routing on with an empty pool, a capability mismatch, or total provider
failure → same UX as 10A outages: grammar + template narrator, no fake LLM
text.

## 12. Phase 10C — production Ollama + secure ngrok

The browser never talks to Ollama. Traffic is always:

```
Browser ──> Jarvis backend ──> Phase 10B router ──> Ollama adapter
                 ──HTTPS──> ngrok / tunnel ──> Ollama host ──> local model
```

Exposing Ollama directly on the public internet **without authentication is
NOT recommended.** Prefer an authenticated ngrok (or similar) tunnel, bind
Ollama to loopback on the GPU host, and keep the bearer token only in the
Jarvis server environment.

### Local Ollama setup

1. Install Ollama and pull a model (`ollama pull llama3.1`). Confirm with
   `ollama list` and `curl http://127.0.0.1:11434/api/tags`.
2. Jarvis development config:
   ```env
   JARVIS_ASSISTANT_LLM_ENABLED=true
   JARVIS_LLM_PROVIDER=ollama
   JARVIS_LLM_BASE_URL=http://127.0.0.1:11434
   JARVIS_LLM_MODEL=llama3.1
   JARVIS_OLLAMA_REQUIRE_HTTPS=false
   ```
3. Empty `JARVIS_LLM_BASE_URL` uses `OLLAMA_BASE_URL` (default
   `http://127.0.0.1:11434`). Trailing slashes are stripped. The loopback
   default is **development only** and is never treated as a production host.

### Remote Ollama / ngrok

1. Keep Ollama on the host (`OLLAMA_HOST=127.0.0.1`).
2. Start an **HTTPS** tunnel (`ngrok http 11434`) and enable tunnel auth /
   forward-auth if available.
3. Point Jarvis at the tunnel. Do not hardcode the ngrok hostname in source:
   ```env
   JARVIS_LLM_BASE_URL=https://<secure-ngrok-domain>
   JARVIS_LLM_MODEL=llama3.1
   OLLAMA_API_KEY=<tunnel-bearer-token>
   JARVIS_OLLAMA_REQUIRE_HTTPS=true
   ```
4. `OLLAMA_AUTH_TOKEN` is used only when `OLLAMA_API_KEY` is empty.
   `JARVIS_LLM_BASE_URL` wins over `OLLAMA_BASE_URL`.

### Authentication

The Ollama adapter is the only component that reads the SecretStr token. It
sends `Authorization: Bearer …` on `/api/chat` and `/api/tags`. The token
must not appear in logs, `/api/llm/status`, WebSocket events, exception
messages, or frontend JavaScript. There is no browser key input.

### HTTPS requirements

`JARVIS_OLLAMA_REQUIRE_HTTPS=true` rejects non-loopback HTTP URLs with a
typed `configuration_error` (not retried). Loopback HTTP remains valid so
local development is not broken. Configured `https://` URLs are never
rewritten to HTTP. Invalid schemes/hosts also raise `configuration_error`.

### Health and model availability

`GET /api/tags` is the only health probe. It is bounded by
`JARVIS_LLM_HEALTH_TIMEOUT_SECONDS` and does **not** pull or install models.
Safe `status` values: `not_configured`, `configuration_error`, `unreachable`,
`authentication_failure`, `server_unavailable`, `reachable`.
`model_available` is true when the configured model (or its untagged prefix)
appears in the tags list. Health never returns provider bodies, prompts, or
completions. Application startup does not call Ollama.

### Router fallback when the tunnel is down

With routing enabled, an Ollama timeout/connect/auth/config failure walks
`JARVIS_LLM_FALLBACK_PROVIDERS` (DeepSeek, Gemini, …). If every provider
fails, Jarvis keeps the deterministic grammar and narrator. An unavailable
ngrok endpoint cannot block a request indefinitely: generate uses
`JARVIS_LLM_TIMEOUT_SECONDS` plus the existing bounded retry policy (auth
and configuration errors are not retried).

### Production security

- Browser origin checks for the WebSocket are unchanged; no permissive CORS
  was added for Ollama.
- Status metadata may include provider, model, reachability, routing flags,
  capability names, `model_available`, and `health_status` — never tokens or
  Authorization headers.

### Manual ngrok verification (not part of CI)

1. Start Ollama.
2. Confirm the model exists (`ollama list`).
3. Start the ngrok HTTPS tunnel to port 11434.
4. Set `JARVIS_LLM_BASE_URL` to the HTTPS URL.
5. Set `OLLAMA_API_KEY` if the tunnel requires a bearer token.
6. Start Jarvis (`uvicorn app.main:create_app --factory`).
7. Open `GET /api/llm/status` — `provider=ollama`, `reachable` true when the
   tunnel is up; no token in the JSON.
8. Send a real assistant chat that uses the LLM path.
9. Confirm Ollama received `/api/chat` (Ollama/ngrok logs).
10. Stop Ollama or ngrok.
11. With routing + a fallback provider configured, the next request should
    use that provider; with none, the UI stays on deterministic replies.
12. Confirm the browser network tab never shows `OLLAMA_API_KEY` or a Bearer
    token destined for Ollama (only Jarvis same-origin calls).
