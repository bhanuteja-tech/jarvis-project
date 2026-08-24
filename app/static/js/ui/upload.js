// Premium resume upload zone: PDF/DOCX/TXT/MD are FIRST-CLASS formats.
// Drag & drop or browse; files are validated client-side (extension + size)
// AND server-side (extension + magic bytes + size). Bytes travel as base64
// over the existing WS envelope; the server's document-extraction layer
// normalizes everything before the frozen text parser sees it. Contents are
// never rendered here.

const ACCEPT = [".pdf", ".docx", ".txt", ".md"];
const ACCEPT_ATTR =
    ".pdf,.docx,.txt,.md,application/pdf," +
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
    "text/plain,text/markdown";
const FORMAT_LABELS = {
    ".pdf": ["PDF", "pdf-document.svg"],
    ".docx": ["Word document", "docx"],
    ".txt": ["Plain text", "txt"],
    ".md": ["Markdown", "md"],
};
const MAGIC = {
    ".pdf": (bytes) => bytes.length > 4 && bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46,
    ".docx": (bytes) => bytes.length > 1 && bytes[0] === 0x50 && bytes[1] === 0x4b,
};

export function initUploadZone(zone, { onFile, maxBytes, store }) {
    zone.innerHTML = "";

    const input = document.createElement("input");
    input.type = "file";
    input.accept = ACCEPT_ATTR;
    input.hidden = true;
    input.setAttribute("aria-hidden", "true");

    const iconWrap = document.createElement("div");
    iconWrap.className = "upload-icon";
    iconWrap.setAttribute("aria-hidden", "true");
    iconWrap.innerHTML = UPLOAD_ARROW_SVG;

    const title = document.createElement("div");
    title.className = "upload-title";
    title.textContent = "Drop your resume here";

    const hint = document.createElement("div");
    hint.className = "upload-hint";
    hint.textContent = "or click to browse";

    const formats = document.createElement("div");
    formats.className = "upload-formats";
    formats.textContent = "PDF · DOCX · TXT · MD";

    const limit = document.createElement("div");
    limit.className = "upload-limit muted";
    limit.textContent = `Max ${Math.max(1, Math.round(maxBytes / (1024 * 1024)))} MB`;

    const statusEl = document.createElement("div");
    statusEl.className = "upload-status";
    statusEl.hidden = true;

    const progressBar = document.createElement("div");
    progressBar.className = "upload-progress";
    const barFill = document.createElement("span");
    progressBar.appendChild(barFill);
    progressBar.hidden = true;

    const fileCard = document.createElement("div");
    fileCard.className = "file-card";
    fileCard.hidden = true;

    zone.append(iconWrap, title, hint, formats, limit, input);
    zone.insertAdjacentElement("afterend", statusEl);

    let currentFile = null;
    let currentBase64 = null;

    function setStatus(message, kind = "") {
        statusEl.className = `upload-status ${kind}`;
        statusEl.textContent = message || "";
        statusEl.hidden = !message;
    }

    function setProgress(show, fraction = null) {
        progressBar.hidden = !show;
        if (!show) return;
        barFill.style.width =
            fraction == null ? "38%" : `${Math.max(8, Math.min(96, Math.round(fraction * 100)))}%`;
    }

    function showReadyCard(file, base64) {
        currentFile = file;
        currentBase64 = base64;
        const ext = extensionOf(file.name);
        const [label] = FORMAT_LABELS[ext] || ["File"];
        fileCard.innerHTML = "";
        const docIcon = document.createElement("span");
        docIcon.className = "file-card__icon";
        docIcon.textContent = ext.replace(".", "").toUpperCase();
        const meta = document.createElement("div");
        meta.className = "file-card__meta";
        const name = document.createElement("strong");
        name.textContent = file.name;
        name.title = file.name;
        const sub = document.createElement("small");
        sub.textContent = `${label} · ${formatSize(file.size)}`;
        meta.append(name, document.createElement("br"), sub);
        const badge = document.createElement("span");
        badge.className = "file-card__state";
        badge.textContent = "Ready";
        const actions = document.createElement("div");
        actions.className = "file-card__actions";
        const change = document.createElement("button");
        change.type = "button";
        change.className = "btn";
        change.textContent = "Change file";
        change.addEventListener("click", () => input.click());
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "btn btn--danger";
        removeBtn.textContent = "Remove";
        removeBtn.addEventListener("click", () => reset());
        actions.append(change, removeBtn);
        fileCard.append(docIcon, meta, badge, actions);
        fileCard.hidden = false;

        title.textContent = file.name;
        hint.textContent = `${label} · ${formatSize(file.size)}`;
        formats.textContent = "Press Send to analyze this resume";
        setStatus(null);
    }

    function reset() {
        currentFile = null;
        currentBase64 = null;
        fileCard.hidden = true;
        setProgress(false);
        input.value = "";
        store.setUpload({ status: "empty", filename: null, error: null });
        title.textContent = "Drop your resume here";
        hint.textContent = "or click to browse";
        formats.textContent = "PDF · DOCX · TXT · MD";
        setStatus(null);
    }

    async function handleFile(file) {
        const ext = extensionOf(file.name);
        if (!ACCEPT.includes(ext)) {
            fail("This file type isn't supported. Use PDF, DOCX, TXT or MD.");
            return;
        }
        if (file.size === 0) {
            fail("That file is empty. Please choose a real resume file.");
            return;
        }
        if (file.size > maxBytes) {
            fail(`Too large (${formatSize(file.size)}). Max is ${Math.round(maxBytes / (1024 * 1024))} MB.`);
            return;
        }

        store.setUpload({ status: "reading", filename: file.name, error: null });
        title.textContent = "Reading resume…";
        setStatus("Reading resume…", "working");
        setProgress(true, 0.25);

        try {
            const buffer = await file.arrayBuffer();
            const bytes = new Uint8Array(buffer.slice(0, 8));
            const magicOk = !MAGIC[ext] || MAGIC[ext](bytes);
            if (!magicOk) {
                fail("We couldn't recognize this file's contents.");
                return;
            }
            const base64 = bytesToBase64(new Uint8Array(buffer));
            setProgress(true, 0.6);
            store.setUpload({ status: "parsing" });
            showReadyCard(file, base64);
            // Hand off to the app coordinator (which sends over WS).
            onFile({ name: file.name, data_base64: base64 });
        } catch {
            fail("Could not read the file. Please try again.");
        }
    }

    function fail(message) {
        store.setUpload({ status: "error", error: message });
        setProgress(false);
        setStatus(`✕ ${message}`, "error");
    }

    zone.addEventListener("click", () => input.click());
    zone.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            input.click();
        }
    });
    zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("drag-over");
        const file = e.dataTransfer?.files?.[0];
        if (file) void handleFile(file);
    });
    input.addEventListener("change", () => {
        if (input.files?.[0]) void handleFile(input.files[0]);
        input.value = "";
    });

    /** Server confirmed parsing (tool_completed set_resume). */
    function markDone() {
        store.setUpload({ status: "done" });
        setProgress(false);
        if (currentFile) {
            const badge = fileCard.querySelector(".file-card__state");
            if (badge) {
                badge.textContent = "✓ Ready";
                badge.classList.add("is-done");
            }
        }
        title.textContent = "Resume ready";
        hint.textContent = "Ask me to find jobs for you now.";
        setStatus(null);
    }

    /** Server rejected the resume with a typed code. */
    function markError(codeOrMessage) {
        const friendly = FRIENDLY_ERRORS[codeOrMessage] || codeOrMessage;
        store.setUpload({ status: "error", error: friendly });
        setProgress(false);
        setStatus(`✕ ${friendly}`, "error");
        title.textContent = "Drop your resume here";
        hint.textContent = "or click to browse";
        formats.textContent = "PDF · DOCX · TXT · MD";
    }

    return { markDone, markError };
}

const FRIENDLY_ERRORS = {
    unsupported_format: "This file type isn't supported. Use PDF, DOCX, TXT or MD.",
    file_too_large: "This file is too large. Please upload a smaller resume.",
    empty_file: "The uploaded file is empty.",
    no_extractable_text:
        "No selectable text could be extracted. Upload a text-based PDF or DOCX.",
    invalid_document: "We couldn't read this document. Try exporting it again.",
    invalid_resume: "Resume must be non-empty and within the size limit.",
    parse_error: "Something went wrong while parsing. Please try again.",
};

export function renderResumeStats(container, stats) {
    container.innerHTML = "";
    if (!stats) return;

    const chips = [];
    if (Number.isFinite(stats.skills_found)) chips.push(["skills", stats.skills_found]);
    if (Number.isFinite(stats.experience_items)) {
        chips.push(["experience entries", stats.experience_items]);
    }
    for (const key of ["projects_found", "projects"]) {
        if (Number.isFinite(stats[key])) chips.push(["projects", stats[key]]);
    }
    if (!chips.length) return;

    for (const [label, value] of chips) {
        const chipEl = document.createElement("span");
        chipEl.className = "stat-chip";
        const strong = document.createElement("strong");
        strong.textContent = String(value);
        chipEl.append(strong, document.createTextNode(` ${label}`));
        container.appendChild(chipEl);
    }
}

// ---- helpers -----------------------------------------------------------------

function extensionOf(name) {
    if (typeof name !== "string") return "";
    const base = name.replace(/\\/g, "/").split("/").pop() || "";
    const dot = base.lastIndexOf(".");
    return dot <= 0 ? "" : base.slice(dot).toLowerCase();
}

function formatSize(bytes) {
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${bytes} B`;
}

function bytesToBase64(bytes) {
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
}

const UPLOAD_ARROW_SVG = `
<svg viewBox="0 0 24 24" width="30" height="30">
  <path fill="currentColor" opacity=".85"
        d="M12 3 6.5 8.5l1.4 1.4L11 6.8V15h2V6.8l3.1 3.1 1.4-1.4L12 3Zm-7 14v2h14v-2h2v4H3v-4h2Z"/>
</svg>`;
