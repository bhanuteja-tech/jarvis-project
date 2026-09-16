/**
 * Browser Web Speech API helper (SpeechSynthesis & SpeechRecognition).
 */

export interface SpeechController {
  speak: (text: string, onStart?: () => void, onEnd?: () => void) => boolean
  stopSpeaking: () => void
  isSpeaking: () => boolean
  isRecognitionSupported: () => boolean
}

export function cleanTextForSpeech(text: string): string {
  if (!text) return ''
  return text
    .replace(/```[\s\S]*?```/g, '') // remove code blocks
    .replace(/`([^`]+)`/g, '$1')     // remove inline code
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // link formatting
    .replace(/[#*_-]/g, ' ')         // markdown symbols
    .replace(/\s+/g, ' ')
    .trim()
}

export function speakText(
  text: string,
  onStart?: () => void,
  onEnd?: () => void
): boolean {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    return false
  }

  stopSpeaking()

  const clean = cleanTextForSpeech(text)
  if (!clean) return false

  try {
    const utterance = new SpeechSynthesisUtterance(clean)
    utterance.rate = 1.0
    utterance.pitch = 1.0

    const voices = window.speechSynthesis.getVoices()
    const englishVoice = voices.find(
      (v) =>
        v.lang.startsWith('en') &&
        (v.name.includes('Natural') ||
          v.name.includes('Google') ||
          v.name.includes('Samantha') ||
          v.name.includes('Daniel'))
    )
    if (englishVoice) {
      utterance.voice = englishVoice
    }

    utterance.onstart = () => {
      onStart?.()
    }

    utterance.onend = () => {
      onEnd?.()
    }

    utterance.onerror = (e) => {
      console.warn('Speech synthesis error:', e)
      onEnd?.()
    }

    window.speechSynthesis.speak(utterance)
    return true
  } catch (err) {
    console.error('Failed to initiate speech synthesis:', err)
    return false
  }
}

export function stopSpeaking(): void {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
}

export function isSpeaking(): boolean {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    return false
  }
  return window.speechSynthesis.speaking
}

export function isSpeechRecognitionSupported(): boolean {
  if (typeof window === 'undefined') return false
  return 'SpeechRecognition' in window || 'webkitSpeechRecognition' in window
}
