// Drag-and-drop resume upload with state machine.

export function initUploadZone(zone, { onFile, maxChars }) {
  zone.textContent = "Drop your resume (.txt/.md) or click to browse";
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".txt,.md";
  input.hidden = true;
  zone.append(input);

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) readFile(file, onFile, maxChars, setStatus(zone));
  });
  input.addEventListener("change", () => {
    if (input.files[0]) readFile(input.files[0], onFile, maxChars, setStatus(zone));
  });
}

function setStatus(zone) {
  return (message, kind = "") => {
    zone.dataset.state = kind;
    const status = zone.querySelector(".upload-status") || document.createElement("div");
    status.className = `upload-status ${kind}`;
    status.textContent = message;
    if (!status.isConnected) zone.append(status);
  };
}

function readFile(file, onFile, maxChars, setStatusFn) {
  const lower = file.name.toLowerCase();
  if (!lower.endsWith(".txt") && !lower.endsWith(".md")) {
    setStatusFn("✕ Unsupported format (PDF/DOCX not supported). Use .txt or .md", "error");
    return;
  }
  if (file.size > maxChars * 2) {
    setStatusFn(`✕ File too large (max ~${Math.round(maxChars / 1000)}k chars).`, "error");
    return;
  }
  setStatusFn("Reading file…", "working");
  const reader = new FileReader();
  reader.onload = () => {
    setStatusFn("✓ File read; sending for parsing…", "done");
    onFile({ name: file.name, content: reader.result, explicit_text: true });
  };
  reader.onerror = () => setStatusFn("✕ Could not read file.", "error");
  reader.readAsText(file);
}
