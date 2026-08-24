// Voice: Web Speech STT + TTS with stop/cancel and graceful degradation.
// No server-side audio; browser capability only. PII never leaves the page:
// transcripts go straight to the chat input path, never to storage.

export function sttSupported() {
  return (
    typeof window !== "undefined" &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition)
  );
}

export function ttsSupported() {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/**
 * Start one listening session.
 * @param {object} opts
 * @param {(text: string) => void} [opts.onFinal]    final transcript
 * @param {(text: string) => void} [opts.onInterim]  interim transcript
 * @param {() => void} [opts.onStart]
 * @param {() => void} [opts.onEnd]                  session ended (any reason)
 * @param {string} [opts.lang]                       BCP-47, default en-US
 * @returns {{stop: () => void}|null}                null when unsupported
 */
export function startListening({
  onFinal,
  onInterim,
  onStart,
  onEnd,
  lang = "en-US",
} = {}) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return null;

  const recognition = new Recognition();
  recognition.lang = lang;
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  let finished = false;

  recognition.onstart = () => onStart?.();
  recognition.onresult = (event) => {
    let interim = "";
    let finalText = "";
    for (const result of event.results) {
      if (result.isFinal) finalText += result[0].transcript;
      else interim += result[0].transcript;
    }
    if (interim) onInterim?.(interim.trim());
    if (finalText.trim()) {
      finished = true;
      onFinal?.(finalText.trim());
    }
  };
  recognition.onerror = () => {
    // Errors end the session quietly; UI falls back to typing.
  };
  recognition.onend = () => {
    onEnd?.();
    if (!finished) onFinal?.(""); // empty final => treat as cancelled/empty
  };

  try {
    recognition.start();
  } catch {
    return null; // already-started or blocked by permissions
  }

  return {
    stop() {
      try {
        recognition.stop();
      } catch {
        /* ignore */
      }
    },
  };
}

/**
 * Speak text when enabled; cancels any current utterance first.
 * @param {object} opts
 * @param {boolean} opts.enabled
 * @param {() => void} [opts.onStart]
 * @param {() => void} [opts.onEnd]  fires on natural end and on cancel
 */
export function speak(text, { enabled, onStart, onEnd } = {}) {
  if (!ttsSupported()) return;
  window.speechSynthesis.cancel();
  if (!enabled || !text) return;

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.05;
  utterance.pitch = 1.0;
  utterance.onstart = () => onStart?.();
  utterance.onend = () => onEnd?.();
  utterance.onerror = () => onEnd?.();
  window.speechSynthesis.speak(utterance);
}

/** Cancel current speech. onEnd handlers fire via utterance.onend/onerror. */
export function cancelSpeak() {
  if (ttsSupported()) window.speechSynthesis.cancel();
}
