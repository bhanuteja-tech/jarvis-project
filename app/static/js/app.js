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
  refreshWorkspace();
  refreshChrome();
});

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

  if (mapped.token) {
    appendTokenToLiveBubble(mapped.token);
    return;
  }

  if (mapped.assistantMessage) {
    hideTyping(els.messages);
    renderMessage(els.messages, "jarvis", mapped.assistantMessage.text);

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