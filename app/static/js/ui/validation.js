// Truth + ATS validation dashboard. Severity semantics preserved:
// truth failure => FAIL; ATS findings => at most WARN.

export function renderValidation(container, report) {
  container.textContent = "";
  if (!report) {
    container.textContent = "No validation report available.";
    return;
  }

  const banner = document.createElement("div");
  banner.className = `validation-banner status-${report.overall_status.toLowerCase()}`;
  banner.textContent = `${report.overall_status}`;
  container.appendChild(banner);

  // ---- Truth panel -------------------------------------------------------
  const truthPanel = document.createElement("div");
  truthPanel.className = "validation-panel";
  const truthTitle = document.createElement("h4");
  truthTitle.textContent = "Truth / Authenticity — " + (report.truth?.status || "?");
  truthTitle.className = "truth-title " +
    (report.truth?.status === "FAIL" ? "fail" : "pass");
  truthPanel.append(truthTitle);
  for (const check of report.truth?.checks || []) {
    const row = document.createElement("div");
    row.className = `check-row check-${check.status}`;
    const icon = document.createElement("span");
    icon.textContent = check.status === "passed" ? "✓"
      : check.status === "failed" ? "✕"
      : check.status === "warning" ? "⚠" : "ℹ";
    const label = document.createElement("code");
    label.textContent = check.name.split("_")[0];
    const detail = document.createElement("span");
    detail.textContent = check.detail;
    row.append(icon, label, detail);
    truthPanel.append(row);
  }
  container.appendChild(truthPanel);

  // ---- ATS panel ---------------------------------------------------------
  const atsPanel = document.createElement("div");
  atsPanel.className = "validation-panel";
  const atsTitle = document.createElement("h4");
  atsTitle.textContent = "ATS Compatibility — " + (report.ats?.status || "?");
  atsTitle.className = "ats-title " +
    (report.ats?.status === "WARN" ? "warn" : "pass");
  atsPanel.append(atsTitle);

  const metrics = report.ats?.metrics;
  if (metrics) {
    const grid = document.createElement("div");
    grid.className = "metrics-grid";
    for (const [label, key] of [
      ["Required skills", "required_coverage_pct"],
      ["Preferred skills", "preferred_coverage_pct"],
      ["JD responsibilities", "responsibility_token_coverage_pct"],
    ]) {
      const item = document.createElement("div");
      item.className = "metric";
      item.innerHTML = "";
      const value = document.createElement("strong");
      value.textContent = metrics[key] + "%";
      const caption = document.createElement("small");
      caption.textContent = label;
      item.append(value, document.createElement("br"), caption);
      grid.append(item);
    }
    atsPanel.append(grid);

    if (metrics.keyword_counts?.length) {
      const table = document.createElement("table");
      table.className = "keyword-table";
      const head = table.createTHead().insertRow();
      for (const label of ["Term", "Original", "Tailored"]) {
        const th = document.createElement("th");
        th.textContent = label; head.append(th);
      }
      const body = table.createTBody();
      for (const entry of metrics.keyword_counts.slice(0, 20)) {
        const row = body.insertRow();
        row.insertCell().textContent = entry.term;
        row.insertCell().textContent = String(entry.original);
        row.insertCell().textContent = String(entry.tailored);
      }
      atsPanel.append(table);
    }
  }

  for (const check of report.ats?.checks || []) {
    const row = document.createElement("div");
    row.className = `check-row check-${check.status}`;
    row.textContent = `${check.name}: ${check.status} — ${check.detail}`;
    atsPanel.append(row);
  }
  container.appendChild(atsPanel);

  if (report.warnings?.length) {
    const warningsBox = document.createElement("div");
    warningsBox.className = "warn-box";
    warningsBox.textContent = "Warnings: " + report.warnings.join(" | ");
    container.appendChild(warningsBox);
  }
}
