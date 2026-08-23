// Robot avatar state machine: driven exclusively by server event types.
const STATES = new Set(["idle", "listening", "thinking", "executing", "speaking", "done", "error"]);

export function setAvatarState(state) {
  const el = document.getElementById("avatar");
  const label = document.getElementById("avatar-state");
  if (!el || !STATES.has(state)) return;
  el.className = `avatar ${state}`;
  if (label) label.textContent = state;
}

export function avatarFromEvent(type) {
  switch (type) {
    case "listening_started": return setAvatarState("listening");
    case "agent_thinking":    return setAvatarState("thinking");
    case "workflow_node_completed":
    case "tool_completed":    return setAvatarState("executing");
    case "agent_speaking":
    case "token":             return setAvatarState("speaking");
    case "agent_completed":
    case "completed":         return setAvatarState("done");
    case "agent_error":
    case "error":             return setAvatarState("error");
    default:                  return undefined;
  }
}
