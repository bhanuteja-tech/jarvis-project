/**
 * ContinuousVoiceController.ts
 *
 * The single authoritative client-side controller for the JARVIS continuous voice session.
 *
 * Manages:
 *  - SpeechRecognition lifecycle with robust auto-restart loop
 *  - SpeechSynthesis (TTS) lifecycle with voice selection & keep-alive
 *  - Acoustic loop prevention: stop recognition while speaking
 *  - Barge-in / interruption: cancels TTS, increments generation, sends voice_barge_in
 *  - Generation ID invalidation to reject stale responses
 *  - Auto-listening immediately after TTS finishes
 *  - Real-time latency tracking & event history for debugging
 */

export type VoiceSessionState =
  | 'IDLE'
  | 'LISTENING'
  | 'TRANSCRIBING'
  | 'ROUTING'
  | 'EXECUTING'
  | 'OBSERVING'
  | 'SPEAKING'
  | 'INTERRUPTED'
  | 'ENDING'
  | 'ENDED'
  | 'ERROR'

export interface VoiceEventRecord {
  id: string
  time: number
  event: string
  detail?: string
}

export interface VoiceLatencies {
  speechEndToFinalMs: number
  finalToRouterMs: number
  routerToToolMs: number
  responseToTtsStartMs: number
  ttsStartToAudioMs: number
}

export interface VoiceDebugData {
  state: VoiceSessionState
  isActive: boolean
  recognitionRunning: boolean
  generation: number
  currentTranscript: string
  interimTranscript: string
  normalizedTranscript?: string
  routerType: string
  intent: string
  entity?: string
  confidence?: number
  execution?: string
  verification?: string
  activeApplication?: string
  currentDirectory?: string
  taskId?: string
  currentStep?: string
  currentTask: string
  ttsStatus: 'IDLE' | 'SPEAKING'
  errorMessage: string | null
  recentEvents: VoiceEventRecord[]
  latencies: VoiceLatencies
}

const TERMINATION_PHRASES = new Set([
  'bye jarvis',
  'goodbye jarvis',
  'bye',
  'goodbye',
  'stop listening',
  'end session',
  'terminate session',
  'exit session',
  'quit session',
])

export function cleanVoiceText(text: string): string {
  if (!text) return ''
  return text
    // Strip emojis
    .replace(/[\u{1F300}-\u{1F6FF}\u{1F900}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, '')
    // Strip markdown code blocks and inline code
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    // Strip URLs
    .replace(/https?:\/\/\S+/g, '')
    // Strip markdown links [label](url) -> label
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Strip markdown styling characters
    .replace(/[#*_~>]/g, '')
    // Normalize spaces
    .replace(/\s+/g, ' ')
    .trim()
}

export class ContinuousVoiceController {
  private state: VoiceSessionState = 'IDLE'
  private isActive: boolean = false
  private userExplicitlyStopped: boolean = false
  private isCurrentlyEnding: boolean = false
  private generation: number = 1

  private recognition: any = null
  private recognitionRunning: boolean = false
  private currentTranscript: string = ''
  private interimTranscript: string = ''
  private normalizedTranscript: string = ''
  private routerType: string = 'NONE'
  private intent: string = 'none'
  private entity: string = ''
  private confidence: number = 1.0
  private execution: string = ''
  private verification: string = ''
  private activeApplication: string = ''
  private currentDirectory: string = ''
  private taskId: string = ''
  private currentStep: string = ''
  private currentTask: string = 'idle'
  private ttsStatus: 'IDLE' | 'SPEAKING' = 'IDLE'
  private errorMessage: string | null = null

  private recentEvents: VoiceEventRecord[] = []
  private latencies: VoiceLatencies = {
    speechEndToFinalMs: 0,
    finalToRouterMs: 0,
    routerToToolMs: 0,
    responseToTtsStartMs: 0,
    ttsStartToAudioMs: 0,
  }

  private speechEndTimestamp: number | null = null
  private finalTranscriptTimestamp: number | null = null
  private responseTimestamp: number | null = null
  private ttsStartTimestamp: number | null = null

  private restartTimeout: any = null
  private keepAliveInterval: any = null

  private sendVoiceTurnFn: ((text: string, generation: number) => void) | null = null
  private sendVoiceBargeInFn: ((generation: number) => void) | null = null

  private stateSubscribers: Set<(state: VoiceSessionState) => void> = new Set()
  private debugSubscribers: Set<(debugData: VoiceDebugData) => void> = new Set()

  constructor() {
    this.initSpeechRecognition()
  }

  private initSpeechRecognition(): void {
    // Prime speech synthesis voices early
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices()
      }
      window.speechSynthesis.getVoices()
    }
  }

  public updateDiagnosticData(data: Partial<VoiceDebugData>): void {
    if (data.routerType !== undefined) this.routerType = data.routerType
    if (data.currentTask !== undefined) this.currentTask = data.currentTask
    if (data.normalizedTranscript !== undefined) this.normalizedTranscript = data.normalizedTranscript
    if (data.intent !== undefined) this.intent = data.intent
    if (data.entity !== undefined) this.entity = data.entity
    if (data.confidence !== undefined) this.confidence = data.confidence
    if (data.execution !== undefined) this.execution = data.execution
    if (data.verification !== undefined) this.verification = data.verification
    if (data.activeApplication !== undefined) this.activeApplication = data.activeApplication
    if (data.currentDirectory !== undefined) this.currentDirectory = data.currentDirectory
    if (data.taskId !== undefined) this.taskId = data.taskId
    if (data.currentStep !== undefined) this.currentStep = data.currentStep
    this.notifySubscribers()
  }

  public setSendFunctions(
    sendVoiceTurn: (text: string, generation: number) => void,
    sendVoiceBargeIn: (generation: number) => void
  ): void {
    this.sendVoiceTurnFn = sendVoiceTurn
    this.sendVoiceBargeInFn = sendVoiceBargeIn
  }

  public subscribe(fn: (state: VoiceSessionState) => void): () => void {
    this.stateSubscribers.add(fn)
    fn(this.state)
    return () => this.stateSubscribers.delete(fn)
  }

  public subscribeDebug(fn: (debugData: VoiceDebugData) => void): () => void {
    this.debugSubscribers.add(fn)
    fn(this.getDebugData())
    return () => this.debugSubscribers.delete(fn)
  }

  public getState(): VoiceSessionState {
    return this.state
  }

  public getGeneration(): number {
    return this.generation
  }

  public getDebugData(): VoiceDebugData {
    return {
      state: this.state,
      isActive: this.isActive,
      recognitionRunning: this.recognitionRunning,
      generation: this.generation,
      currentTranscript: this.currentTranscript,
      interimTranscript: this.interimTranscript,
      normalizedTranscript: this.normalizedTranscript,
      routerType: this.routerType,
      intent: this.intent,
      entity: this.entity,
      confidence: this.confidence,
      execution: this.execution,
      verification: this.verification,
      activeApplication: this.activeApplication,
      currentDirectory: this.currentDirectory,
      taskId: this.taskId,
      currentStep: this.currentStep,
      currentTask: this.currentTask,
      ttsStatus: this.ttsStatus,
      errorMessage: this.errorMessage,
      recentEvents: [...this.recentEvents],
      latencies: { ...this.latencies },
    }
  }

  private setState(newState: VoiceSessionState): void {
    this.state = newState
    this.notifySubscribers()
  }

  private notifySubscribers(): void {
    const data = this.getDebugData()
    this.stateSubscribers.forEach((fn) => {
      try {
        fn(this.state)
      } catch (err) {
        console.error('Error in state subscriber:', err)
      }
    })
    this.debugSubscribers.forEach((fn) => {
      try {
        fn(data)
      } catch (err) {
        console.error('Error in debug subscriber:', err)
      }
    })
  }

  private addEvent(name: string, detail?: string): void {
    const record: VoiceEventRecord = {
      id: `ev-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      time: Date.now(),
      event: name,
      detail,
    }
    this.recentEvents.unshift(record)
    if (this.recentEvents.length > 25) {
      this.recentEvents.pop()
    }
    this.notifySubscribers()
  }

  // --------------------------------------------------------------------------
  // Session Start / Stop
  // --------------------------------------------------------------------------

  public async startSession(): Promise<boolean> {
    if (typeof window === 'undefined') return false

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition

    if (!SpeechRecognition) {
      this.errorMessage =
        'SpeechRecognition API is not supported in this browser. Please use Chrome or Edge.'
      this.setState('ERROR')
      this.addEvent('ERROR', 'No SpeechRecognition support')
      return false
    }

    // Request microphone permission cleanly
    try {
      if (navigator.mediaDevices?.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        // Close prompt stream immediately since SpeechRecognition opens its own
        stream.getTracks().forEach((t) => t.stop())
      }
    } catch (err: any) {
      console.warn('Microphone permission query failed or denied:', err)
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        this.errorMessage = 'Microphone permission is required for voice mode.'
        this.setState('ERROR')
        this.addEvent('ERROR', 'Microphone permission denied')
        return false
      }
    }

    this.userExplicitlyStopped = false
    this.isCurrentlyEnding = false
    this.isActive = true
    this.errorMessage = null
    this.generation = 1
    this.currentTranscript = ''
    this.interimTranscript = ''

    console.log('VOICE SESSION STARTED')
    this.addEvent('SESSION_START')

    return this.initAndStartRecognition()
  }

  public stopSession(): void {
    console.log('STOPPING VOICE SESSION')
    this.userExplicitlyStopped = true
    this.isActive = false
    this.isCurrentlyEnding = false

    if (this.restartTimeout) {
      clearTimeout(this.restartTimeout)
      this.restartTimeout = null
    }
    if (this.keepAliveInterval) {
      clearInterval(this.keepAliveInterval)
      this.keepAliveInterval = null
    }

    this.stopRecognitionCleanly()

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
    this.ttsStatus = 'IDLE'
    this.setState('ENDED')
    this.addEvent('SESSION_END')
  }

  // --------------------------------------------------------------------------
  // Recognition Lifecycle
  // --------------------------------------------------------------------------

  private initAndStartRecognition(): boolean {
    if (this.recognition) {
      try {
        this.recognition.onstart = null
        this.recognition.onaudiostart = null
        this.recognition.onspeechstart = null
        this.recognition.onresult = null
        this.recognition.onspeechend = null
        this.recognition.onaudioend = null
        this.recognition.onerror = null
        this.recognition.onend = null
        this.recognition.abort()
      } catch {
        // ignore
      }
      this.recognition = null
      this.recognitionRunning = false
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition

    if (!SpeechRecognition) return false

    try {
      const rec = new SpeechRecognition()
      rec.continuous = true
      rec.interimResults = true
      rec.lang = 'en-US'
      rec.maxAlternatives = 1

      rec.onstart = () => {
        this.recognitionRunning = true
        this.addEvent('START')
        this.setState('LISTENING')
        console.log('RECOGNITION STARTED | STATE = LISTENING')
      }

      rec.onaudiostart = () => {
        this.addEvent('AUDIOSTART')
      }

      rec.onspeechstart = () => {
        this.addEvent('SPEECHSTART')
        // CRITICAL: If JARVIS is currently speaking when user speaks, trigger barge-in!
        if (this.state === 'SPEAKING' || this.ttsStatus === 'SPEAKING') {
          console.log('USER SPEECH DETECTED DURING TTS -> TRIGGERING BARGE-IN')
          this.bargeIn()
        }
      }

      rec.onresult = (event: any) => {
        this.addEvent('RESULT')
        let finalChunk = ''
        let interimChunk = ''

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const item = event.results[i]
          if (item.isFinal) {
            finalChunk += item[0].transcript
          } else {
            interimChunk += item[0].transcript
          }
        }

        if (interimChunk) {
          this.interimTranscript = interimChunk
          if (this.state === 'LISTENING') {
            this.setState('TRANSCRIBING')
          }
        }

        if (finalChunk.trim()) {
          const finalTrimmed = finalChunk.trim()
          this.currentTranscript = finalTrimmed
          this.interimTranscript = ''

          const now = Date.now()
          if (this.speechEndTimestamp) {
            this.latencies.speechEndToFinalMs = Math.max(0, now - this.speechEndTimestamp)
          }
          this.finalTranscriptTimestamp = now

          console.log('VOICE TRANSCRIPT:', finalTrimmed)
          this.handleFinalTranscript(finalTrimmed)
        }
      }

      rec.onspeechend = () => {
        this.speechEndTimestamp = Date.now()
        this.addEvent('SPEECHEND')
      }

      rec.onaudioend = () => {
        this.addEvent('AUDIOEND')
      }

      rec.onerror = (event: any) => {
        this.addEvent('ERROR', event.error)
        console.warn('SpeechRecognition error:', event.error)

        if (event.error === 'no-speech') {
          // Normal timeout when silence; restart guarded
          if (this.isActive && !this.userExplicitlyStopped && this.state !== 'SPEAKING') {
            this.scheduleRestart(100)
          }
        } else if (event.error === 'not-allowed') {
          this.errorMessage = 'Microphone permission is required for voice mode.'
          this.setState('ERROR')
          this.stopSession()
        } else if (event.error === 'audio-capture') {
          this.errorMessage = 'No microphone was detected.'
          this.setState('ERROR')
          this.stopSession()
        } else if (event.error === 'network') {
          if (this.isActive && !this.userExplicitlyStopped) {
            this.scheduleRestart(400)
          }
        }
      }

      rec.onend = () => {
        this.recognitionRunning = false
        this.addEvent('END')
        // CRITICAL REQUIREMENT #2: Robust restart loop when onend fires
        if (
          this.isActive &&
          !this.userExplicitlyStopped &&
          !this.isCurrentlyEnding &&
          this.state !== 'SPEAKING'
        ) {
          this.scheduleRestart(150)
        }
      }

      this.recognition = rec
      this.recognition.start()
      return true
    } catch (err) {
      console.error('Failed to create/start SpeechRecognition:', err)
      this.errorMessage = 'Failed to initialize microphone.'
      this.setState('ERROR')
      return false
    }
  }

  private scheduleRestart(delayMs: number): void {
    if (this.restartTimeout) {
      clearTimeout(this.restartTimeout)
      this.restartTimeout = null
    }

    this.restartTimeout = setTimeout(() => {
      this.restartTimeout = null
      if (
        this.isActive &&
        !this.userExplicitlyStopped &&
        !this.isCurrentlyEnding &&
        this.state !== 'SPEAKING'
      ) {
        console.log('RESTARTING RECOGNITION (continuous voice loop)...')
        this.initAndStartRecognition()
      }
    }, delayMs)
  }

  private stopRecognitionCleanly(): void {
    if (this.recognition) {
      try {
        this.recognition.onend = null
        this.recognition.stop()
      } catch {
        // ignore
      }
      this.recognitionRunning = false
    }
  }

  private startRecognition(): void {
    if (this.isActive && !this.userExplicitlyStopped && !this.isCurrentlyEnding) {
      this.initAndStartRecognition()
    }
  }

  // --------------------------------------------------------------------------
  // Voice Turn & Router
  // --------------------------------------------------------------------------

  private handleFinalTranscript(transcript: string): void {
    const cleanedLower = transcript
      .toLowerCase()
      .replace(/[^\w\s]/g, '')
      .trim()

    // Determine router type
    if (TERMINATION_PHRASES.has(cleanedLower)) {
      this.routerType = 'SESSION_TERMINATION'
      this.intent = 'end_session'
      this.currentTask = 'session.terminate'
      this.isCurrentlyEnding = true
      this.setState('ENDING')
    } else {
      // Backend is authoritative. Mark as AUTONOMOUS_AGENT while routing:
      this.routerType = 'AUTONOMOUS_AGENT'
      this.intent = 'evaluating'
      this.currentTask = 'agent.reasoning'
      this.setState('ROUTING')
    }

    const now = Date.now()
    if (this.finalTranscriptTimestamp) {
      this.latencies.finalToRouterMs = Math.max(0, now - this.finalTranscriptTimestamp)
    }

    if (this.sendVoiceTurnFn) {
      console.log(`VOICE TURN SENT (generation=${this.generation})`)
      this.addEvent('VOICE_TURN_SENT', transcript)
      this.sendVoiceTurnFn(transcript, this.generation)
      this.setState('EXECUTING')
    } else {
      console.warn('sendVoiceTurnFn not attached to ContinuousVoiceController!')
    }
  }

  public setObserving(): void {
    if (this.isActive) {
      this.setState('OBSERVING')
      this.addEvent('OBSERVING', 'Inspecting environment state')
    }
  }

  public handleAgentCompleted(): void {
    if (
      this.isActive &&
      (this.state === 'EXECUTING' || this.state === 'OBSERVING' || this.state === 'ROUTING') &&
      this.ttsStatus === 'IDLE'
    ) {
      console.log('ContinuousVoiceController: Agent completed with TTS idle; returning to LISTENING')
      this.setState('LISTENING')
      this.startRecognition()
    }
  }

  // --------------------------------------------------------------------------
  // Assistant Response & TTS Execution
  // --------------------------------------------------------------------------

  public handleAssistantResponse(payload: {
    text: string
    generation?: number
    isAcknowledgment?: boolean
    isTermination?: boolean
  }): void {
    // Drop responses from invalidated generations (Barge-in protection)
    if (payload.generation !== undefined && payload.generation !== this.generation) {
      console.warn(
        `DROPPING STALE VOICE RESPONSE: got gen ${payload.generation}, active is ${this.generation}`
      )
      this.addEvent('STALE_RESPONSE_DROPPED', `gen ${payload.generation}`)
      return
    }

    this.responseTimestamp = Date.now()
    const rawText = payload.text || ''
    const cleanedText = cleanVoiceText(rawText)

    if (!cleanedText) {
      // Nothing audible, return to listening
      this.setState('LISTENING')
      this.startRecognition()
      return
    }

    this.ttsStatus = 'SPEAKING'
    this.setState('SPEAKING')
    this.addEvent('TTS_START', cleanedText.slice(0, 30))

    // CRITICAL REQUIREMENT #7: Cleanly stop recognition while JARVIS speaks
    // so the microphone does NOT transcribe JARVIS's own voice!
    this.stopRecognitionCleanly()

    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      console.warn('SpeechSynthesis not available in this window')
      this.ttsStatus = 'IDLE'
      this.setState('LISTENING')
      this.startRecognition()
      return
    }

    try {
      window.speechSynthesis.cancel()

      const utterance = new SpeechSynthesisUtterance(cleanedText)
      utterance.rate = 1.05
      utterance.pitch = 1.0

      // Pick high-quality English voice
      const voices = window.speechSynthesis.getVoices()
      const preferred = voices.find(
        (v) =>
          v.lang.startsWith('en') &&
          (v.name.includes('Natural') ||
            v.name.includes('Google') ||
            v.name.includes('David') ||
            v.name.includes('Zira') ||
            v.name.includes('Samantha'))
      )
      if (preferred) {
        utterance.voice = preferred
      }

      utterance.onstart = () => {
        this.ttsStartTimestamp = Date.now()
        if (this.responseTimestamp) {
          this.latencies.responseToTtsStartMs = Math.max(
            0,
            this.ttsStartTimestamp - this.responseTimestamp
          )
        }
        console.log('TTS STARTED | TEXT:', cleanedText)
        this.addEvent('TTS_PLAYING')

        // Chrome keep-alive: restart resume() every 4s to prevent silence pause bug
        if (this.keepAliveInterval) clearInterval(this.keepAliveInterval)
        this.keepAliveInterval = setInterval(() => {
          if (window.speechSynthesis.speaking) {
            window.speechSynthesis.pause()
            window.speechSynthesis.resume()
          }
        }, 4000)
      }

      utterance.onend = () => {
        if (this.keepAliveInterval) {
          clearInterval(this.keepAliveInterval)
          this.keepAliveInterval = null
        }
        console.log('TTS FINISHED')
        this.ttsStatus = 'IDLE'
        this.addEvent('TTS_FINISHED')

        if (payload.isTermination) {
          this.setState('ENDED')
          this.stopSession()
        } else {
          // CRITICAL REQUIREMENT #10: AUTO LISTEN AFTER EVERY RESPONSE
          console.log('AUTOMATICALLY LISTENING AGAIN...')
          this.setState('LISTENING')
          this.startRecognition()
        }
      }

      utterance.onerror = (e) => {
        if (this.keepAliveInterval) {
          clearInterval(this.keepAliveInterval)
          this.keepAliveInterval = null
        }
        console.warn('TTS onerror:', e)
        this.ttsStatus = 'IDLE'
        this.addEvent('TTS_ERROR', String(e.error))

        if (this.isActive && !this.userExplicitlyStopped) {
          this.setState('LISTENING')
          this.startRecognition()
        }
      }

      window.speechSynthesis.speak(utterance)
    } catch (err) {
      console.error('SpeechSynthesis speak failed:', err)
      this.ttsStatus = 'IDLE'
      this.setState('LISTENING')
      this.startRecognition()
    }
  }

  // --------------------------------------------------------------------------
  // Barge-In / Interruption (CRITICAL REQUIREMENT #8)
  // --------------------------------------------------------------------------

  public bargeIn(): void {
    console.log('BARGE-IN TRIGGERED: Cancelling TTS & invalidating generation')
    this.addEvent('BARGE_IN', `gen ${this.generation}`)

    // 1. Cancel TTS immediately
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
    if (this.keepAliveInterval) {
      clearInterval(this.keepAliveInterval)
      this.keepAliveInterval = null
    }
    this.ttsStatus = 'IDLE'

    // 2. Notify backend of cancellation
    if (this.sendVoiceBargeInFn) {
      this.sendVoiceBargeInFn(this.generation)
    }

    // 3. Invalidate active generation ID
    this.generation += 1
    this.setState('INTERRUPTED')

    // 4. Immediately listen for new command
    setTimeout(() => {
      if (this.isActive && !this.userExplicitlyStopped) {
        this.setState('LISTENING')
        this.startRecognition()
      }
    }, 150)
  }
}

// Authoritative Singleton Instance
export const continuousVoiceController = new ContinuousVoiceController()
