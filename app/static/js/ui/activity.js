// Agent activity center: safe workflow timeline with elapsed indicators.
// Labels are curated safe labels (never internal reasoning). Elapsed times
// are measured client-side between the REAL start/completion events.

import { NODE_LABELS } from "../state.js";

const ICONS = {
  pending: "○",
  active: "●",
  completed: "✓",
  failed: "✕",
  cancelled: "◌",
};

function elapsedLabel(ms) {
  if (!Number.isFinite(ms) || ms < 0) return null;
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

/** Render the current activity list from the central store. */
export function renderActivity(container, activity) {
  const entries = Array.isArray(activity) ? activity : [];
  container.innerHTML = "";

  if (!entries.length) {
    const li = document.createElement("li");
    li.className = "activity-empty muted";
    li.textContent =
      "Ask Jarvis to find roles and your live agent activity will appear here.";
    container.appendChild(li);
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const entry of entries) fragment.appendChild(row(entry));
  container.appendChild(fragment);
}

/** One-line summary for the collapsed state: the current (or last) step. */
export function currentStepSummary(activity) {
  const entries = Array.isArray(activity) ? activity : [];
  const active = entries.find((e) => e.status === "active");
  if (active) return active.label || NODE_LABELS[active.node] || active.node;
  const lastDone = [...entries].reverse().find((e) => e.status === "completed");
  if (lastDone) return `Completed: ${lastDone.label || lastDone.node}`;
  return null;
}

function row(entry) {
  const li = document.createElement("li");
  li.className = `activity-row ${entry.status}`;
  li.dataset.node = entry.node;

  const icon = document.createElement("span");
  icon.className = "activity-icon";
  icon.textContent = ICONS[entry.status] || "○";
  icon.setAttribute("aria-hidden", "true");

  const main = document.createElement("div");
  main.className = "activity-main";

  const labelSpan = document.createElement("span");
  labelSpan.className = "activity-label";
  labelSpan.textContent = entry.label || NODE_LABELS[entry.node] || entry.node;
  main.appendChild(labelSpan);

  const elapsed = elapsedLabel(entry.elapsedMs);
  if (elapsed) {
    const time = document.createElement("span");
    time.className = "activity-elapsed";
    time.textContent = elapsed;
    time.title = "Measured while this step was actively running";
    main.appendChild(time);
  }

  li.append(icon, main);
  li.setAttribute(
    "aria-label",
    `${labelSpan.textContent} — ${entry.status}${
      elapsed ? `, took ${elapsed}` : ""
    }`
  );
  return li;
}
