// Agent Activity Center: safe step labels only, never chain-of-thought.

import { NODE_LABELS } from "../events-map.js";

const CANONICAL = Object.keys(NODE_LABELS);

export function initActivityCenter(container) {
  container.textContent = "";
  const title = document.createElement("h4");
  title.textContent = "Agent Activity";
  const list = document.createElement("ul");
  list.className = "activity-list";
  for (const node of CANONICAL) {
    const row = document.createElement("li");
    row.dataset.node = node;
    row.className = "activity-row pending";
    const icon = document.createElement("span");
    icon.className = "activity-icon";
    icon.textContent = "○";
    const label = document.createElement("span");
    label.textContent = NODE_LABELS[node];
    row.append(icon, label);
    list.append(row);
  }
  container.append(title, list);
}

export function markActivityStarted(container, node) {
  const row = container.querySelector(`[data-node="${node}"]`);
  if (!row) return;
  row.className = "activity-row active";
  row.querySelector(".activity-icon").textContent = "◉";
}

export function markActivityCompleted(container, node) {
  const row = container.querySelector(`[data-node="${node}"]`);
  if (!row) return;
  row.className = "activity-row done";
  row.querySelector(".activity-icon").textContent = "✓";
}

export function markActivityFailed(container, node) {
  const row = container.querySelector(`[data-node="${node}"]`);
  if (!row) return;
  row.className = "activity-row failed";
  row.querySelector(".activity-icon").textContent = "✕";
}
