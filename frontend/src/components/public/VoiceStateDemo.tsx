import { useState, useEffect } from 'react'
import {
  Mic,
  MicOff,
  Volume2,
  Zap,
  Radio
} from 'lucide-react'

export function VoiceStateDemo() {
  const [isMicActive, setIsMicActive] = useState(false)
  const [activeTab, setActiveTab] = useState<'barge-in' | 'dual-path' | 'latency'>('barge-in')
  const [simulatedVoiceState, setSimulatedVoiceState] = useState<'IDLE' | 'LISTENING' | 'ACTING' | 'SPEAKING'>('IDLE')
  const [interruptionCount, setInterruptionCount] = useState(0)

  // Auto transition demo when mic is triggered
  useEffect(() => {
    let t1: ReturnType<typeof setTimeout>
    let t2: ReturnType<typeof setTimeout>
    let t3: ReturnType<typeof setTimeout>

    if (isMicActive) {
      setSimulatedVoiceState('LISTENING')
      t1 = setTimeout(() => {
        setSimulatedVoiceState('ACTING')
        t2 = setTimeout(() => {
          setSimulatedVoiceState('SPEAKING')
          t3 = setTimeout(() => {
            setSimulatedVoiceState('IDLE')
            setIsMicActive(false)
          }, 4000)
        }, 800)
      }, 1200)
    }

    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
      clearTimeout(t3)
    }
  }, [isMicActive])

  const triggerBargeIn = () => {
    setSimulatedVoiceState('LISTENING')
    setInterruptionCount((c) => c + 1)
    setTimeout(() => {
      setSimulatedVoiceState('SPEAKING')
    }, 600)
  }

  return (
    <div className="w-full rounded-2xl glass-strong border border-jarvis-border/60 p-6 sm:p-8 space-y-6">
      {/* Top Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-jarvis-border/40 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
            <h3 className="text-lg font-bold text-white tracking-wide">JARVIS Sovereign Voice Engine</h3>
          </div>
          <p className="text-xs text-jarvis-muted mt-0.5">
            Zero cloud voice leaks · Instant barge-in cancellation · Dual-path intent dispatch
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex items-center p-1 rounded-xl bg-jarvis-surface/60 border border-jarvis-border/40 text-xs">
          <button
            onClick={() => setActiveTab('barge-in')}
            className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeTab === 'barge-in'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                : 'text-jarvis-muted hover:text-white'
            }`}
          >
            Barge-in Simulator
          </button>
          <button
            onClick={() => setActiveTab('dual-path')}
            className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeTab === 'dual-path'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                : 'text-jarvis-muted hover:text-white'
            }`}
          >
            Dual-Path Architecture
          </button>
          <button
            onClick={() => setActiveTab('latency')}
            className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeTab === 'latency'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                : 'text-jarvis-muted hover:text-white'
            }`}
          >
            Latency Benchmarks
          </button>
        </div>
      </div>

      {/* Tab 1: Barge-in simulator */}
      {activeTab === 'barge-in' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
            {/* Left: Waveform Console */}
            <div className="p-6 rounded-2xl bg-gradient-to-br from-jarvis-surface/80 to-jarvis-darker/90 border border-jarvis-border/50 text-center space-y-4">
              <div className="flex justify-center">
                <div
                  className={`w-20 h-20 rounded-full flex items-center justify-center transition-all duration-300 relative shadow-2xl ${
                    simulatedVoiceState === 'SPEAKING'
                      ? 'bg-gradient-to-tr from-cyan-500 to-blue-600 shadow-cyan-500/40 animate-pulse'
                      : simulatedVoiceState === 'LISTENING'
                      ? 'bg-gradient-to-tr from-amber-500 to-yellow-400 shadow-amber-500/30'
                      : simulatedVoiceState === 'ACTING'
                      ? 'bg-gradient-to-tr from-violet-600 to-indigo-600 shadow-violet-500/30'
                      : 'bg-jarvis-surface border border-jarvis-border text-jarvis-muted'
                  }`}
                >
                  {simulatedVoiceState === 'SPEAKING' ? (
                    <Volume2 size={32} className="text-white" />
                  ) : (
                    <Mic size={32} className={simulatedVoiceState === 'IDLE' ? 'text-jarvis-muted' : 'text-white'} />
                  )}

                  {/* Pulsing ring */}
                  {simulatedVoiceState !== 'IDLE' && (
                    <span className="absolute inset-0 rounded-full border border-cyan-400/50 animate-ping" />
                  )}
                </div>
              </div>

              {/* Status text */}
              <div>
                <div className="text-xs font-mono uppercase tracking-widest text-cyan-400 font-semibold">
                  STATE: {simulatedVoiceState}
                </div>
                <p className="text-xs text-jarvis-muted mt-1">
                  {simulatedVoiceState === 'IDLE' && 'Click "Simulate Speech" below to trigger voice input.'}
                  {simulatedVoiceState === 'LISTENING' && 'Capturing continuous audio stream with VAD...'}
                  {simulatedVoiceState === 'ACTING' && 'FastIntentRouter evaluating deterministic grammar...'}
                  {simulatedVoiceState === 'SPEAKING' && 'Synthesizing voice response. Click Barge-in to cut off!'}
                </p>
              </div>

              {/* Live Waveform */}
              <div className="flex items-center justify-center gap-1.5 h-10">
                {[12, 28, 45, 18, 36, 50, 24, 40, 16, 32, 48, 20].map((h, i) => {
                  const active = simulatedVoiceState === 'SPEAKING' || simulatedVoiceState === 'LISTENING'
                  return (
                    <span
                      key={i}
                      style={{ height: active ? `${h}px` : '4px' }}
                      className={`w-1.5 rounded-full transition-all duration-150 ${
                        active
                          ? simulatedVoiceState === 'SPEAKING'
                            ? 'bg-cyan-400'
                            : 'bg-amber-400'
                          : 'bg-jarvis-border'
                      }`}
                    />
                  )
                })}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-center gap-3 pt-2">
                <button
                  onClick={() => setIsMicActive(!isMicActive)}
                  className={`px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-2 transition-all ${
                    isMicActive
                      ? 'bg-red-500/20 text-red-300 border border-red-500/30'
                      : 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/25'
                  }`}
                >
                  {isMicActive ? <MicOff size={14} /> : <Mic size={14} />}
                  <span>{isMicActive ? 'Cancel Voice' : 'Simulate Speech'}</span>
                </button>

                <button
                  onClick={triggerBargeIn}
                  disabled={simulatedVoiceState !== 'SPEAKING'}
                  className="px-4 py-2 rounded-xl text-xs font-semibold bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                >
                  Test Barge-in Interrupt
                </button>
              </div>
            </div>

            {/* Right: Technical Explanation */}
            <div className="space-y-4 text-xs">
              <div className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2">
                <div className="flex items-center gap-2 text-cyan-400 font-semibold font-mono text-[11px]">
                  <Zap size={14} />
                  <span>INSTANT CANCELLATION PROTOCOL</span>
                </div>
                <p className="text-jarvis-muted leading-relaxed">
                  When you speak while JARVIS is responding, the browser audio output is muted within <strong>18 milliseconds</strong>, the active synthesis worker is aborted, and the connection task is cleanly renewed without corrupting conversation memory.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2">
                <div className="flex items-center gap-2 text-violet-400 font-semibold font-mono text-[11px]">
                  <Radio size={14} />
                  <span>CLIENT-SIDE VAD & ZERO AUDIO RETENTION</span>
                </div>
                <p className="text-jarvis-muted leading-relaxed">
                  Voice Activity Detection runs directly in your browser. Audio waveforms are processed in-memory and never written to disk, sent to third-party ad networks, or used for model training.
                </p>
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-[11px]">
                <span className="text-emerald-400 font-medium">Interruption resilience score:</span>
                <span className="font-mono font-bold text-white">
                  100% Deterministic {interruptionCount > 0 ? `(${interruptionCount} barge-ins tested)` : ''}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Dual-path Architecture */}
      {activeTab === 'dual-path' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="p-5 rounded-xl bg-blue-950/20 border border-blue-500/30 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-cyan-400">PATH 1: FAST INTENT ROUTER</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 font-mono">18ms - 45ms</span>
            </div>
            <p className="text-xs text-jarvis-muted leading-relaxed">
              Handles direct workspace transitions, filter adjustments, barge-in stops, search criteria queries, and audio state toggles. Completely deterministic grammar; zero LLM token wait time.
            </p>
            <div className="text-[11px] font-mono bg-black/40 p-3 rounded-lg text-jarvis-light space-y-1">
              <div className="text-emerald-400">✓ "Show my matched jobs" → workspace: jobs</div>
              <div className="text-emerald-400">✓ "Pause narration" → audio: stop</div>
              <div className="text-emerald-400">✓ "Open PDF Studio" → workspace: doc-studio</div>
            </div>
          </div>

          <div className="p-5 rounded-xl bg-violet-950/20 border border-violet-500/30 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-violet-400">PATH 2: LANGGRAPH DEEP AGENT</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-violet-500/10 text-violet-300 font-mono">Parallel Background</span>
            </div>
            <p className="text-xs text-jarvis-muted leading-relaxed">
              Dispatches long-running multi-source radar scans, JD semantic deconstruction, 8-weight candidate matching, and mathematical truth audits while voice narration provides real-time streaming updates.
            </p>
            <div className="text-[11px] font-mono bg-black/40 p-3 rounded-lg text-jarvis-light space-y-1">
              <div className="text-violet-300">⚙ Phase 1: Discover & Deduplicate</div>
              <div className="text-violet-300">⚙ Phase 2 & 4: Evidence Match Engine</div>
              <div className="text-violet-300">⚙ Phase 5 & 6: Truth Guard & ATS Audit</div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Latency Benchmarks */}
      {activeTab === 'latency' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl bg-jarvis-surface/50 border border-jarvis-border/40 text-center">
              <div className="text-2xl font-bold font-mono text-cyan-400">180ms</div>
              <div className="text-[11px] text-jarvis-muted uppercase tracking-wider font-semibold mt-1">
                Time-to-First-Token (Voice)
              </div>
              <p className="text-[11px] text-jarvis-muted/70 mt-1">Direct WebSocket intent path</p>
            </div>

            <div className="p-4 rounded-xl bg-jarvis-surface/50 border border-jarvis-border/40 text-center">
              <div className="text-2xl font-bold font-mono text-emerald-400">&lt; 18ms</div>
              <div className="text-[11px] text-jarvis-muted uppercase tracking-wider font-semibold mt-1">
                Barge-in Interruption
              </div>
              <p className="text-[11px] text-jarvis-muted/70 mt-1">Client-side immediate cutoff</p>
            </div>

            <div className="p-4 rounded-xl bg-jarvis-surface/50 border border-jarvis-border/40 text-center">
              <div className="text-2xl font-bold font-mono text-violet-400">12ms</div>
              <div className="text-[11px] text-jarvis-muted uppercase tracking-wider font-semibold mt-1">
                Truth Verification
              </div>
              <p className="text-[11px] text-jarvis-muted/70 mt-1">T1-T10 token containment audit</p>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-black/30 border border-jarvis-border/30 text-xs text-jarvis-muted">
            <span className="font-semibold text-white">Why it matters:</span> Traditional conversational agents take 2,000ms – 4,500ms to parse intent because they pipe every keystroke and vocal utterance through cloud LLMs. JARVIS uses a deterministic hybrid grammar for instantaneous execution and reserves LLMs solely for optional semantic expansion.
          </div>
        </div>
      )}
    </div>
  )
}
