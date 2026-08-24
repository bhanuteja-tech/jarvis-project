// Premium job cards built strictly from backend snapshot facts.
// F5 tolerance: the current backend snapshot carries jobs without __index,
// so identity is positional (jobs[i] <-> job_index i, canonical order).
// Nothing is invented: fields absent from state are simply not rendered.

const TIER_COLORS = {
  strong: "#3fb950",
  moderate: "#d29922",
};

/**
 * Render all jobs. `matchResults` are MatchResult dumps with
 * {job_index, score, tier, matched_skills, missing_required, breakdown}.
 */
export function renderJobCards(container, jobs, matchResults, handlers = {}) {
  container.innerHTML = "";
  const list = Array.isArray(jobs) ? jobs : [];
  if (!list.length) return;

  const matches = Array.isArray(matchResults) ? matchResults : [];
  const byIndex = new Map();
  for (const m of matches) {
    if (m && Number.isInteger(m.job_index)) byIndex.set(m.job_index, m);
  }

  const fragment = document.createDocumentFragment();
  list.forEach((job, index) => {
    const match = byIndex.get(index) || null;
    fragment.appendChild(jobCard(job, index, match, handlers));
  });
  container.appendChild(fragment);
  animateEntrance(container);
}

// Staggered card entrance — capped so large result sets stay cheap, and
// skipped entirely under prefers-reduced-motion.
function animateEntrance(container) {
  const reduced =
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  if (reduced) return;
  const cards = container.querySelectorAll(".job-card:not(.is-in)");
  cards.forEach((card, i) => {
    if (i >= 12) {
      card.classList.add("is-in"); // no animation beyond the first dozen
      return;
    }
    card.style.animationDelay = `${Math.min(i * 45, 400)}ms`;
    card.classList.add("is-in");
  });

  // Score arcs sweep from 0 to their value once mounted.
  for (const arc of container.querySelectorAll(".score-arc")) {
    const target = arc.dataset.value;
    requestAnimationFrame(() => {
      arc.setAttribute("stroke-dasharray", String(target));
    });
  }
}

function jobCard(job, index, match, handlers) {
  const card = document.createElement("article");
  card.className = "job-card";
  if (match?.tier) card.classList.add(`tier-${match.tier}`);
  card.dataset.jobIndex = String(index);

  // ---- header: title + score ring
  const head = document.createElement("div");
  head.className = "job-card__head";

  const titleWrap = document.createElement("div");
  titleWrap.style.minWidth = "0";
  const title = document.createElement("div");
  title.className = "job-card__title";
  title.textContent = nonEmpty(job?.title) || "Untitled role";
  titleWrap.appendChild(title);

  const company = document.createElement("div");
  company.className = "job-card__company";
  company.textContent = nonEmpty(job?.company) || "";
  if (company.textContent) titleWrap.appendChild(company);
  head.appendChild(titleWrap);

  if (match && isFinite(match.score)) {
    head.appendChild(scoreRing(match.score, match.tier));
  }
  card.appendChild(head);

  // ---- meta: location + remote hint (only what state provides)
  const metaBits = [];
  if (nonEmpty(job?.location)) metaBits.push(job.location);
  const meta = document.createElement("div");
  meta.className = "job-card__meta";
  meta.textContent = metaBits.join(" · ");
  if (!meta.textContent) meta.hidden = true;
  card.appendChild(meta);

  // ---- skills chips: matched first, then missing (advisory)
  if (match) {
    const matchedSkills = stringsOnly(match.matched_skills);
    const missingSkills = stringsOnly(match.missing_required);
    if (matchedSkills.length || missingSkills.length) {
      const chips = document.createElement("div");
      chips.className = "chips";
      for (const name of matchedSkills.slice(0, 6)) {
        chips.appendChild(chip(`✓ ${name}`, "chip--matched"));
      }
      for (const name of missingSkills.slice(0, 4)) {
        chips.appendChild(chip(`⚠ ${name}`, "chip--missing"));
      }
      card.appendChild(chips);
    }
  }

  // ---- actions
  const actions = document.createElement("div");
  actions.className = "job-card__actions";

  if (match) {
    const viewBtn = document.createElement("button");
    viewBtn.type = "button";
    viewBtn.className = "btn btn--primary";
    viewBtn.textContent = "View Match";
    viewBtn.addEventListener("click", () => handlers.onViewMatch?.(index, match));
    actions.appendChild(viewBtn);
  }

  const tailorBtn = document.createElement("button");
  tailorBtn.type = "button";
  tailorBtn.className = "btn";
  tailorBtn.textContent = "Tailor Resume";
  tailorBtn.addEventListener("click", () => handlers.onTailor?.(index));
  actions.appendChild(tailorBtn);

  if (nonEmpty(job?.job_url)) {
    const link = document.createElement("a");
    link.className = "btn";
    link.href = /** @type {string} */ (job.job_url);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open posting ↗";
    actions.appendChild(link);
  }

  card.appendChild(actions);
  return card;
}

function chip(text, modifier) {
  const span = document.createElement("span");
  span.className = `chip ${modifier}`;
  span.textContent = text;
  return span;
}

function scoreRing(score, tier) {
  const wrap = document.createElement("div");
  wrap.className = "score-ring";
  if (tier) wrap.classList.add(`tier-${tier}`);

  const pct = Math.max(0, Math.min(100, Number(score)));
  const r = 17;
  const circumference = 2 * Math.PI * r;
  const target = (pct / 100) * circumference;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 44 44");
  svg.setAttribute("width", "46");
  svg.setAttribute("height", "46");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Match score ${Math.round(pct)} percent`);

  const track = circle(r, "#232b36", 4);
  const arc = circle(
    r,
    TIER_COLORS[tier] || "#8b949e",
    4,
    `0 ${circumference}` // animated to target after mount
  );
  arc.setAttribute("data-value", `${target} ${circumference}`);
  arc.classList.add("score-arc");
  arc.setAttribute("transform", "rotate(-90 22 22)");
  arc.setAttribute("stroke-linecap", "round");

  const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
  text.setAttribute("x", "22");
  text.setAttribute("y", "26");
  text.setAttribute("text-anchor", "middle");
  text.setAttribute("font-size", "11.5");
  text.textContent = String(Math.round(pct));

  svg.append(track, arc, text);

  const caption = document.createElement("div");
  caption.className = "score-caption";
  caption.textContent = "match";

  wrap.append(svg, caption);
  return wrap;
}

function circle(r, stroke, width, dashArray) {
  const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  c.setAttribute("cx", "22");
  c.setAttribute("cy", "22");
  c.setAttribute("r", String(r));
  c.setAttribute("fill", "none");
  c.setAttribute("stroke", stroke);
  c.setAttribute("stroke-width", String(width));
  if (dashArray) c.setAttribute("stroke-dasharray", dashArray);
  return c;
}

function nonEmpty(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function stringsOnly(value) {
  return Array.isArray(value)
    ? value.filter((v) => typeof v === "string" && v).map((v) => v)
    : [];
}
