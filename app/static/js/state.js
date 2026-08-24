// Central UI state store — single source of truth for all components.
// The server owns business facts; this store projects only what the UI
// renders. Pure pub/sub, no framework. Components subscribe and re-render.

const ACTIVITY_ORDER = [
  "fetch_sources",
  "build_candidate_profile",
  "deduplicate_jobs",
  "rank_jobs",
  "analyze_jd",
  "match_candidate_to_jobs",
  "tailor_resume",
  "validate_resume",
];

export const NODE_LABELS = {
  fetch_sources: "Searching jobs",
  build_candidate_profile: "Understanding your profile",
  deduplicate_jobs: "Removing duplicates",
  rank_jobs: "Ranking relevant roles",
  analyze_jd: "Analyzing requirements",
  match_candidate_to_jobs: "Matching your experience",
  tailor_resume: "Tailoring your resume",
  validate_resume: "Validating the result",
  // Phase 11 AI-engine pseudo-steps (driven by real routing events only)
  llm_router: "Routing AI request",
  llm_provider: "AI provider selected",
  llm_stream: "Generating response",
  llm_complete: "Response complete",
};

// Top-bar stage pill text per active node — only real node events drive it.
export const STAGE_BY_NODE = {
  build_candidate_profile: "UNDERSTANDING REQUEST",
  fetch_sources: "SEARCHING OPPORTUNITIES",
  deduplicate_jobs: "REFINING RESULTS",
  rank_jobs: "RANKING OPPORTUNITIES",
  analyze_jd: "ANALYZING REQUIREMENTS",
  match_candidate_to_jobs: "MATCHING YOUR PROFILE",
  tailor_resume: "TAILORING RESUME",
  validate_resume: "VALIDATING RESULT",
};

const state = {
  session: { id: null, connected: false },

  messages: [], // {role: user|jarvis|status|error, text}

  run: {
    id: null,
    status: "idle", // idle|running|completed|cancelled|error
    currentNode: null,
    branch: null,
    stage: null, // top-bar pill text while running (from STAGE_BY_NODE)
    replacedCount: 0,
  },

  activity: [], // ordered [{node,label,status}] status: pending|active|completed|failed|cancelled

  artifacts: {
    jobs: [],
    matchResults: [],
    tailoredResume: null,
    validationReport: null,
  },

  avatar: { state: "idle" }, // see avatar.js STATE list

  // Phase 11: AI engine / multi-model control surface (safe metadata only).
  llm: {
    enabled: false,
    reachable: false,
    provider: "",
    model: "",
    routingEnabled: false,
    configuredProviders: [],
    capabilities: [],
    modelAvailable: false,
    healthStatus: "",
    preferredProvider: "",
    fallbackProviders: [],
    providers: [], // catalog rows from /api/llm/providers
    activeRequestProvider: "",
    activeRequestModel: "",
    streaming: false,
    tokensStreamed: 0,
  },

  voice: {
    listening: false,
    speaking: false,
    transcript: "",
    supported: typeof window !== "undefined" &&
      !!(window.SpeechRecognition || window.webkitSpeechRecognition),
  },

  upload: {
    status: "empty", // empty|reading|parsing|done|error
    filename: null,
    error: null,
    stats: null, // {skills_found, experience_items, ...} from backend only
  },
};

const subscribers = new Set();

function notify() {
  const snapshot = state;
  for (const fn of subscribers) fn(snapshot);
}

export function getState() {
  return state;
}

export function subscribe(fn) {
  subscribers.add(fn);
  return () => subscribers.delete(fn);
}

// ---- session ---------------------------------------------------------------
export function setSession(patch) {
  Object.assign(state.session, patch);
  notify();
}

// ---- messages ----------------------------------------------------------------
export function addMessage(role, text) {
  state.messages.push({ role, text });
  if (state.messages.length > 200) state.messages.shift();
  notify();
}

// ---- run + activity ----------------------------------------------------------
export function beginRun(runId) {
  const replaced = state.run.status === "running";
  if (replaced) state.run.replacedCount += 1;
  state.run.id = runId;
  state.run.status = "running";
  state.run.currentNode = null;
  state.run.stage = null;
  state.activity = ACTIVITY_ORDER.map((node) => ({
    node,
    label: NODE_LABELS[node] || node,
    status: "pending",
    startedAt: null, // client arrival time of the REAL start event
    elapsedMs: null, // measured active duration for completed steps
  }));
  notify();
  return replaced; // true when this run silently replaced an in-flight one
}

export function markNodeStarted(node, labelOverride) {
  state.run.currentNode = node;
  state.run.branch = node === "build_candidate_profile" ? "candidate" : "discovery";
  state.run.stage = STAGE_BY_NODE[node] || null;
  const entry = findActivity(node);
  if (entry) {
    entry.status = "active";
    if (labelOverride) entry.label = labelOverride;
    entry.startedAt = performance.now();
    if (entry.elapsedMs != null) entry.elapsedMs = null; // restarted
  }
  notify();
}

export function markNodeCompleted(node) {
  const entry = findActivity(node);
  if (entry && entry.status !== "failed") {
    entry.status = "completed";
    if (entry.startedAt != null) {
      entry.elapsedMs = Math.round(performance.now() - entry.startedAt);
    }
  }
  notify();
}

export function markRunFinished(status) {
  state.run.status = status;
  if (status !== "running") state.run.currentNode = null;
  if (status === "completed") state.run.stage = "COMPLETE";
  else state.run.stage = null;
  if (status === "cancelled") {
    for (const entry of state.activity) {
      if (entry.status === "pending" || entry.status === "active") {
        entry.status = "cancelled";
      }
    }
  }
  notify();
}

export function resetActivity() {
  state.activity = [];
  notify();
}

function findActivity(node) {
  return state.activity.find((a) => a.node === node) || null;
}

// ---- artifacts ------------------------------------------------------------------
// Tolerant projection of the current backend snapshot shape (F4/F5): accepts
// either data.result_snapshot or an attachment {kind:"result_snapshot"...},
// and tolerates jobs without __index by positional identity.
export function applyArtifacts(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return;
  const jobs = Array.isArray(snapshot.jobs) ? snapshot.jobs : [];
  const matchResults = Array.isArray(snapshot.match_results)
    ? snapshot.match_results
    : Array.isArray(snapshot.matchResults)
      ? snapshot.matchResults
      : [];

  state.artifacts.jobs = jobs.map((job, index) =>
    job && typeof job === "object" ? { __index: index, ...job } : job
  );
  state.artifacts.matchResults = matchResults;
  state.artifacts.tailoredResume =
    snapshot.tailored_resume ?? snapshot.tailoredResume ?? null;
  state.artifacts.validationReport =
    snapshot.validation_report ?? snapshot.validationReport ?? null;
  notify();
}

export function extractResultSnapshot(envelopeData) {
  if (!envelopeData) return null;
  if (envelopeData.result_snapshot) return envelopeData.result_snapshot;
  if (envelopeData.resultSnapshot) return envelopeData.resultSnapshot;
  const attachments = envelopeData.attachments;
  if (Array.isArray(attachments)) {
    for (const att of attachments) {
      if (att && (att.kind === "result_snapshot" || att.kind === "resultSnapshot")) {
        return att;
      }
    }
  }
  return null;
}

// ---- voice ------------------------------------------------------------------------
export function setVoice(patch) {
  Object.assign(state.voice, patch);
  notify();
}

// ---- avatar -------------------------------------------------------------------------
export function setAvatarState(next) {
  if (state.avatar.state === next) return false;
  state.avatar.state = next;
  notify();
  return true;
}

// ---- llm engine (Phase 11) ------------------------------------------------------------
export function setLlm(patch) {
  Object.assign(state.llm, patch);
  notify();
}

export function setPreferredProvider(name) {
  state.llm.preferredProvider = String(name || "");
  notify();
}

export function setFallbackProviders(list) {
  state.llm.fallbackProviders = (Array.isArray(list) ? list : []).slice(0, 6);
  notify();
}

// ---- upload --------------------------------------------------------------------------
export function setUpload(patch) {
  Object.assign(state.upload, patch);
  notify();
}
