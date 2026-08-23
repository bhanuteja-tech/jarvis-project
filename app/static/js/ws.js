// WebSocket transport: seq dedup, reconnect, typed envelope dispatch.

export function connectJarvis({ sessionId, onEvent, onOpen, onClose }) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let lastSeq = -1;
  let ws = null;
  let closedByUser = false;

  function connect() {
    ws = new WebSocket(
      `${proto}://${location.host}/ws/jarvis?session_id=${encodeURIComponent(sessionId)}`
    );
    ws.onopen = () => { lastSeq = -1; onOpen?.(); };
    ws.onclose = () => { if (!closedByUser) setTimeout(connect, 2000); onClose?.(); };
    ws.onerror = () => {};
    ws.onmessage = (event) => {
      try {
        const envelope = JSON.parse(event.data);
        if (!envelope || !envelope.type) return;
        if (typeof envelope.seq === "number") {
          if (envelope.seq <= lastSeq) return; // duplicate/out-of-order
          lastSeq = envelope.seq;
        }
        onEvent(envelope);
      } catch { /* malformed frames ignored */ }
    };
  }

  function send(type, data = {}) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type, ...data }));
    return true;
  }

  connect();
  return { send, close: () => { closedByUser = true; ws?.close(); } };
}

export function sendEnvelope(ws, type, data = {}) {
  if (ws && typeof ws.send === "function" && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type, ...data }));
  }
}
