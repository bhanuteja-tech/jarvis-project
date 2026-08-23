// Tailored resume workspace: renders tailored_resume.resume with
// evidence-backed "Why?" panels. PII is structurally absent from the source.

export function renderTailoredResume(container, tailoredResult) {
  container.textContent = "";
  const resume = tailoredResult?.resume;
  if (!resume) {
    container.textContent = "No tailored resume available.";
    return;
  }

  if (resume.unaddressed_jd_requirements?.length) {
    const warn = document.createElement("div");
    warn.className = "warn-box";
    warn.textContent =
      "JD requirements not evidenced in your resume (never added): " +
      resume.unaddressed_jd_requirements.join(", ");
    container.appendChild(warn);
  }

  appendSectionTitle(container, "Summary");
  container.appendChild(textP(resume.summary?.text || ""));

  appendSectionTitle(container, "Skills");
  for (const skill of resume.skills || []) {
    const row = document.createElement("div");
    row.className = "skill-row";
    const badge = document.createElement("span");
    badge.className = `chip req-${skill.requirement}`;
    badge.textContent = skill.requirement;
    row.append(badge, textSpan(skill.display));
    container.appendChild(row);
  }

  appendSectionTitle(container, "Experience");
  for (const item of resume.experience || []) {
    const block = document.createElement("div");
    block.className = "exp-block";
    const head = document.createElement("strong");
    head.textContent = [item.title, item.company].filter(Boolean).join(" — ");
    block.append(head);
    if (item.date_range_raw) {
      const dates = document.createElement("div");
      dates.className = "muted";
      dates.textContent = item.date_range_raw;
      block.append(dates);
    }
    for (const bullet of item.highlights || []) {
      const row = document.createElement("div");
      row.className = "bullet-row";
      row.append(textSpan("• " + bullet.final_text));
      row.appendChild(whyButton(resume, bullet, item.source_index));
      block.append(row);
    }
    container.appendChild(block);
  }

  appendSectionTitle(container, "Education / Certifications");
  for (const education of resume.education || []) {
    container.appendChild(textSpan(
      `${education.degree}${education.field_of_study ? " in " + education.field_of_study : ""}` +
      (education.institution ? ` — ${education.institution}` : "") +
      (education.graduation_year ? ` (${education.graduation_year})` : "")
    ));
  }
  for (const certification of resume.certifications || []) {
    container.appendChild(textSpan("★ " + certification.name));
  }
}

function whyButton(resume, bullet, sourceIndex) {
  const button = document.createElement("button");
  button.className = "why-btn";
  button.textContent = "Why?";
  button.addEventListener("click", () => {
    let panel = container.querySelector(".why-panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "why-panel";
      container.appendChild(panel);
    }
    panel.textContent = "";
    const original = document.createElement("div");
    original.textContent = "Original: " + bullet.original_text;
    const finalText = document.createElement("div");
    finalText.textContent = "Tailored: " + bullet.final_text;
    const ref = document.createElement("code");
    ref.textContent = bullet.evidence_ref;

    const relatedChanges = (resume.changes || []).filter(change =>
      change.section.startsWith(`experience[${sourceIndex}]`)
    );
    panel.append(
      original,
      document.createElement("hr"),
      finalText,
      document.createElement("hr"),
      ref
    );
    for (const change of relatedChanges) {
      const line = document.createElement("div");
      line.className = "muted";
      line.textContent = change.reason;
      panel.append(line);
    }
  });
  return button;
}

function appendSectionTitle(container, title) {
  const h = document.createElement("h4");
  h.textContent = title;
  container.appendChild(h);
}

function textSpan(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div;
}
