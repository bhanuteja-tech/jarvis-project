// Voice: Web Speech STT + TTS with stop/cancel and graceful degradation.

export function sttSupported() {
  return typeof window !== "undefined" &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export function ttsSupported() {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function startListening({ onResult, onInterim, onStart }) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return null;
  const recognition = new Recognition();
  recognition.lang = "en-US";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => onStart?.();
  recognition.onresult = (event) => {
    let interim = "";
    let final_text = "";
    for (const result of event.results) {
      if (result.isFinal) final_text += result[0].transcript;
      else interim += result[0].transcript;
    }
    if (interim && onInterim) onInterim(interim);
    if (final_text && onResult) onResult(final_text.trim());
  };
  recognition.onerror = () => {};
  recognition.start();
  return recognition;
}

export function speak(text, { enabled }) {
  if (!enabled || !ttsSupported() || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.05;
  utterance.pitch = 1.0;
  window.speechSynthesis.speak(utterance);
}

export function cancelSpeak() {
  if (ttsSupported()) window.speechSynthesis.cancel();
}
