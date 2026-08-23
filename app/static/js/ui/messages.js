// Safe chat rendering: textContent only, simple bullet/paragraph handling.

export function addMessage(container, role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  for (const node of renderRich(text)) div.appendChild(node);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function renderRich(text) {
  const nodes = [];
  let list = null;
  for (const rawLine of String(text).split("\n")) {
    const line = rawLine.trimEnd();
    if (!line.trim()) { nodes.push(document.createElement("br")); continue; }
    if (/^[•\-*]\s+/.test(line)) {
      if (!list) { list = document.createElement("ul"); nodes.push(list); }
      const li = document.createElement("li");
      li.textContent = line.replace(/^[•\-*]\s+/, "");
      list.appendChild(li);
      continue;
    }
    list = null;
    const p = document.createElement("p");
    p.style.margin = "0 0 4px";
    p.textContent = line;
    nodes.push(p);
  }
  return nodes.length ? nodes : [document.createTextNode("")];
}
