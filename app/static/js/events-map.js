// Event -> UI transition map (branch-aware, order-tolerant).
// The server guarantees monotonic seq per connection; duplicates/out-of-order
// frames are dropped by ws.js before reaching this module.

export const NODE_LABELS = {
  fetch_sources: "Searching jobs",
  build_candidate_profile: "Building candidate profile",
  deduplicate_jobs: "Removing duplicate jobs",
  rank_jobs: "Ranking relevant jobs",
  analyze_jd: "Analyzing job requirements",
  match_candidate_to_jobs: "Matching candidate",
  tailor_resume: "Tailoring resume",
  validate_resume: "Validating resume",
};

export const BRANCH_OF = {
  build_candidate_profile: "candidate",
};

// Pipeline stage each node maps to (drives avatar emphasis).
export const AVATAR_BY_NODE = {
  fetch_sources: "searching",
  deduplicate_jobs: "executing",
  rank_jobs: "analyzing",
  analyze_jd: "analyzing",
  match_candidate_to_jobs: "matching",
  tailor_resume: "tailoring",
  validate_resume: "validating",
  build_candidate_profile: "thinking",
};

/**
 * Map one server envelope to UI intents.
 * Returns null for frames that should not change visible state.
 */
export function mapEvent(envelope, lastSeqRef) {
  const seq = typeof envelope.seq === "number" ? envelope.seq : 0;
  if (lastSeqRef.value !== undefined && seq <= lastSeqRef.value) {
    return null; // duplicate / out-of-order
  }
  lastSeqRef.value = seq;

  switch (envelope.type) {
    case "agent_started":
      return { avatar: "thinking", runStatus: "running", runId: envelope.run_id };
    case "agent_thinking":
      return { avatar: "thinking" };
    case "workflow_node_started":
      return {
        avatar: AVATAR_BY_NODE[envelope.data.node] || "executing",
        nodeStarted: {
          node: envelope.data.node,
          label: envelope.data.label || NODE_LABELS[envelope.data.node] || envelope.data.node,
        },
      };
    case "workflow_node_completed":
      return {
        avatar: AVATAR_BY_NODE[envelope.data.node] || "executing",
        nodeCompleted: envelope.data.node,
      };
    case "tool_completed":
      if (envelope.data.tool === "set_resume") {
        return { resumeParsed: envelope.data };
      }
      return null;
    case "agent_speaking":
      return { avatar: "speaking" };
    case "assistant_message":
      return {
        avatar: "done",
        assistantMessage: {
          text: envelope.data.text,
          attachments: envelope.data.attachments || [],
          resultSnapshot: envelope.data.result_snapshot || null,
        },
      };
    case "completed":
      return { runStatus: "completed", avatar: "idle" };
    case "cancelled":
      return { runStatus: "cancelled", avatar: "idle",
               errorText: "Run cancelled." };
    case "error":
    case "agent_error":
      return {
        avatar: "error",
        errorText: envelope.data.message || "An error occurred.",
        errorCode: envelope.data.code || envelope.type,
      };
    default:
      return null; // unknown types ignored gracefully
  }
}
