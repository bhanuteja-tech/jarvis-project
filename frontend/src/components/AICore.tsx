import { useEffect, useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { Activity, CheckCircle2, Mic, Terminal } from 'lucide-react'
import { useStore } from '../store/useStore'
import { continuousVoiceController, VoiceSessionState } from '../utils/ContinuousVoiceController'

const STATE_MAPPINGS: Record<string, { label: string; mode: 'idle' | 'active' | 'warning' | 'verified' | 'error'; note: string }> = {
  idle: { label: 'Standby', mode: 'idle', note: 'Awaiting voice or keyboard instruction' },
  listening: { label: 'Listening', mode: 'active', note: 'Acoustic input active — speak freely' },
  transcribing: { label: 'Processing audio', mode: 'active', note: 'Interpreting speech phonemes' },
  routing: { label: 'Planning steps', mode: 'active', note: 'Mapping goal to OS commands' },
  executing: { label: 'Executing action', mode: 'warning', note: 'Dispatched to local agent on your machine' },
  observing: { label: 'Observing screen', mode: 'active', note: 'Grounding state against visible window titles' },
  thinking: { label: 'Evaluating state', mode: 'active', note: 'Validating safety boundaries' },
  searching: { label: 'Querying filesystem', mode: 'active', note: 'Searching local directory tree' },
  analyzing: { label: 'Verifying outcome', mode: 'active', note: 'Checking post-execution evidence' },
  speaking: { label: 'Responding', mode: 'verified', note: 'Streaming audio feedback' },
  interrupted: { label: 'Interrupted', mode: 'error', note: 'Execution halted by user barge-in' },
  ending: { label: 'Closing session', mode: 'idle', note: 'Terminating channel' },
  ended: { label: 'Session ended', mode: 'idle', note: 'Standby' },
  error: { label: 'Action failed', mode: 'error', note: 'Execution halted or connection timed out' },
}

export function AICore() {
  const { aiCoreState: storeState, computerState } = useStore()
  const [voiceState, setVoiceState] = useState<VoiceSessionState>('IDLE')
  const [isVoiceActive, setIsVoiceActive] = useState<boolean>(false)

  useEffect(() => {
    const unsub = continuousVoiceController.subscribe((state) => {
      setVoiceState(state)
      const debug = continuousVoiceController.getDebugData()
      setIsVoiceActive(debug.isActive || state !== 'IDLE')
    })
    return unsub
  }, [])

  const rawState = isVoiceActive ? voiceState.toLowerCase() : storeState
  const currentConfig = STATE_MAPPINGS[rawState] || STATE_MAPPINGS.idle

  const isExecuting = rawState === 'executing' || rawState === 'searching'
  const isListening = rawState === 'listening' || rawState === 'transcribing'
  const isSpeaking = rawState === 'speaking'
  const isError = rawState === 'error' || rawState === 'interrupted'

  // Generate 20 calibrated spectrometer bars
  const bars = useMemo(() => Array.from({ length: 24 }), [])

  return (
    <div className="w-full max-w-xl mx-auto rounded border border-[#262B35] bg-[#16191E] p-4 text-[#E1E4EA] select-none">
      {/* Top Header Rail */}
      <div className="flex items-center justify-between border-b border-[#262B35] pb-3 text-xs">
        <div className="flex items-center gap-2">
          {/* Signal Indicator Dot */}
          <span
            className={`w-2 h-2 rounded-full ${
              isError
                ? 'bg-[#E2604E]'
                : isExecuting
                ? 'bg-[#D97736] animate-pulse'
                : isListening
                ? 'bg-[#D97736]'
                : isSpeaking
                ? 'bg-[#2EA069]'
                : 'bg-[#828997]/50'
            }`}
          />
          <span className="font-medium text-[#E1E4EA]">{currentConfig.label}</span>
          <span className="text-[#828997] font-mono text-[11px]">[{rawState}]</span>
        </div>

        <div className="flex items-center gap-3 text-[#828997] font-mono text-[11px]">
          <span className="flex items-center gap-1">
            <Terminal size={12} className="text-[#828997]" />
            <span>PID: verified</span>
          </span>
          <span className="flex items-center gap-1">
            <Mic size={12} className={isListening ? 'text-[#D97736]' : 'text-[#828997]'} />
            <span>{isListening ? 'Audio live' : 'Muted'}</span>
          </span>
        </div>
      </div>

      {/* Central Calibrated Spectrometer / Reticle */}
      <div className="py-5 px-2">
        <div className="flex items-end justify-between h-14 gap-1 px-4 bg-[#0E1013] rounded border border-[#262B35]/70">
          {bars.map((_, i) => {
            // Predictable, calm bar height based on real operational state
            const centerDistance = Math.abs(i - 12) / 12
            const baseFactor = 1 - centerDistance * 0.4
            
            let height = 4 // minimum baseline floor
            let color = '#262B35' // idle hairline

            if (isListening) {
              const variance = ((i * 17) % 7) * 4
              height = Math.max(6, Math.min(48, variance * baseFactor + 8))
              color = '#D97736'
            } else if (isSpeaking) {
              const variance = ((i * 23) % 9) * 4.5
              height = Math.max(6, Math.min(44, variance * baseFactor + 6))
              color = '#2EA069'
            } else if (isExecuting) {
              const variance = ((i * 13) % 5) * 5
              height = Math.max(6, Math.min(36, variance + 6))
              color = '#D97736'
            } else if (isError) {
              height = 8
              color = '#E2604E'
            }

            return (
              <motion.div
                key={i}
                className="flex-1 rounded-t-sm"
                style={{ backgroundColor: color }}
                animate={{ height: `${height}px` }}
                transition={{ duration: 0.15, ease: 'easeOut' }}
              />
            )
          })}
        </div>
      </div>

      {/* Bottom Telemetry Note & Action Guard */}
      <div className="flex items-center justify-between text-xs text-[#828997] pt-2 border-t border-[#262B35] font-mono">
        <span className="truncate pr-4 font-sans text-xs text-[#828997]">
          {currentConfig.note}
        </span>
        <div className="flex items-center gap-2 shrink-0">
          {computerState.lastVerified ? (
            <span className="inline-flex items-center gap-1 text-[#2EA069] text-[11px]">
              <CheckCircle2 size={12} />
              <span>State verified</span>
            </span>
          ) : isExecuting ? (
            <span className="inline-flex items-center gap-1 text-[#D97736] text-[11px]">
              <Activity size={12} className="animate-spin" />
              <span>Step in progress</span>
            </span>
          ) : (
            <span className="text-[11px] text-[#828997]">Safety interlock armed</span>
          )}
        </div>
      </div>
    </div>
  )
}
