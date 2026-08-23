// Voice interface over the same text pipeline (browser Web Speech APIs only).

export function sttSupported() {
  return typeof window !== "undefined" &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export function startListening(onText) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return null;
  const recognition = new Recognition();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    if (transcript && onText) onText(transcript);
  };
  recognition.start();
  return recognition;
}

export function ttsSupported() {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function speak(text, { enabled }) {
  if (!enabled || !ttsSupported() || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.05;
  window.speechSynthesis.speak(utterance);
}
