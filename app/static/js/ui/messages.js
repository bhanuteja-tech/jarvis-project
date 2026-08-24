// Safe chat rendering: textContent-only DOM APIs, markdown-lite formatting
// (**bold**, `code`, bullets, numbered lists), typing indicator, status and
// error lines, optional action chips. User/JD/resume-derived text is
// untrusted — never injected as HTML.

/**
 * Append a message bubble. role: "user" | "jarvis" | "status" | "error".
 * Returns the element.
 */
export function addMessage(container, role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "status") {
    div.textContent = text;
  } else {
    for (const node of renderRich(text)) div.appendChild(node);
  }
  container.appendChild(div);
  scrollToEnd(container);
  return div;
}

/**
 * Assistant message plus grounded quick actions (e.g. after results).
 * actions: [{label, onClick}]
 */
export function addMessageWithActions(container, role, text, actions = []) {
  const bubble = addMessage(container, role, text);
  if (!actions.length) return bubble;

  const row = document.createElement("div");
  row.className = "action-row";
  for (const action of actions.slice(0, 4)) {
    if (typeof action?.label !== "string") continue;
    const chipEl = document.createElement("button");
    chipEl.type = "button";
    chipEl.className = "action-chip";
    chipEl.textContent = action.label;
    chipEl.addEventListener("click", () => action.onClick?.());
    row.appendChild(chipEl);
  }
  bubble.appendChild(row);
  return bubble;
}

/** Show a transient "Jarvis is working" indicator while a run is active. */
export function showTyping(container) {
  hideTyping(container);
  const wrap = document.createElement("div");
  wrap.className = "msg jarvis typing-msg";
  wrap.dataset.typing = "true";
  const dots = document.createElement("span");
  dots.className = "typing";
  dots.setAttribute("aria-label", "Jarvis is thinking");
  for (let i = 0; i < 3; i++) dots.appendChild(document.createElement("i"));
  wrap.appendChild(dots);
  container.appendChild(wrap);
  scrollToEnd(container);
}

export function hideTyping(container) {
  for (const el of container.querySelectorAll("[data-typing]")) el.remove();
}

// ---- markdown-lite (safe) -----------------------------------------------------

function renderRich(text) {
  const nodes = [];
  let list = null;
  let ordered = false;

  for (const rawLine of String(text ?? "").split("\n")) {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      list = null;
      continue; // collapse blank lines into paragraph spacing
    }

    const bulletMatch = line.match(/^[-•*]\s+(.*)$/);
    const numberedMatch = line.match(/^\d+[.)]\s+(.*)$/);

    if (bulletMatch || numberedMatch) {
      const wantOrdered = Boolean(numberedMatch);
      if (!list || ordered !== wantOrdered) {
        list = document.createElement(wantOrdered ? "ol" : "ul");
        nodes.push(list);
        ordered = wantOrdered;
      }
      const li = document.createElement("li");
      for (const node of inlineRich(bulletMatch ? bulletMatch[1] : numberedMatch[1])) {
        li.appendChild(node);
      }
      list.appendChild(li);
      continue;
    }

    list = null;
    const p = document.createElement("p");
    for (const node of inlineRich(line)) p.appendChild(node);
    nodes.push(p);
  }
  return nodes.length ? nodes : [document.createTextNode("")];
}

/** Inline formatting: **bold**, `code`. Everything else stays plain text. */
function inlineRich(line) {
  const nodes = [];
  const pattern = /\*\*([^*]+)\*\*|`([^`]+)`/g;
  let cursor = 0;
  let match;

  while ((match = pattern.exec(line))) {
    if (match.index > cursor) {
      nodes.push(document.createTextNode(line.slice(cursor, match.index)));
    }
    if (match[1] !== undefined) {
      const strong = document.createElement("strong");
      strong.textContent = match[1];
      nodes.push(strong);
    } else {
      const code = document.createElement("code");
      code.textContent = match[2];
      nodes.push(code);
    }
    cursor = pattern.lastIndex;
  }
  if (cursor < line.length) {
    nodes.push(document.createTextNode(line.slice(cursor)));
  }
  return nodes.length ? nodes : [document.createTextNode(line)];
}

function scrollToEnd(container) {
  requestAnimationFrame(() => {
    container.scrollTop = container.scrollHeight;
  });
}
