// Application coordinator: wires WebSocket events -> central store -> UI.
// No framework, no build step. PII never rendered: only backend-sanitized
// snapshots reach this layer, and all dynamic text uses safe DOM APIs.

import { AvatarController } from "./avatar/avatar.js";
import { sttSupported, startListening, speak, cancelSpeak } from "./voice.js";
import { connectJarvis } from "./ws.js";
import {
  getState,
  subscribe,
  setSession,
  addMessage,
  beginRun,
  markNodeStarted,
  markNodeCompleted,
  markRunFinished,
  applyArtifacts,
  extractResultSnapshot,
  setUpload,
  setAvatarState,
  setVoice,
  setLlm,
} from "./state.js";
import { mapEvent, HERO_BY_STATE } from "./events-map.js";
import { addMessage as renderMessage, showTyping, hideTyping } from "./ui/messages.js";
import { renderJobCards } from "./ui/jobs.js";
import { initMatchDrawer } from "./ui/match.js";
import { renderTailoredResume } from "./ui/resume.js";
import { renderValidation } from "./ui/validation.js";
import { renderActivity, currentStepSummary } from "./ui/activity.js";
import { initUploadZone, renderResumeStats } from "./ui/upload.js";

const $ = (id) => document.getElementById(id);

// ---- element references ------------------------------------------------------
const els = {
  systemState: $("system-state"),
  connPill: $("conn-pill"),
  connLabel: $("conn-label"),
  ttsToggle: $("tts-enabled"),
  avatarStage: $("avatar-stage"),
  stateChip: $("state-chip"),
  voiceTranscript: $("voice-transcript"),
  messages: $("messages"),
  chatForm: $("chat-form"),
  chatInput: $("chat-input"),
  micBtn: $("mic-btn"),
  activityList: $("activity-list"),
  jobEmpty: $("job-empty"),
  jobCards: $("job-cards"),
  jobsHead: $("jobs-head"),
  jobsCount: $("jobs-count"),
  uploadZone: $("upload-zone"),
  resumeStats: $("resume-stats"),
  tailoredView: $("tailored-view"),
  validationView: $("validation-view"),
  matchDrawer: $("match-drawer"),
  matchBody: $("match-body"),
  matchClose: $("match-close"),
  liveStep: $("live-step"),
  liveStepLabel: $("live-step-label"),
  cancelBtn: $("cancel-btn"),
  stopSpeakBtn: $("stop-speak"),
};

for (const [name, el] of Object.entries(els)) {
  if (!el) console.error(`[jarvis] missing #${name.replace(/([A-Z])/g, "-$1").toLowerCase()} anchor`);
}

// ---- module instances ----------------------------------------------------------
const avatar = new AvatarController(els.avatarStage);
function setAvatar(next) {
  if (avatar.setState(next)) setAvatarState(avatar.state);
}
const matchDrawer = initMatchDrawer(els.matchDrawer, els.matchBody, els.matchClose);
const uploader = initUploadZone(els.uploadZone, {
  maxBytes: 10 * 1024 * 1024, // mirrors server default max_resume_upload_bytes
  // The backend genuinely parses here (document extraction + ResumeAnalyzer
  // run server-side); the avatar reflects that real in-flight operation.
  onFile: (file) => {
    setAvatar("analyzing");
    send("resume_upload", file);
  },
  store: { setUpload },
});

const sessionId =
  crypto.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
setSession({ id: sessionId });

// ---- workspace tabs ---------------------------------------------------------------
const tabButtons = Array.from(document.querySelectorAll(".tab[data-tab]"));
for (const btn of tabButtons) {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
}
function activateTab(name) {
  for (const btn of tabButtons) {
    const isActive = btn.dataset.tab === name;
    btn.classList.toggle("is-active", isActive);
    btn.setAttribute("aria-selected", String(isActive));
    const panel = $(`tab-${btn.dataset.tab}`);
    if (panel) panel.hidden = !isActive;
  }
}

// ---- rendering helpers ---------------------------------------------------------------
function refreshWorkspace() {
  const state = getState();
  renderActivity(els.activityList, state.activity);

  const hasJobs = state.artifacts.jobs.length > 0;
  els.jobEmpty.hidden = hasJobs;
  els.jobsHead.hidden = !hasJobs;
  if (hasJobs) {
    const matchCount = state.artifacts.matchResults.length;
    els.jobsCount.textContent = matchCount
      ? `${state.artifacts.jobs.length} opportunities · ${matchCount} scored against your profile`
      : `${state.artifacts.jobs.length} opportunities`;
    renderJobCards(els.jobCards, state.artifacts.jobs, state.artifacts.matchResults, {
      onViewMatch: (index, match) => matchDrawer.open(index, match),
      onTailor: (index) => submitUserText(`tailor job ${index + 1}`),
    });
  } else {
    els.jobCards.innerHTML = "";
  }

  if (state.artifacts.tailoredResume) {
    renderTailoredResume(els.tailoredView, state.artifacts.tailoredResume);
  }
  if (state.artifacts.validationReport) {
    renderValidation(els.validationView, state.artifacts.validationReport);
  }
}

function refreshChrome() {
  const state = getState();
  // topbar pill
  const pillMap = {
    idle: ["IDLE", "pill-idle"],
    running: ["WORKING", "pill-run"],
    completed: ["DONE", "pill-ok"],
    cancelled: ["CANCELLED", "pill-warn"],
    error: ["ERROR", "pill-err"],
  };
  const [label, cls] = pillMap[state.run.status] || pillMap.idle;
  els.systemState.textContent =
    state.run.status === "running" && state.run.stage
      ? `● ${state.run.stage}`
      : state.run.status === "completed"
        ? "✓ COMPLETE"
        : label;
  els.systemState.className = `pill ${cls}`;

  // hero copy follows the avatar state
  const heroState = state.avatar.state;
  els.stateChip.dataset.state = heroState;
  els.stateChip.textContent = HERO_BY_STATE[heroState] || "Ready when you are";

  document.body.classList.toggle("run-active", state.run.status === "running");

  // live strip + cancel control exist only while a run is active
  const running = state.run.status === "running";
  els.liveStep.hidden = !running;
  if (running) {
    const summary = currentStepSummary(state.activity);
    els.liveStepLabel.textContent = summary || "Preparing…";
    els.cancelBtn.hidden = false;
  } else {
    els.cancelBtn.hidden = true;
  }

  // collapsed activity summary mirrors the live step
  const activitySummary = currentStepSummary(state.activity);
  const activityToggle = document.querySelector("#tab-activity .activity-collapse > summary");
  if (activityToggle) {
    activityToggle.dataset.summary = activitySummary || "";
  }

  // working shimmer on both panels
  for (const panel of [els.messages.closest(".chat-panel"), els.jobCards.closest(".workspace-panel")]) {
    panel?.classList.toggle("is-working", running);
  }

  // stop-speaking control reflects real utterance lifecycle
  els.stopSpeakBtn.hidden = !state.voice.speaking;

  // voice transcript line
  if (state.voice.listening && state.voice.transcript) {
    els.voiceTranscript.hidden = false;
    els.voiceTranscript.textContent = `\u201c${state.voice.transcript}\u201d`;
  } else {
    els.voiceTranscript.hidden = true;
  }
}

subscribe(() => {
  syncMessages();
  refreshWorkspace();
  refreshChrome();
});

// Project store.messages -> DOM exactly once each (user/status/error bubbles
// included; assistant replies are appended by their own event path).
let renderedCount = 0;
function syncMessages() {
  const { messages } = getState();
  if (messages.length === renderedCount) return;
  const fresh = messages.slice(renderedCount);
  renderedCount = messages.length;
  for (const msg of fresh) {
    renderMessage(els.messages, msg.role === "jarvis" ? "jarvis" : msg.role, msg.text);
  }
}

// ---- websocket lifecycle ------------------------------------------------------------
let everConnected = false;

function onConnectionChange(isOnline) {
  setSession({ connected: isOnline });
  els.connPill.classList.toggle("is-online", isOnline);
  els.connPill.classList.toggle("is-offline", !isOnline);
  els.connLabel.textContent = isOnline ? "ONLINE" : "RECONNECTING…";

  if (!isOnline) {
    if (getState().run.status === "running") {
      addMessage("status", "Connection lost — reconnecting…");
    }
  } else if (everConnected) {
    addMessage("status", "Reconnected.");
  } else {
    everConnected = true;
  }
}

const transport = connectJarvis({
  sessionId,
  onEvent: handleEvent,
  onConnectionChange,
});

// ---- outbound paths ---------------------------------------------------------------
function send(type, data = {}) {
  return transport.send(type, data);
}

function submitUserText(text) {
  cancelSpeak();
  stopListening();
  addMessage("user", text);
  send("chat", { text });
}

// cancel the active run (server emits cancelled; UI also marks locally)
els.cancelBtn.addEventListener("click", () => {
  send("cancel");
});

// live step strip opens the activity timeline
els.liveStep.addEventListener("click", () => activateTab("activity"));

// stop a spoken reply mid-utterance
els.stopSpeakBtn.addEventListener("click", () => {
  cancelSpeak();
  setVoice({ speaking: false });
});

// close the grammar popover when a command example is clicked
for (const codeEl of document.querySelectorAll("#help-menu code")) {
  codeEl.addEventListener("click", () => {
    document.getElementById("help-menu")?.removeAttribute("open");
    els.chatInput.value = codeEl.textContent || "";
    els.chatInput.focus();
  });
}

// ---- AI engine status card (safe /api/llm/* metadata only) ------------
const aiEngine = document.getElementById("ai-engine");
const aiBody = document.getElementById("ai-engine-body");
const aiTestBtn = document.getElementById("ai-test-btn");
const aiModelsBtn = document.getElementById("ai-models-btn");
const aiDrawer = document.getElementById("ai-drawer");
const aiClose = document.getElementById("ai-close");
const aiActive = document.getElementById("ai-active");
const aiRouting = document.getElementById("ai-routing-enabled");
const aiPreferred = document.getElementById("ai-preferred-select");
const aiFallbackSel = document.getElementById("ai-fallback-select");
const aiFallbackAdd = document.getElementById("ai-fallback-add");
const aiFallbackList = document.getElementById("ai-fallback-list");
const aiHealthList = document.getElementById("ai-provider-health");
const aiSaveBtn = document.getElementById("ai-save-prefs");
const aiTestBtn2 = document.getElementById("ai-test-btn2");

function renderEngineStatus(status) {
  setLlm({
    enabled: !!status.enabled,
    reachable: !!status.reachable,
    provider: status.provider || "",
    model: status.model || "",
    routingEnabled: !!status.routing_enabled,
    configuredProviders: Array.isArray(status.configured_providers)
      ? status.configured_providers
      : [],
    capabilities: Array.isArray(status.capabilities) ? status.capabilities : [],
    modelAvailable: !!status.model_available,
    healthStatus: status.health_status || "",
    preferredProvider: status.preferred_provider || "",
    fallbackProviders: Array.isArray(status.fallback_providers)
      ? status.fallback_providers
      : [],
  });

  const connected = !!status.enabled && status.reachable === true;
  if (aiEngine) {
    aiEngine.classList.toggle("is-connected", connected);
    aiEngine.classList.toggle(
      "is-unreachable",
      !!status.enabled && !connected
    );
  }
  const modeBadge = status.routing_enabled
    ? '<span class="mode-badge on">Intelligent Routing</span>'
    : status.enabled
      ? '<span class="mode-badge on">Direct</span>'
      : '<span class="mode-badge">Deterministic</span>';
  const latency =
    status.health_status === "reachable" ? "Online" : connected ? "Degraded" : "Offline";
  aiBody.innerHTML = "";
  for (const [k, v, isHtml] of [
    ["Status", connected ? "● ONLINE" : status.enabled ? "● UNAVAILABLE" : "○ LLM unavailable"],
    ["Provider", status.provider || "—", true],
    ["Model", status.model || (status.enabled ? "" : "Deterministic assistant mode"), true],
    ["Mode", modeBadge],
    ["Health", latency, true],
  ]) {
    const row = document.createElement("div");
    row.className = "ai-row";
    const key = document.createElement("span");
    key.className = "k";
    key.textContent = k;
    const val = document.createElement("span");
    val.className = "v";
    if (isHtml) val.textContent = String(v);
    else val.innerHTML = v; // our own badge markup only
    row.append(key, val);
    aiBody.appendChild(row);
  }
}

async function fetchProviders() {
  try {
    const response = await fetch("/api/llm/providers");
    const payload = await response.json();
    setLlm({ providers: Array.isArray(payload.providers) ? payload.providers : [] });
    return getState().llm.providers;
  } catch {
    return [];
  }
}

// ---- AI drawer -----------------------------------------------------------
let drawerDraftPreferred = "";
let drawerDraftFallbacks = [];

function openAiDrawer() {
  const llm = getState().llm;
  drawerDraftPreferred = llm.preferredProvider;
  drawerDraftFallbacks = [...llm.fallbackProviders];
  void fetchProviders().then(() => renderAiDrawer());
  renderAiDrawer();
  aiDrawer.hidden = false;
  requestAnimationFrame(() => aiDrawer.classList.add("is-open"));
  aiClose.focus();
}

function closeAiDrawer() {
  aiDrawer.classList.remove("is-open");
  setTimeout(() => {
    aiDrawer.hidden = true;
  }, 220);
}

function renderAiDrawer() {
  const llm = getState().llm;

  // Active block
  aiActive.innerHTML = "";
  for (const [k, v] of [
    ["Provider", llm.activeRequestProvider || llm.provider || "—"],
    ["Model", llm.activeRequestModel || llm.model || "—"],
  ]) {
    const row = document.createElement("div");
    row.className = "ai-row";
    const key = document.createElement("span");
    key.className = "k";
    key.textContent = k;
    const val = document.createElement("span");
    val.className = "v";
    val.textContent = v;
    row.append(key, val);
    aiActive.appendChild(row);
  }
  aiRouting.checked = llm.routingEnabled;

  // Preferred select: only CONFIGURED providers (+ auto).
  aiPreferred.innerHTML = "";
  const auto = document.createElement("option");
  auto.value = "";
  auto.textContent = "Auto (routing decides)";
  aiPreferred.appendChild(auto);
  for (const p of llm.providers.filter((entry) => entry.configured)) {
    const opt = document.createElement("option");
    opt.value = p.name;
    opt.textContent = `${p.name} · ${p.model || "default"}`;
    if (p.name === drawerDraftPreferred) opt.selected = true;
    aiPreferred.appendChild(opt);
  }

  // Fallback select excludes preferred + existing chain.
  aiFallbackSel.innerHTML = '<option value="">Add provider…</option>';
  for (const p of llm.providers.filter(
    (entry) =>
      entry.configured &&
      entry.name !== drawerDraftPreferred &&
      !drawerDraftFallbacks.includes(entry.name)
  )) {
    const opt = document.createElement("option");
    opt.value = p.name;
    opt.textContent = p.name;
    aiFallbackSel.appendChild(opt);
  }

  // Fallback chain list with remove buttons.
  aiFallbackList.innerHTML = "";
  drawerDraftFallbacks.forEach((name, index) => {
    const li = document.createElement("li");
    li.className = "fallback-item";
    const num = document.createElement("span");
    num.className = "fallback-num";
    num.textContent = `${index + 1}.`;
    const nameSpan = document.createElement("span");
    nameSpan.textContent = name;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "icon-btn";
    remove.setAttribute("aria-label", `Remove ${name} from fallback chain`);
    remove.textContent = "✕";
    remove.addEventListener("click", () => {
      drawerDraftFallbacks.splice(index, 1);
      renderAiDrawer();
    });
    li.append(num, nameSpan, remove);
    aiFallbackList.appendChild(li);
  });
  if (!drawerDraftFallbacks.length) {
    const li = document.createElement("li");
    li.className = "fallback-empty muted";
    li.textContent = "No manual fallbacks — routing uses its default order.";
    aiFallbackList.appendChild(li);
  }

  // Provider health grid.
  aiHealthList.innerHTML = "";
  for (const p of llm.providers) {
    const li = document.createElement("li");
    li.className = "provider-health-row";
    const dot = document.createElement("span");
    dot.className = "conn-dot " + (
      p.reachable === true ? "is-online" :
      p.reachable === false ? "is-offline" : ""
    );
    dot.style.position = "static";
    const nameEl = document.createElement("strong");
    nameEl.textContent = p.name;
    const state = document.createElement("small");
    state.className = "muted";
    state.textContent = !p.configured
      ? "not configured"
      : p.name === (llm.activeRequestProvider || llm.provider)
        ? p.health_status || (p.reachable ? "online" : "unavailable")
        : "configured";
    li.append(dot, nameEl, state);
    if (p.model) {
      const model = document.createElement("small");
      model.className = "provider-model";
      model.textContent = p.model + (p.model_available ? " ● available" : "");
      li.appendChild(model);
    }
    aiHealthList.appendChild(li);
  }
  refreshChrome();
}

aiModelsBtn?.addEventListener("click", openAiDrawer);
aiClose?.addEventListener("click", closeAiDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && aiDrawer && !aiDrawer.hidden) closeAiDrawer();
});
aiPreferred?.addEventListener("change", () => {
  drawerDraftPreferred = aiPreferred.value;
  renderAiDrawer();
});
aiFallbackAdd?.addEventListener("click", () => {
  if (!aiFallbackSel.value) return;
  drawerDraftFallbacks.push(aiFallbackSel.value);
  renderAiDrawer();
});
aiRouting?.addEventListener("change", () => {
  setLlm({ routingEnabled: aiRouting.checked });
});

aiSaveBtn?.addEventListener("click", async () => {
  aiSaveBtn.disabled = true;
  setAvatar("thinking");
  try {
    const sessionId = getState().session.id || "";
    const response = await fetch(
      `/api/llm/preferences?session_id=${encodeURIComponent(sessionId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          routing_enabled: aiRouting.checked,
          preferred_provider: drawerDraftPreferred,
          fallback_providers: drawerDraftFallbacks,
        }),
      }
    );
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      addMessage(
        "error",
        detail?.detail?.message || "Preferences were rejected by the server."
      );
    } else {
      const saved = await response.json();
      setLlm({
        preferredProvider: saved.preferred_provider,
        fallbackProviders: saved.fallback_providers,
        routingEnabled: saved.routing_enabled,
      });
      addMessage("status", "AI engine preferences saved for this session.");
      closeAiDrawer();
    }
  } catch {
    addMessage("error", "Could not save AI engine preferences.");
  } finally {
    aiSaveBtn.disabled = false;
    setAvatar("idle");
  }
});

async function refreshEngineStatus() {
  setAvatar("thinking");
  try {
    const response = await fetch("/api/llm/status");
    renderEngineStatus(await response.json());
  } catch {
    renderEngineStatus({ enabled: false, reachable: false });
  }
  setAvatar("idle");
}

aiEngine?.addEventListener("toggle", () => {
  if (aiEngine.open) void refreshEngineStatus();
});

// Both Test buttons share one flow: /api/llm/test + status refresh.
for (const btn of [aiTestBtn, aiTestBtn2]) {
  btn?.addEventListener("click", async () => {
    cancelSpeak();
    stopListening();
    btn.disabled = true;
    setAvatar("thinking");
    try {
      const response = await fetch("/api/llm/test", { method: "POST" });
      const payload = await response.json();
      renderEngineStatus(payload);
      addMessage(
        "status",
        payload.reachable
          ? `✓ ${payload.provider || "provider"} reachable`
          : "✕ AI engine unavailable"
      );
    } catch {
      addMessage("error", "Could not reach the AI engine endpoint.");
    } finally {
      btn.disabled = false;
      setAvatar("idle");
    }
  });
}

els.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = els.chatInput.value.trim();
  if (!text) return;
  els.chatInput.value = "";
  submitUserText(text);
  els.chatInput.focus();
});

// ---- voice ---------------------------------------------------------------------------
let listening = null;

els.micBtn.addEventListener("click", () => {
  if (listening) {
    stopListening();
    return;
  }
  if (!sttSupported()) {
    addMessage("error", "Speech recognition is not supported in this browser.");
    return;
  }
  cancelSpeak();
  listening = startListening({
    onStart: () => {
      setVoice({ listening: true, transcript: "" });
      els.micBtn.classList.add("is-recording");
      els.micBtn.setAttribute("aria-pressed", "true");
      setAvatar("listening");
    },
    onInterim: (transcript) => setVoice({ transcript }),
    onEnd: () => {
      setVoice({ listening: false });
      els.micBtn.classList.remove("is-recording");
      els.micBtn.setAttribute("aria-pressed", "false");
    },
    onFinal: (transcript) => {
      if (transcript) submitUserText(transcript);
    },
  });
});

function stopListening() {
  listening?.stop();
  listening = null;
  setVoice({ listening: false, transcript: "" });
  els.micBtn.classList.remove("is-recording");
  els.micBtn.setAttribute("aria-pressed", "false");
}

// ---- inbound event handling --------------------------------------------------------------
function handleEvent(envelope) {
  const mapped = mapEvent(envelope);
  if (!mapped) return;

  const state = getState();

  if (mapped.runStatus === "running" && envelope.run_id) {
    const replaced = beginRun(envelope.run_id);
    if (replaced) {
      addMessage("status", "New request received — previous run replaced.");
    }
    activateTab("activity");
    showTyping(els.messages);
    setAvatar(mapped.avatar || "thinking");
    return;
  }

  if (mapped.nodeStarted) {
    markNodeStarted(mapped.nodeStarted);
    if (mapped.avatar) setAvatar(mapped.avatar);
    return;
  }

  if (mapped.nodeCompleted) {
    markNodeCompleted(mapped.nodeCompleted);
    if (mapped.avatar) setAvatar(mapped.avatar);
    return;
  }

  if (mapped.resumeParsed) {
    uploader.markDone();
    renderResumeStats(els.resumeStats, mapped.resumeParsed);
    setAvatar("success");
    addMessage(
      "status",
      `Resume analyzed — ${mapped.resumeParsed.skills_found ?? 0} skills, ` +
        `${mapped.resumeParsed.experience_items ?? 0} experience entries detected.`
    );
    return;
  }

  if (mapped.aiSelected) {
    // Real routing visibility from the backend (never fabricated client-side).
    setLlm({
      activeRequestProvider: mapped.aiSelected.provider,
      activeRequestModel: mapped.aiSelected.model,
      streaming: false,
      tokensStreamed: 0,
    });
    markNodeStarted("llm_router");
    markNodeCompleted("llm_router");
    markNodeStarted(
      "llm_provider",
      `Provider: ${mapped.aiSelected.provider || "auto"}` +
        (mapped.aiSelected.model ? ` · ${mapped.aiSelected.model}` : "")
    );
    markNodeCompleted("llm_provider");
    return;
  }

  if (mapped.aiFallback) {
    const { from, to, code } = mapped.aiFallback;
    addMessage(
      "status",
      `${from || "provider"} unavailable — falling back to ${to || "next provider"}`
    );
    if (!to) {
      markRunFinished("error");
    }
    return;
  }

  if (mapped.token) {
    const state = getState();
    setLlm({
      streaming: true,
      tokensStreamed: state.llm.tokensStreamed + 1,
      ...(mapped.llmProvider
        ? { activeRequestProvider: mapped.llmProvider }
        : {}),
      ...(mapped.llmModel ? { activeRequestModel: mapped.llmModel } : {}),
    });
    if (state.llm.tokensStreamed === 0) markNodeStarted("llm_stream");
    appendTokenToLiveBubble(mapped.token);
    return;
  }

  if (mapped.assistantMessage) {
    hideTyping(els.messages);
    renderMessage(els.messages, "jarvis", mapped.assistantMessage.text);

    // AI-engine completion row from REAL llm_meta attachment.
    const llmMeta = (mapped.assistantMessage.attachments || []).find(
      (a) => a && a.kind === "llm_meta"
    );
    if (llmMeta) {
      markNodeCompleted("llm_stream");
      const bits = [llmMeta.provider || getState().llm.activeRequestProvider];
      if (Number.isFinite(llmMeta.tokens)) bits.push(`${llmMeta.tokens} tokens`);
      if (Number.isFinite(llmMeta.duration_ms)) {
        bits.push(`${(llmMeta.duration_ms / 1000).toFixed(1)}s`);
      }
      for (const fb of llmMeta.fallbacks || []) {
        addMessage("status", `${fb.from} unavailable → ${fb.to || "fallback"} (${fb.code})`);
      }
      markNodeStarted("llm_complete", `Complete — ${bits.filter(Boolean).join(" · ")}`);
      markNodeCompleted("llm_complete");
      setLlm({ streaming: false });
    }

    const snapshot = extractResultSnapshot({
      result_snapshot: envelope.data?.result_snapshot,
      attachments: mapped.assistantMessage.attachments,
    });
    if (snapshot) {
      applyArtifacts(snapshot);
      if (snapshot.jobs?.length) activateTab("jobs");
      else if (snapshot.tailored_resume) activateTab("resume");
      else if (snapshot.validation_report) activateTab("validation");
      attachResultActions(snapshot);
    }

    const enabled = els.ttsToggle.checked;
    speak(mapped.assistantMessage.text, {
      enabled,
      onStart: () => {
        setVoice({ speaking: true });
        setAvatar("speaking");
      },
      onEnd: () => setVoice({ speaking: false }),
    });
    if (!enabled) setAvatar("success");
    return;
  }

  if (mapped.runStatus === "completed") {
    hideTyping(els.messages);
    markRunFinished("completed");
    setAvatar("success");
    return;
  }

  if (mapped.runStatus === "cancelled") {
    hideTyping(els.messages);
    markRunFinished("cancelled");
    addMessage("status", mapped.statusText || "Run cancelled.");
    setAvatar("idle");
    return;
  }

  if (mapped.errorText) {
    hideTyping(els.messages);
    const isUploadError = [
      "unsupported_format", "file_too_large", "empty_file",
      "no_extractable_text", "invalid_document", "invalid_resume",
      "max_chars_violation",
    ].includes(mapped.errorCode);
    if (!isUploadError) markRunFinished("error");
    addMessage("error", mapped.errorText);
    setAvatar(isUploadError ? "idle" : "error");
    if (isUploadError) {
      uploader.markError(mapped.errorCode);
    }
    return;
  }

  // Non-run errors (e.g. upload failures) still restore the avatar.
  if (state.run.status !== "running") {
    setAvatar("idle");
  }
}

// Grounded quick actions attached to the latest assistant result message.
function attachResultActions(snapshot) {
  const actions = [];
  if (snapshot.jobs?.length) {
    actions.push({
      label: "Browse jobs",
      onClick: () => activateTab("jobs"),
    });
    const best = (snapshot.match_results || []).slice().sort(
      (a, b) => (b.score ?? 0) - (a.score ?? 0)
    )[0];
    if (best) {
      actions.push({
        label: `Why job #${best.job_index + 1}?`,
        onClick: () => matchDrawer.open(best.job_index, best),
      });
    }
  }
  if (snapshot.tailored_resume) {
    actions.push({ label: "Review resume", onClick: () => activateTab("resume") });
  }
  if (snapshot.validation_report) {
    actions.push({
      label: "Open validation report",
      onClick: () => activateTab("validation"),
    });
  }
  if (!actions.length || !els.messages.lastElementChild) return;
  const row = document.createElement("div");
  row.className = "action-row";
  for (const action of actions.slice(0, 4)) {
    const chipEl = document.createElement("button");
    chipEl.type = "button";
    chipEl.className = "action-chip";
    chipEl.textContent = action.label;
    chipEl.addEventListener("click", action.onClick);
    row.appendChild(chipEl);
  }
  els.messages.lastElementChild.appendChild(row);
}

// Real provider token streaming only; never faked by this frontend.
let liveBubble = null;
let liveText = "";
function appendTokenToLiveBubble(token) {
  if (!liveBubble || !liveBubble.isConnected) {
    liveBubble = renderMessage(els.messages, "jarvis", "");
    liveText = "";
  }
  liveText += token;
  liveBubble.textContent = liveText;
  els.messages.scrollTop = els.messages.scrollHeight;
}