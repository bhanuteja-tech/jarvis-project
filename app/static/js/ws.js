// WebSocket transport with reconnect + typed envelope dispatch.

export function connectJarvis({ sessionId, onEvent, onOpen, onClose }) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(
    `${proto}://${location.host}/ws/jarvis?session_id=${encodeURIComponent(sessionId)}`
  );

  ws.onopen = () => onOpen && onOpen();
  ws.onclose = () => onClose && onClose();
  ws.onerror = () => {};
  ws.onmessage = (event) => {
    try {
      const envelope = JSON.parse(event.data);
      if (envelope && envelope.type) onEvent(envelope);
    } catch { /* ignore malformed frames */ }
  };
  return ws;
}

export function sendEnvelope(ws, type, data = {}) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type, ...data }));
}
