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

let currentAudio = null;
let currentAudioUrl = null;

function stopCurrentAudio() {
  if (currentAudio) {
    try {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    } catch {
      /* ignore */
    }
    currentAudio = null;
  }
  if (currentAudioUrl) {
    try {
      URL.revokeObjectURL(currentAudioUrl);
    } catch {
      /* ignore */
    }
    currentAudioUrl = null;
  }
}

/**
 * Speak text when enabled; cancels any current utterance first.
 * Attempts ElevenLabs high-fidelity TTS API first, falling back to Web Speech synthesis.
 * @param {string} text
 * @param {object} opts
 * @param {boolean} opts.enabled
 * @param {() => void} [opts.onStart]
 * @param {() => void} [opts.onEnd]  fires on natural end and on cancel
 */
export async function speak(text, { enabled, onStart, onEnd } = {}) {
  cancelSpeak();
  if (!enabled || !text) return;

  // 1. Try ElevenLabs API endpoint first
  try {
    const res = await fetch("/api/voice/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    if (res.ok) {
      const blob = await res.blob();
      currentAudioUrl = URL.createObjectURL(blob);
      const audio = new Audio(currentAudioUrl);
      currentAudio = audio;

      audio.onplay = () => onStart?.();
      audio.onended = () => {
        stopCurrentAudio();
        onEnd?.();
      };
      audio.onerror = () => {
        stopCurrentAudio();
        speakWebSpeech(text, { enabled, onStart, onEnd });
      };

      await audio.play();
      return;
    }
  } catch (err) {
    // ElevenLabs API unavailable or failed; fall back to Web Speech
  }

  // 2. Fallback to Web Speech Synthesis
  speakWebSpeech(text, { enabled, onStart, onEnd });
}

function speakWebSpeech(text, { enabled, onStart, onEnd } = {}) {
  if (!ttsSupported()) {
    onEnd?.();
    return;
  }
  if (!enabled || !text) return;

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.05;
  utterance.pitch = 1.0;
  utterance.onstart = () => onStart?.();
  utterance.onend = () => onEnd?.();
  utterance.onerror = () => onEnd?.();
  window.speechSynthesis.speak(utterance);
}

/** Cancel current speech (both ElevenLabs audio and Web Speech). */
export function cancelSpeak() {
  stopCurrentAudio();
  if (ttsSupported()) {
    try {
      window.speechSynthesis.cancel();
    } catch {
      /* ignore */
    }
  }
}

