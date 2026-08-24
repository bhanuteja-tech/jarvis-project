// Match explanation drawer: evidence-based projection of a MatchResult dump
// (score, tier, per-component breakdown with reasons, matched/missing skills).
// Only backend-provided facts are rendered.

import { humanize } from "../events-map.js";

export function initMatchDrawer(drawer, body, closeBtn) {
  const open = (jobIndex, match) => {
    renderMatch(body, jobIndex, match);
    drawer.hidden = false;
    requestAnimationFrame(() => drawer.classList.add("is-open"));
    closeBtn.focus();
  };
  const close = () => {
    drawer.classList.remove("is-open");
    setTimeout(() => {
      drawer.hidden = true;
    }, 220);
  };

  closeBtn.addEventListener("click", close);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !drawer.hidden) close();
  });

  return { open, close };
}

function renderMatch(body, jobIndex, match) {
  body.innerHTML = "";

  // ---- hero: score + tier
  const hero = document.createElement("div");
  hero.className = "match-score-hero";
  if (match?.tier) hero.classList.add(`tier-${match.tier}`);

  const score = document.createElement("strong");
  score.style.fontSize = "34px";
  score.textContent = isFinite(match?.score) ? `${Math.round(match.score)}%` : "—";

  const badge = document.createElement("span");
  badge.className = "match-tier-badge";
  badge.textContent = typeof match?.tier === "string" ? match.tier : "scored";
  if (!match?.tier) badge.hidden = true;

  const caption = document.createElement("small");
  caption.className = "muted";
  caption.textContent = `for job #${Number(jobIndex) + 1}`;

  hero.append(score, badge, caption);
  body.appendChild(hero);

  // ---- matched / missing skills
  const matched = stringsOnly(match?.matched_skills);
  const missing = stringsOnly(match?.missing_required);

  if (matched.length || missing.length) {
    const details = document.createElement("details");
    details.className = "match-section";
    details.open = true;
    const summary = document.createElement("summary");
    summary.textContent = `Matched (${matched.length}) / missing (${missing.length})`;
    details.appendChild(summary);

    const grid = document.createElement("div");
    grid.className = "chips match-section-body";
    for (const name of matched) {
      grid.appendChild(skillChip(`✓ ${name}`, "chip--matched"));
    }
    for (const name of missing) {
      grid.appendChild(skillChip(`⚠ ${name}`, "chip--missing"));
    }
    details.appendChild(grid);
    body.appendChild(details);
  }

  // ---- breakdown by component
  const breakdown =
    match?.breakdown && typeof match.breakdown === "object" ? match.breakdown : null;
  if (breakdown) {
    const details = document.createElement("details");
    details.className = "match-section";
    details.open = true;
    const summary = document.createElement("summary");
    summary.textContent = "Score breakdown";
    details.appendChild(summary);

    const listBody = document.createElement("div");
    listBody.className = "match-section-body";

    for (const [component, result] of Object.entries(breakdown)) {
      const row = document.createElement("div");
      row.className = `component-row status-${result?.status || "unknown"}`;

      const points = document.createElement("span");
      points.className = "component-points";
      const pts = Number(result?.points);
      const max = Number(result?.max);
      points.textContent =
        isFinite(pts) && isFinite(max) ? `${pts}/${max}` : "—";

      const label = document.createElement("span");
      label.className = "component-reason";
      const reasonText =
        typeof result?.reason === "string" ? result.reason : "";
      label.textContent = reasonText
        ? `${humanize(component)} — ${reasonText}`
        : humanize(component);

      row.append(points, label);
      listBody.appendChild(row);
    }
    details.appendChild(listBody);
    body.appendChild(details);
  }
}

function skillChip(text, modifier) {
  const span = document.createElement("span");
  span.className = `chip ${modifier}`;
  span.textContent = text;
  return span;
}

function stringsOnly(value) {
  return Array.isArray(value)
    ? value.filter((v) => typeof v === "string" && v.trim())
    : [];
}
