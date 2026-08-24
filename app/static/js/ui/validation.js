// Validation dashboard: two severity-distinct panels.
// TRUTH failure = serious (FAIL); ATS findings = advisory (max WARN).
// Renders only backend CheckResult facts: {name, status, detail}.

const STATUS_ICON = {
  passed: "✓",
  failed: "✕",
  warning: "⚠",
  info: "ℹ",
};

const STATUS_CLASS = {
  passed: "st-passed",
  failed: "st-failed",
  warning: "st-warning",
  info: "st-info",
};

// Curated recruiter-friendly names for known checks (collapsed row text).
// Unknown checks fall back to their short id — nothing is invented.
const CHECK_LABELS = {
  T1_token_containment: "Every claim traces to your resume",
  T2_original_fidelity: "Original bullets unchanged at source",
  T3_evidence_refs_resolvable: "Evidence references consistent",
  T4_unsupported_skills: "No unsupported skills added",
  T5_missing_skills_not_inserted: "Missing requirements never inserted",
  T6_employer_title_date_consistency: "Employers, titles and dates intact",
  T8_duplicate_content: "No duplicated content",
  T9_pii_absence: "No contact details exposed",
  T10_meta_consistency: "Generation metadata coherent",
  chronology_info: "Career timeline notes",
  A1_required_skill_coverage: "Required skills coverage",
  A2_preferred_skill_coverage: "Preferred skills coverage",
  A3_responsibility_token_coverage: "JD responsibility alignment",
  A4_keyword_counts: "Keyword frequency table",
  A5_keyword_stuffing: "Keyword stuffing check",
  A6_section_order: "Section ordering",
  A7_format_limits: "Formatting limits",
  A8_date_range_consistency: "Consistent date formatting",
};

function friendlyLabel(name) {
  if (typeof name !== "string") return "";
  return CHECK_LABELS[name] || shortId(name);
}

export function renderValidation(container, report) {
  container.innerHTML = "";
  if (!report || typeof report !== "object") {
    emptyNote(container, "Validation appears after tailoring a resume — every claim is then re-verified against your original.");
    return;
  }

  container.appendChild(banner(report.overall_status));

  const truth = report.truth;
  if (truth) {
    container.appendChild(
      panel({
        kind: "truth",
        title: "Resume Truth",
        status: truth.status,
        badgeText: truth.status,
        note: "A truth failure means content could not be verified against your original resume. Serious.",
        checks: Array.isArray(truth.checks) ? truth.checks : [],
      })
    );
  }

  const ats = report.ats;
  if (ats) {
    const panelEl = panel({
      kind: "ats",
      title: "ATS Readiness",
      status: ats.status,
      badgeText: ats.status,
      note: "Advisory recruiter-system readability signals. Warnings are suggestions, not failures.",
      checks: Array.isArray(ats.checks) ? ats.checks : [],
    });

    const metrics = ats.metrics;
    if (metrics && typeof metrics === "object") {
      panelEl.appendChild(metricsGrid(metrics));
      panelEl.appendChild(keywordTable(metrics.keyword_counts));
    }
    // ATS check rows appended after metrics for scannability:
    const rowsWrap = document.createElement("div");
    for (const check of Array.isArray(ats.checks) ? ats.checks : []) {
      rowsWrap.appendChild(checkDetails(check));
    }
    panelEl.appendChild(rowsWrap);
    container.appendChild(panelEl);
  }
}

function banner(overall) {
  const div = document.createElement("div");
  const key = String(overall || "").toLowerCase();
  div.className = `validation-banner status-${key}`;
  div.setAttribute("role", "status");

  const label = document.createElement("span");
  label.textContent = String(overall || "UNKNOWN");

  const hint = document.createElement("small");
  hint.textContent =
    key === "pass"
      ? "All truth checks passed; no ATS warnings."
      : key === "warn"
        ? "Truth intact — advisory ATS suggestions only."
        : key === "fail"
          ? "Unverifiable content detected — do not send as-is."
          : "";
  div.append(label, hint);
  return div;
}

function panel({ kind, title, status, badgeText, note, checks }) {
  const el = document.createElement("div");
  el.className = `vpanel ${kind} ${String(status).toLowerCase()}`;

  const head = document.createElement("div");
  head.className = "vpanel-head";
  const titleEl = document.createElement("span");
  titleEl.className = "vpanel-title";
  titleEl.textContent = title;
  const badge = document.createElement("span");
  badge.className = "vpanel-badge";
  badge.textContent = String(badgeText || "?");
  badge.classList.add(STATUS_CLASS[statusClassOf(badgeText)] || "");
  head.append(titleEl, badge);
  el.appendChild(head);

  // Truth checks render as the expandable list; ATS rows are added by the
  // caller after metrics.
  if (kind === "truth") {
    const wrap = document.createElement("div");
    for (const check of checks) wrap.appendChild(checkDetails(check));
    el.appendChild(wrap);
  }

  if (note) {
    const noteEl = document.createElement("p");
    noteEl.className = "vpanel-note";
    noteEl.textContent = note;
    el.appendChild(noteEl);
  }
  return el;
}

function checkDetails(check) {
  const details = document.createElement("details");
  details.className = "check-details";

  const summary = document.createElement("summary");
  const icon = document.createElement("span");
  icon.className = `check-icon ${STATUS_CLASS[check?.status] || ""}`;
  icon.textContent = STATUS_ICON[check?.status] || "·";
  icon.setAttribute("aria-hidden", "true");

  const id = document.createElement("span");
  id.className = "check-id";
  id.textContent = shortId(check?.name);

  const text = document.createElement("span");
  text.className = "check-summary-text";
  // Collapsed row: "✓ T3 — Evidence consistency" (backend status + label).
  const label = friendlyLabel(check?.name);
  const firstLine =
    typeof check?.detail === "string" && check.detail
      ? check.detail.split("; ")[0]
      : "";
  text.textContent = label && !label.startsWith(firstLine.slice(0, 8))
    ? `${label}${firstLine ? ` — ${truncate(firstLine, 70)}` : ""}`
    : truncate(firstLine, 110);

  summary.append(icon, id, text);

  const body = document.createElement("div");
  body.className = "check-body";
  body.textContent = nonEmpty(check?.detail) || "No further details.";

  details.append(summary, body);
  details.setAttribute(
    "aria-label",
    `${friendlyLabel(check?.name) || shortId(check?.name)} — ${check?.status}`
  );
  return details;
}

function metricsGrid(metrics) {
  const grid = document.createElement("div");
  grid.className = "metrics-grid";
  for (const [label, key] of [
    ["Required skills", "required_coverage_pct"],
    ["Preferred skills", "preferred_coverage_pct"],
    ["JD responsibilities", "responsibility_token_coverage_pct"],
  ]) {
    const value = Number(metrics[key]);
    const cell = document.createElement("div");
    cell.className = "metric";
    const strong = document.createElement("strong");
    strong.textContent = isFinite(value) ? `${Math.round(value)}%` : "—";
    const small = document.createElement("small");
    small.textContent = label;
    cell.append(strong, small);
    grid.appendChild(cell);
  }
  return grid;
}

function keywordTable(counts) {
  const list = Array.isArray(counts) ? counts : [];
  if (!list.length) return document.createDocumentFragment();

  const table = document.createElement("table");
  table.className = "keyword-table";
  const head = table.createTHead().insertRow();
  for (const label of ["Term", "Original", "Tailored"]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    head.appendChild(th);
  }
  const tbody = table.createTBody();
  for (const entry of list.slice(0, 20)) {
    const row = tbody.insertRow();
    if (
      Number(entry.tailored) >= 3 &&
      isFinite(entry.original) &&
      Number(entry.tailored) > 2 * Number(entry.original)
    ) {
      row.className = "inflated";
      row.title = "Tailored frequency noticeably exceeds the original resume.";
    }
    const termCell = row.insertCell();
    termCell.textContent = String(entry.term ?? "");
    const origCell = row.insertCell();
    origCell.className = "num";
    origCell.textContent = String(entry.original ?? 0);
    const tailoredCell = row.insertCell();
    tailoredCell.className = "num";
    tailoredCell.textContent = String(entry.tailored ?? 0);
  }
  return table;
}

// ---- helpers -----------------------------------------------------------------

function shortId(name) {
  if (typeof name !== "string") return "—";
  // "T1_token_containment" -> "T1", "A5_keyword_stuffing" -> "A5"
  const match = name.match(/^([TA]\d{1,2})/);
  return match ? match[1] : name.slice(0, 6);
}

function firstSentence(detail) {
  const text = typeof detail === "string" ? detail.trim() : "";
  if (!text) return "";
  const cut = text.indexOf("; ");
  return (cut > 0 ? text.slice(0, cut) : text).slice(0, 120);
}

function truncate(text, max) {
  const value = String(text ?? "").trim();
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function statusClassOf(status) {
  return ["passed", "failed", "warning", "info"].includes(String(status).toLowerCase())
    ? String(status).toLowerCase()
    : "info";
}

function emptyNote(container, message) {
  const div = document.createElement("div");
  div.className = "empty-state muted";
  div.textContent = message;
  container.appendChild(div);
}
