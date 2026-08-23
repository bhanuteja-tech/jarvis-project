// Application coordinator: wires WS events -> state store -> UI modules.

import { setAvatarState, avatarFromEvent } from "./avatar/avatar.js";
import { sttSupported, startListening, speak, cancelSpeak } from "./voice.js";
import { connectJarvis, sendEnvelope } from "./ws.js";
import { getState, setState, patchRun, setArtifacts, markNodeStarted, markNodeCompleted } from "./state.js";
import { mapEvent } from "./events-map.js";
import { addMessage } from "./ui/messages.js";
import { renderJobCards } from "./ui/jobs.js";
import { renderTailoredResume } from "./ui/resume.js";
import { renderValidation } from "./ui/validation.js";
import { initActivityCenter, markActivityStarted, markActivityCompleted, markActivityFailed } from "./ui/activity.js";
import { initUploadZone } from "./ui/upload.js";

const $ = (id) => document.getElementById(id);
const sessionId = crypto.randomUUID?.() || String(Date.now());
let ws = null;
let connected = false;
let lastSeqRef = {};

initActivityCenter($("node-log"));
initUploadZone($("upload-zone"), {
  onFile: (file) => sendEnvelope(ws, "resume_upload", file),
  maxChars: 30000,
});

function startSession() {
  ws = connectJarvis({
    sessionId,
    onOpen: () => { setState({ connected: true }); setAvatarState("idle"); },
    onClose: () => {
      setState({ connected: false });
      setAvatarState("idle");
      setTimeout(startSession, 2000);
    },
    onEvent: handleEvent,
  });
}

function handleEvent(envelope) {
  avatarFromEvent(envelope.type);
  const mapped = mapEvent(envelope, lastSeqRef);

  if (!mapped) return;

  if (mapped.runStatus) patchRun({ status: mapped.runStatus, runId: envelope.run_id });
  if (mapped.avatar) setAvatarState(mapped.avatar);

  if (mapped.nodeStarted) markNodeStarted(mapped.nodeStarted.node, mapped.nodeStarted.label);
  if (mapped.nodeCompleted) markNodeCompleted(mapped.nodeCompleted);

  if (mapped.resumeParsed) {
    $("resume-status").textContent =
      `✓ Resume parsed: ${mapped.resumeParsed.skills_found || 0} skills, ` +
      `${mapped.resumeParsed.experience_items || 0} experience entries.`;
    $("resume-status").className = "ok";
  }

  if (mapped.assistantMessage) {
    const msg = mapped.assistantMessage;
    addMessage($("messages"), "assistant", msg.text);

    // Populate workspace artifacts from result_snapshot.
    if (msg.resultSnapshot) {
      setArtifacts(msg.resultSnapshot);
      renderJobCards($("job-cards"), msg.resultSnapshot.jobs || [], msg.resultSnapshot.match_results || []);
      if (msg.resultSnapshot.tailored_resume) {
        renderTailoredResume($("tailored-view"), msg.resultSnapshot.tailored_resume);
      }
      if (msg.resultSnapshot.validation_report) {
        renderValidation($("validation-view"), msg.resultSnapshot.validation_report);
      }
    }

    // Speak the reply.
    speak(msg.text, { enabled: $("tts-enabled").checked });
  }

  if (mapped.errorText) {
    addMessage($("messages"), "error", mapped.errorText);
  }

  if (envelope.type === "listening_started") setAvatarState("listening");
}

// ---- Chat form -------------------------------------------------------------
$("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text) return;
  cancelSpeak();
  addMessage($("messages"), "user", text);
  session_append_user(text);
  sendEnvelope(ws, "chat", { text });
  input.value = "";
});

// ---- Voice ------------------------------------------------------------------
$("mic-btn").addEventListener("click", () => {
  if (!sttSupported()) {
    addMessage($("messages"), "error",
      "Speech recognition is not supported in this browser.");
    return;
  }
  setAvatarState("listening");
  $("mic-btn").classList.add("recording");
  startListening((transcript) => {
    $("mic-btn").classList.remove("recording");
    setAvatarState("thinking");
    addMessage($("messages"), "user", transcript);
    sendEnvelope(ws, "chat", { text: transcript });
  });
});

function cancelSpeak() {
  import("./voice.js").then((m) => m.speak("", { enabled: true }));
}

function session_append_user(text) {
  // Session store is server-side; local echo is enough for UI.
}

startSession();
