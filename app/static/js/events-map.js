// Event -> UI intents. Branch-aware and order-tolerant: the server guarantees
// monotonic seq per connection; ws.js drops duplicates before this module runs.
// Unknown event types map to null (forward compatibility).

import { NODE_LABELS } from "./state.js";

// Pipeline stage each node maps to (drives the avatar).
export const AVATAR_BY_NODE = {
  fetch_sources: "searching",
  build_candidate_profile: "thinking",
  deduplicate_jobs: "thinking",
  rank_jobs: "analyzing",
  analyze_jd: "analyzing",
  match_candidate_to_jobs: "matching",
  tailor_resume: "tailoring",
  validate_resume: "validating",
};

export const HERO_BY_STATE = {
  idle: "Ready when you are",
  listening: "Listening…",
  thinking: "Understanding your request",
  searching: "Searching relevant jobs",
  analyzing: "Analyzing job requirements",
  matching: "Matching your profile",
  tailoring: "Tailoring your resume",
  validating: "Validating the result",
  speaking: "Speaking",
  success: "Done — results are ready",
  error: "Something went wrong",
};

/**
 * Map one server envelope to UI intents.
 * Returns null for frames that should not change visible state.
 */
export function mapEvent(envelope) {
  const type = envelope.type;
  const data = envelope.data || {};

  switch (type) {
    case "agent_started":
      return { avatar: "thinking", runStatus: "running", runId: envelope.run_id };

    case "agent_thinking":
      return { avatar: "thinking" };

    case "workflow_node_started":
      return {
        avatar: AVATAR_BY_NODE[data.node] || "thinking",
        nodeStarted: data.node,
        nodeLabel: data.label || NODE_LABELS[data.node] || humanize(data.node),
      };

    case "workflow_node_completed":
      return {
        avatar: AVATAR_BY_NODE[data.node] || "thinking",
        nodeCompleted: data.node,
      };

    case "tool_started":
      return { avatar: "thinking", statusText: safeLabel(data.tool) };

    case "tool_progress":
      return { statusText: safeLabel(data.tool) };

    case "tool_completed":
      if (data.tool === "set_resume") return { resumeParsed: data };
      return { statusText: safeLabel(data.tool) };

    case "token":
      // Real provider streaming only; render incrementally when present.
      return {
        token: typeof data.text === "string" ? data.text : null,
        llmProvider: typeof data.provider === "string" ? data.provider : "",
        llmModel: typeof data.model === "string" ? data.model : "",
      };

    case "llm_provider_selected":
      return {
        aiSelected: {
          provider: typeof data.provider === "string" ? data.provider : "",
          model: typeof data.model === "string" ? data.model : "",
        },
      };

    case "llm_fallback":
      return {
        aiFallback: {
          from: typeof data.from === "string" ? data.from : "",
          to: typeof data.to === "string" ? data.to : "",
          code: typeof data.code === "string" ? data.code : "provider_error",
        },
      };

    case "agent_speaking":
      return { avatar: "speaking" };

    case "assistant_message":
      return {
        avatar: null, // completion event decides the final state
        assistantMessage: {
          text: typeof data.text === "string" ? data.text : "",
          attachments: Array.isArray(data.attachments) ? data.attachments : [],
        },
      };

    case "agent_completed":
      return { runStatus: "completed", avatar: "success" };

    case "completed":
      return { runStatus: "completed", avatar: "success" };

    case "cancelled":
      return {
        runStatus: "cancelled",
        avatar: "idle",
        statusText: "Run cancelled.",
      };

    case "error":
    case "agent_error":
      return {
        avatar: "error",
        errorText:
          typeof data.message === "string" && data.message
            ? data.message
            : "An error occurred. Please try again.",
        errorCode: data.code || type,
        // A run-scoped failure resolves the active run (no stuck UI state).
        runStatus: envelope.run_id ? "error" : null,
      };

    default:
      return null; // unknown types ignored gracefully
  }
}

function safeLabel(tool) {
  if (typeof tool !== "string" || !tool) return null;
  return humanize(tool);
}

export function humanize(raw) {
  if (typeof raw !== "string") return "";
  const words = raw.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
