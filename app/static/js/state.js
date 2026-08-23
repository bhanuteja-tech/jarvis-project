// Central UI state store. The server owns business facts; this store only
// projects what the UI renders. Pure pub/sub, no framework.

const state = {
  sessionId: null,
  connected: false,
  run: { status: "idle", runId: null, currentNode: null },
  artifacts: {
    jobs: [],
    match_results: [],
    tailored_resume: null,
    validation_report: null,
  },
  avatar: "idle",
  activity: {},          // node -> {status, label}
  messages: [],          // {role, html-safe text rendered elsewhere}
};

const subscribers = new Set();

export function getState() {
  return state;
}

export function setState(patch) {
  Object.assign(state, patch);
  notify();
}

export function patchRun(patch) {
  Object.assign(state.run, patch);
  notify();
}

export function setAvatar(avatarState) {
  if (state.avatar === avatarState) return;
  state.avatar = avatarState;
  notify();
}

export function markNodeCompleted(node) {
  const entry = state.activity[node] || { status: "pending", label: node };
  entry.status = "done";
  state.activity[node] = entry;
  notify();
}

export function markNodeStarted(node, label) {
  const existing = state.activity[node];
  if (existing && existing.status !== "pending") return;
  state.activity[node] = { status: "active", label: label || node };
  notify();
}

export function resetActivity() {
  state.activity = {};
}

export function setArtifacts(artifacts) {
  Object.assign(state.artifacts, artifacts);
  notify();
}

export function subscribe(fn) {
  subscribers.add(fn);
  return () => subscribers.delete(fn);
}

function notify() {
  for (const fn of subscribers) fn(state);
}
