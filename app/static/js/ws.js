// WebSocket transport: seq dedup, auto-reconnect, typed envelope dispatch.
// Malformed frames are ignored; unknown event types flow through and are
// dropped by the mapper (forward compatibility).

export function connectJarvis({ sessionId, onEvent, onConnectionChange }) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let lastSeq = -1;
  let ws = null;
  let closedByUser = false;
  let reconnectTimer = null;

  function connect() {
    ws = new WebSocket(
      `${proto}://${location.host}/ws/jarvis?session_id=${encodeURIComponent(sessionId)}`
    );
    ws.onopen = () => {
      lastSeq = -1; // new server-side emitter => restart sequence tracking
      onConnectionChange?.(true);
    };
    ws.onclose = () => {
      onConnectionChange?.(false);
      if (!closedByUser) scheduleReconnect();
    };
    ws.onerror = () => {}; // close handler drives recovery
    ws.onmessage = (event) => {
      let envelope;
      try {
        envelope = JSON.parse(event.data);
      } catch {
        return; // malformed frame ignored
      }
      if (!envelope || typeof envelope.type !== "string") return;
      if (typeof envelope.seq === "number") {
        if (envelope.seq <= lastSeq) return; // duplicate / out-of-order
        lastSeq = envelope.seq;
      }
      onEvent(envelope);
    };
  }

  function scheduleReconnect() {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, 2000);
  }

  connect();

  return {
    send(type, data = {}) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      ws.send(JSON.stringify({ type, ...data }));
      return true;
    },
    close() {
      closedByUser = true;
      clearTimeout(reconnectTimer);
      ws?.close();
    },
  };
}
