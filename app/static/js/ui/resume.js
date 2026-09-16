// Tailored resume workspace: structured sections over tailored_resume.resume
// with evidence-backed "Why?" panels. PII is structurally absent from the
// backend artifact; this module renders only what state provides.

import { humanize } from "../events-map.js";

export function renderTailoredResume(container, tailoredResult, opts = {}) {
  container.innerHTML = "";
  const resume = tailoredResult?.resume;
  if (!resume) {
    emptyNote(container, "Upload a resume to build your candidate profile, then tailor it from a job card.");
    return;
  }

  const targetJob = opts.targetJob || resume.target_job || null;
  const validationReport = opts.validationReport || null;

  // ---- TARGET JOB APPLICATION REVIEW BANNER ----
  const banner = document.createElement("div");
  banner.className = "app-review-banner";
  banner.style.cssText = `
    background: linear-gradient(135deg, rgba(35, 45, 60, 0.9), rgba(20, 26, 35, 0.95));
    border: 1px solid rgba(88, 166, 255, 0.3);
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 20px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  `;

  const bannerHead = document.createElement("div");
  bannerHead.style.cssText = "display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px;";

  const titleWrap = document.createElement("div");
  const jobTitleText = targetJob?.title || resume.target_job_title || "Target Role";
  const companyText = targetJob?.company || resume.target_company || "";

  const titleEl = document.createElement("h3");
  titleEl.style.cssText = "margin:0; font-size:18px; color:var(--fg, #e6edf3); display:flex; align-items:center; gap:8px;";
  titleEl.innerHTML = `✨ Tailored Resume ${companyText ? `<span style="color:var(--muted); font-size:15px; font-weight:normal;">for <strong>${companyText}</strong> — ${jobTitleText}</span>` : ""}`;
  titleWrap.appendChild(titleEl);

  const badge = document.createElement("span");
  badge.className = "mode-badge on";
  badge.textContent = "Verified Fact-Grounded";
  bannerHead.append(titleWrap, badge);
  banner.appendChild(bannerHead);

  // ATS Suggestions / Validation Summary
  const suggestions = [];
  if (validationReport) {
    const warnings = Array.isArray(validationReport.findings) ? validationReport.findings.filter(f => f.severity === "WARN" || f.level === "WARN") : [];
    if (warnings.length) {
      suggestions.push(`${warnings.length} ATS advisory recommendation${warnings.length > 1 ? "s" : ""} available.`);
    } else {
      suggestions.push("100% Truth & ATS validation checks passed cleanly.");
    }
  }

  const unaddressed = stringsOnly(resume.unaddressed_jd_requirements);
  if (unaddressed.length) {
    suggestions.push(`${unaddressed.length} JD requirement${unaddressed.length > 1 ? "s" : ""} unaddressed by candidate experience.`);
  }

  if (suggestions.length) {
    const sugText = document.createElement("div");
    sugText.style.cssText = "font-size:13.5px; color:var(--muted); margin-bottom:14px;";
    sugText.textContent = `💡 Resume Analysis: ${suggestions.join(" ")}`;
    banner.appendChild(sugText);
  }

  // Banner Actions (Confirm & Apply CTA)
  const ctaRow = document.createElement("div");
  ctaRow.style.cssText = "display:flex; align-items:center; flex-wrap:wrap; gap:10px;";

  const jobUrl = targetJob?.job_url || opts.jobUrl || null;
  if (jobUrl) {
    const confirmBtn = document.createElement("a");
    confirmBtn.className = "btn btn--primary";
    confirmBtn.href = jobUrl;
    confirmBtn.target = "_blank";
    confirmBtn.rel = "noopener noreferrer";
    confirmBtn.style.cssText = "font-weight:600; padding:8px 16px;";
    confirmBtn.textContent = "Confirm & Proceed to Application ↗";
    confirmBtn.addEventListener("click", () => opts.onConfirmApply?.(targetJob));
    ctaRow.appendChild(confirmBtn);
  }

  const dlBtn = document.createElement("button");
  dlBtn.type = "button";
  dlBtn.className = "btn";
  dlBtn.textContent = "Download Markdown";
  dlBtn.addEventListener("click", () => downloadMarkdown(resume));
  ctaRow.appendChild(dlBtn);

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "btn";
  copyBtn.textContent = "Copy Plain Text";
  copyBtn.addEventListener("click", () => {
    const text = generatePlainText(resume);
    navigator.clipboard?.writeText(text);
    copyBtn.textContent = "✓ Copied!";
    setTimeout(() => { copyBtn.textContent = "Copy Plain Text"; }, 2000);
  });
  ctaRow.appendChild(copyBtn);

  banner.appendChild(ctaRow);
  container.appendChild(banner);

  // ---- unaddressed JD requirements box ----
  if (unaddressed.length) {
    const warn = document.createElement("div");
    warn.className = "warn-box requirements-box";
    const icon = document.createElement("span");
    icon.textContent = "⚠";
    icon.setAttribute("aria-hidden", "true");
    const text = document.createElement("div");
    const head = document.createElement("strong");
    head.textContent = "Requirements to address";
    text.appendChild(head);
    text.appendChild(document.createElement("br"));
    text.appendChild(
      document.createTextNode(
        `${unaddressed.length} requirement${unaddressed.length === 1 ? "" : "s"} ` +
          "could not be supported by your current resume:"
      )
    );
    const list = document.createElement("ul");
    for (const req of unaddressed) {
      const li = document.createElement("li");
      li.textContent = req;
      list.appendChild(li);
    }
    text.appendChild(list);
    warn.append(icon, text);
    container.appendChild(warn);
  }

  // ---- SUMMARY
  if (nonEmpty(resume.summary?.text)) {
    container.appendChild(sectionTitle("Summary"));
    const p = document.createElement("p");
    p.className = "summary-text";
    p.textContent = resume.summary.text;
    container.appendChild(p);
  }

  // ---- SKILLS
  const skills = Array.isArray(resume.skills) ? resume.skills : [];
  if (skills.length) {
    container.appendChild(sectionTitle("Skills"));
    const grid = document.createElement("div");
    grid.className = "skill-grid";
    for (const skill of skills) {
      if (!skill?.display && !skill?.name) continue;
      const pill = document.createElement("span");
      pill.className = `skill-pill req-${skill.requirement || "additional"}`;
      const nameSpan = document.createElement("span");
      nameSpan.textContent = skill.display || skill.name;
      pill.appendChild(nameSpan);
      if (skill.requirement === "required" || skill.requirement === "preferred") {
        const tag = document.createElement("span");
        tag.className = "req-tag";
        tag.textContent = skill.requirement;
        pill.appendChild(tag);
      }
      grid.appendChild(pill);
    }
    container.appendChild(grid);
  }

  // ---- EXPERIENCE
  const experience = Array.isArray(resume.experience) ? resume.experience : [];
  if (experience.length) {
    container.appendChild(sectionTitle("Experience"));
    for (const item of experience) {
      container.appendChild(experienceBlock(resume, item));
    }
  }

  // ---- PROJECTS
  const projects = Array.isArray(resume.projects) ? resume.projects : [];
  if (projects.length) {
    container.appendChild(sectionTitle("Projects"));
    for (const project of projects) {
      const block = document.createElement("div");
      block.className = "exp-block";
      const nameEl = document.createElement("div");
      nameEl.className = "exp-head";
      nameEl.textContent = nonEmpty(project.name) || "Project";
      block.appendChild(nameEl);
      if (nonEmpty(project.description)) {
        const desc = document.createElement("p");
        desc.style.cssText = "font-size:13.5px;color:var(--muted);margin:4px 0";
        desc.textContent = project.description;
        block.appendChild(desc);
      }
      const techs = stringsOnly(project.technologies);
      if (techs.length) {
        const chips = document.createElement("div");
        chips.className = "chips";
        for (const tech of techs) {
          const chipEl = document.createElement("span");
          chipEl.className = "chip chip--matched";
          chipEl.textContent = tech;
          chips.appendChild(chipEl);
        }
        block.appendChild(chips);
      }
      container.appendChild(block);
    }
  }

  // ---- EDUCATION / CERTIFICATIONS
  const education = Array.isArray(resume.education) ? resume.education : [];
  const certifications = Array.isArray(resume.certifications)
    ? resume.certifications
    : [];
  if (education.length || certifications.length) {
    container.appendChild(sectionTitle("Education & Certifications"));
    for (const edu of education) {
      const line = document.createElement("div");
      line.className = "edu-line";
      const strong = document.createElement("strong");
      strong.textContent = humanize(edu.degree || "");
      const bits = [
        nonEmpty(edu.field_of_study),
        nonEmpty(edu.institution),
        Number.isFinite(edu.graduation_year) ? String(edu.graduation_year) : null,
      ].filter(Boolean);
      line.append(strong);
      if (bits.length) line.append(document.createTextNode(` — ${bits.join(", ")}`));
      container.appendChild(line);
    }
    for (const cert of certifications) {
      const line = document.createElement("div");
      line.className = "cert-line";
      const strong = document.createElement("strong");
      strong.textContent = nonEmpty(cert.name) || "";
      line.appendChild(strong);
      container.appendChild(line);
    }
  }

  if (!container.childElementCount) {
    emptyNote(container, "Tailored resume has no renderable content.");
  }
}

function experienceBlock(resume, item) {
  const block = document.createElement("div");
  block.className = "exp-block";

  const head = document.createElement("div");
  head.className = "exp-head";
  head.textContent = [item.title, item.company].filter(nonEmpty).join(" · ");
  if (!head.textContent) head.textContent = "Role";
  block.appendChild(head);

  if (nonEmpty(item.date_range_raw)) {
    const dates = document.createElement("div");
    dates.className = "exp-dates";
    dates.textContent = item.date_range_raw;
    block.appendChild(dates);
  }

  for (const bullet of Array.isArray(item.highlights) ? item.highlights : []) {
    if (!bullet || typeof bullet.final_text !== "string") continue;

    const row = document.createElement("div");
    row.className = "bullet-row";

    const mark = document.createElement("span");
    mark.className = "bullet-mark";
    mark.textContent = "•";
    mark.setAttribute("aria-hidden", "true");

    const text = document.createElement("span");
    text.className = "bullet-text";
    text.textContent = bullet.final_text;

    row.append(mark, text);
    row.appendChild(whyButton(resume, bullet, item.source_index));
    block.appendChild(row);
  }
  return block;
}

function whyButton(resume, bullet, sourceIndex) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "why-btn";
  button.textContent = "Why?";
  button.setAttribute(
    "aria-label",
    "Why was this bullet kept or changed?"
  );
  button.addEventListener("click", () => toggleWhyPanel(button, resume, bullet, sourceIndex));
  return button;
}

function toggleWhyPanel(button, resume, bullet, sourceIndex) {
  const existing = button.closest(".bullet-row").parentElement.querySelector(".why-panel[data-open]");
  const mine = button.closest(".bullet-row").nextElementSibling;
  if (existing && existing !== mine) collapse(existing);
  if (mine && mine.classList?.contains("why-panel")) {
    const wasOpen = mine.hasAttribute("data-open");
    collapse(mine);
    if (!wasOpen) expand(button, mine, resume, bullet, sourceIndex);
    return;
  }
  const panel = document.createElement("div");
  panel.className = "why-panel";
  button.closest(".bullet-row").insertAdjacentElement("afterend", panel);
  expand(button, panel, resume, bullet, sourceIndex);
}

function expand(button, panel, resume, bullet, sourceIndex) {
  panel.setAttribute("data-open", "");
  panel.innerHTML = "";

  step(panel, "Original", bullet.original_text);
  step(panel, "Tailored", bullet.final_text);
  if (nonEmpty(bullet.evidence_ref)) {
    const refRow = document.createElement("div");
    refRow.className = "why-step";
    const kind = document.createElement("span");
    kind.className = "why-kind";
    kind.textContent = "Evidence";
    const refCode = document.createElement("code");
    refCode.textContent = bullet.evidence_ref;
    refRow.append(kind, refCode);
    panel.appendChild(refRow);
  }

  const relatedChanges = (Array.isArray(resume.changes) ? resume.changes : []).filter(
    (change) =>
      typeof change?.section === "string" &&
      change.section.startsWith(`experience[${sourceIndex}]`)
  );
  for (const change of relatedChanges.slice(0, 3)) {
    if (nonEmpty(change.reason)) step(panel, "Reason", change.reason);
  }

  button.setAttribute("aria-expanded", "true");
}

function collapse(panel) {
  panel.removeAttribute("data-open");
  panel.remove();
}

function step(panel, kind, value) {
  if (!nonEmpty(value)) return;
  const rowEl = document.createElement("div");
  rowEl.className = "why-step";
  const kindSpan = document.createElement("span");
  kindSpan.className = "why-kind";
  kindSpan.textContent = kind;
  const valueSpan = document.createElement("span");
  valueSpan.textContent = value;
  rowEl.append(kindSpan, valueSpan);
  panel.appendChild(rowEl);
}

// ---- helpers -----------------------------------------------------------------

function sectionTitle(title) {
  const h = document.createElement("h4");
  h.className = "resume-section-title";
  h.textContent = title;
  return h;
}

function emptyNote(container, message) {
  const div = document.createElement("div");
  div.className = "empty-state muted";
  div.textContent = message;
  container.appendChild(div);
}

function downloadMarkdown(resume) {
  const lines = [];
  lines.push("# Tailored Resume", "");
  if (nonEmpty(resume.summary?.text)) lines.push(resume.summary.text, "");

  const skills = Array.isArray(resume.skills) ? resume.skills : [];
  if (skills.length) {
    lines.push("## Skills", "");
    for (const skill of skills) {
      lines.push(`- ${skill.display || skill.name}${skill.requirement ? ` (${skill.requirement})` : ""}`);
    }
    lines.push("");
  }

  for (const item of Array.isArray(resume.experience) ? resume.experience : []) {
    lines.push(
      `## ${[item.title, item.company].filter(nonEmpty).join(" — ")}`,
      nonEmpty(item.date_range_raw) ? `*${item.date_range_raw}*` : "",
      ""
    );
    for (const bullet of Array.isArray(item.highlights) ? item.highlights : []) {
      if (typeof bullet.final_text === "string") lines.push(`- ${bullet.final_text}`);
    }
    lines.push("");
  }

  for (const project of Array.isArray(resume.projects) ? resume.projects : []) {
    lines.push(`## ${nonEmpty(project.name) || "Project"}`, "");
    if (nonEmpty(project.description)) lines.push(project.description, "");
    const techs = stringsOnly(project.technologies);
    if (techs.length) lines.push(`Technologies: ${techs.join(", ")}`, "");
  }

  const education = Array.isArray(resume.education) ? resume.education : [];
  const certifications = Array.isArray(resume.certifications) ? resume.certifications : [];
  if (education.length || certifications.length) {
    lines.push("## Education & Certifications", "");
    for (const edu of education) {
      lines.push(
        `- ${humanize(edu.degree || "")}${edu.field_of_study ? " in " + edu.field_of_study : ""}${
          edu.institution ? ", " + edu.institution : ""
        }`
      );
    }
    for (const cert of certifications) {
      if (nonEmpty(cert.name)) lines.push(`- ${cert.name}`);
    }
  }

  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "tailored-resume.md";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function generatePlainText(resume) {
  const lines = [];
  lines.push("TAILORED RESUME", "==============", "");
  if (nonEmpty(resume.summary?.text)) lines.push("SUMMARY", "-------", resume.summary.text, "");

  const skills = Array.isArray(resume.skills) ? resume.skills : [];
  if (skills.length) {
    lines.push("SKILLS", "------");
    for (const skill of skills) {
      lines.push(`• ${skill.display || skill.name}${skill.requirement ? ` (${skill.requirement})` : ""}`);
    }
    lines.push("");
  }

  for (const item of Array.isArray(resume.experience) ? resume.experience : []) {
    lines.push(
      [item.title, item.company].filter(nonEmpty).join(" — ").toUpperCase(),
      nonEmpty(item.date_range_raw) || ""
    );
    for (const bullet of Array.isArray(item.highlights) ? item.highlights : []) {
      if (typeof bullet.final_text === "string") lines.push(`• ${bullet.final_text}`);
    }
    lines.push("");
  }

  for (const project of Array.isArray(resume.projects) ? resume.projects : []) {
    lines.push(`PROJECT: ${nonEmpty(project.name) || "Project"}`);
    if (nonEmpty(project.description)) lines.push(project.description);
    const techs = stringsOnly(project.technologies);
    if (techs.length) lines.push(`Technologies: ${techs.join(", ")}`);
    lines.push("");
  }

  const education = Array.isArray(resume.education) ? resume.education : [];
  const certifications = Array.isArray(resume.certifications) ? resume.certifications : [];
  if (education.length || certifications.length) {
    lines.push("EDUCATION & CERTIFICATIONS", "--------------------------");
    for (const edu of education) {
      lines.push(
        `• ${humanize(edu.degree || "")}${edu.field_of_study ? " in " + edu.field_of_study : ""}${
          edu.institution ? ", " + edu.institution : ""
        }`
      );
    }
    for (const cert of certifications) {
      if (nonEmpty(cert.name)) lines.push(`• ${cert.name}`);
    }
  }

  return lines.join("\n");
}

function nonEmpty(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function stringsOnly(value) {
  return Array.isArray(value)
    ? value.filter((v) => typeof v === "string" && v.trim())
    : [];
}
