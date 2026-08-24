// Tailored resume workspace: structured sections over tailored_resume.resume
// with evidence-backed "Why?" panels. PII is structurally absent from the
// backend artifact; this module renders only what state provides.

import { humanize } from "../events-map.js";

export function renderTailoredResume(container, tailoredResult) {
  container.innerHTML = "";
  const resume = tailoredResult?.resume;
  if (!resume) {
    emptyNote(container, "Upload a resume to build your candidate profile, then tailor it from a job card.");
    return;
  }

  // ---- unaddressed JD requirements (never converted into claims)
  const unaddressed = stringsOnly(resume.unaddressed_jd_requirements);
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

  // ---- download (client-side projection of verified facts only)
  const downloadRow = document.createElement("div");
  downloadRow.className = "download-row";
  const dlBtn = document.createElement("button");
  dlBtn.type = "button";
  dlBtn.className = "btn";
  dlBtn.textContent = "Download Markdown";
  dlBtn.addEventListener("click", () => downloadMarkdown(resume));
  downloadRow.appendChild(dlBtn);
  container.appendChild(downloadRow);

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

function nonEmpty(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function stringsOnly(value) {
  return Array.isArray(value)
    ? value.filter((v) => typeof v === "string" && v.trim())
    : [];
}
