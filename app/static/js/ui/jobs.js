// Job/match cards built strictly from backend snapshot facts.

import { contentTokens } from "../tokens.js";

export function renderJobCards(container, jobs, matchResults) {
  container.textContent = "";
  const byIndex = new Map((matchResults || []).map(m => [m.job_index, m]));
  for (const job of jobs) {
    const match = byIndex.get(job.__index);
    if (!match && matchResults?.length) continue;
    container.appendChild(jobCard(job, match));
  }
}

function jobCard(job, match) {
  const card = document.createElement("div");
  card.className = "job-card";

  const header = document.createElement("div");
  header.className = "job-card__head";
  const title = document.createElement("strong");
  title.textContent = job.title || "Untitled role";
  const company = document.createElement("span");
  company.className = "muted";
  company.textContent = ` — ${job.company || "Unknown"}`;
  header.append(title, company);

  if (match) {
    header.appendChild(scoreRing(match.score, match.tier));

    if (match.missing_required?.length) {
      const missing = document.createElement("div");
      missing.className = "chips missing";
      for (const name of match.missing_required) {
        const chip = document.createElement("span");
        chip.className = "chip chip--missing";
        chip.textContent = `✕ ${name}`;
        missing.appendChild(chip);
      }
      card.appendChild(missing);
    }
  }

  const meta = document.createElement("div");
  meta.className = "muted";
  meta.textContent = [job.location, "Remote"].filter(Boolean).join(" · ");
  card.append(header, meta);
  return card;
}

function scoreRing(score, tier) {
  const wrap = document.createElement("div");
  wrap.className = `score-ring tier-${tier}`;
  const pct = Math.max(0, Math.min(100, Number(score)));
  const r = 18;
  const circumference = 2 * Math.PI * r;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 44 44");
  svg.setAttribute("width", "44"); svg.setAttribute("height", "44");

  const track = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  track.setAttribute("cx", 22); track.setAttribute("cy", 22); track.setAttribute("r", r);
  track.setAttribute("fill", "none"); track.setAttribute("stroke", "#30363d");
  track.setAttribute("stroke-width", "4");

  const arc = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  arc.setAttribute("cx", 22); arc.setAttribute("cy", 22); arc.setAttribute("r", r);
  arc.setAttribute("fill", "none");
  arc.setAttribute("stroke", tier === "strong" ? "#3fb950" : tier === "moderate" ? "#d29922" : "#8b949e");
  arc.setAttribute("stroke-width", "4");
  arc.setAttribute("stroke-linecap", "round");
  arc.setAttribute("transform", "rotate(-90 22 22)");
  arc.setAttribute("stroke-dasharray", `${(pct / 100) * circumference} ${circumference}`);

  const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
  text.setAttribute("x", 22); text.setAttribute("y", 26);
  text.setAttribute("text-anchor", "middle");
  text.setAttribute("font-size", "11");
  text.setAttribute("fill", "#e6edf3");
  text.textContent = String(Math.round(pct));

  svg.append(track, arc, text);
  wrap.appendChild(svg);
  return wrap;
}
