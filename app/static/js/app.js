// Jarvis SPA: chat, avatar state machine, resume upload, voice, results view.
import { setAvatarState, avatarFromEvent } from "./avatar.js";
import { sttSupported, startListening, speak } from "./voice.js";
import { connectJarvis, sendEnvelope } from "./ws.js";

const $ = (id) => document.getElementById(id);
const sessionId = crypto.randomUUID?.() || String(Date.now());
let ws = null;
let connected = false;

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  $("messages").appendChild(div);
  $("messages").scrollTop = $("messages").scrollHeight;
}

function addNodeLog(nodeName) {
  const li = document.createElement("li");
  li.textContent = `✓ ${nodeName}`;
  $("node-log").appendChild(li);
}

function handleEvent(envelope) {
  avatarFromEvent(envelope.type);

  switch (envelope.type) {
    case "workflow_node_completed":
      addNodeLog(envelope.data.node);
      break;

    case "assistant_message": {
      const text = envelope.data.text || "";
      addMessage("assistant", text);
      speak(text, { enabled: $("tts-enabled").checked });
      renderAttachments(envelope.data.attachments || [], envelope);
      setAvatarState("done");
      break;
    }

    case "agent_error":
    case "error":
      addMessage("error", `${envelope.data.code || "error"}: ${envelope.data.message || ""}`);
      setAvatarState("error");
      break;

    case "listening_started":
      setAvatarState("listening");
      break;
  }
}

function renderAttachments(attachments, envelope) {
  if (!attachments.length) return;
  fetch(`/api/runs/${envelope.run_id}/result`)
    .then((r) => (r.ok ? r.json() : null))
    .then((snapshot) => {
      if (!snapshot) return;
      $("validation-view").textContent = JSON.stringify(
        {
          validation_status: snapshot.validation_status,
          tailored_target_index: snapshot.tailored_target_index,
        },
        null,
        2
      );
    })
    .catch(() => {});
  // Full structured resume lives in session.last_state via the final run;
  // a dedicated result endpoint can be added later without breaking this UI.
  void envelope;
}

function startSession() {
  ws = connectJarvis({
    sessionId,
    onOpen: () => setAvatarState("idle"),
    onClose: () => setTimeout(startSession, 2000),
    onEvent: handleEvent,
  });
}

$("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text || !connected) return;
  addMessage("user", text);
  sendEnvelope(ws, "chat", { text });
  input.value = "";
});

$("mic-btn").addEventListener("click", () => {
  if (!sttSupported()) {
    addMessage("error", "Speech recognition is not supported in this browser.");
    return;
  }
  sendEnvelope(ws, "listening_started");
  startListening((transcript) => {
    sendEnvelope(ws, "listening_stopped");
    addMessage("user", transcript);
    sendEnvelope(ws, "chat", { text: transcript });
  });
});

$("resume-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  file.text().then((content) => {
    sendEnvelope(ws, "resume_upload", { name: file.name, content });
  });
});

startSession();
