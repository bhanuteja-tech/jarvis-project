import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useStore } from '../store/useStore'
import { continuousVoiceController, VoiceSessionState } from '../utils/ContinuousVoiceController'

const ORB_CLASSES: Record<string, string> = {
  idle: 'ai-orb',
  listening: 'ai-orb',
  transcribing: 'ai-orb-analyzing',
  routing: 'ai-orb',
  executing: 'ai-orb-searching',
  observing: 'ai-orb-analyzing',
  thinking: 'ai-orb',
  searching: 'ai-orb-searching',
  analyzing: 'ai-orb-analyzing',
  speaking: 'ai-orb',
  interrupted: 'ai-orb-error',
  ending: 'ai-orb-analyzing',
  ended: 'ai-orb',
  error: 'ai-orb-error',
}

const STATUS_COLORS: Record<string, string> = {
  idle: 'text-cyan-400',
  listening: 'text-amber-400',
  transcribing: 'text-blue-400',
  routing: 'text-violet-400',
  executing: 'text-cyan-400',
  observing: 'text-purple-400',
  thinking: 'text-blue-400',
  searching: 'text-cyan-400',
  analyzing: 'text-violet-400',
  speaking: 'text-emerald-400',
  interrupted: 'text-orange-400',
  ending: 'text-rose-400',
  ended: 'text-zinc-400',
  error: 'text-red-400',
}

const VOICE_LABELS: Record<VoiceSessionState, string> = {
  IDLE: 'READY',
  LISTENING: 'LISTENING',
  TRANSCRIBING: 'UNDERSTANDING',
  ROUTING: 'THINKING',
  EXECUTING: 'EXECUTING',
  OBSERVING: 'OBSERVING',
  SPEAKING: 'SPEAKING',
  INTERRUPTED: 'INTERRUPTED',
  ENDING: 'ENDING',
  ENDED: 'SESSION ENDED',
  ERROR: 'ERROR',
}

export function AICore() {
  const { aiCoreState: storeState, aiCoreLabel: storeLabel } = useStore()
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

  // In voice mode, the voice controller is authoritative
  const effectiveState = isVoiceActive ? voiceState.toLowerCase() : storeState
  const effectiveLabel = isVoiceActive
    ? `● ${VOICE_LABELS[voiceState] || voiceState}`
    : storeLabel

  const isActive = isVoiceActive
    ? voiceState !== 'IDLE' && voiceState !== 'ENDED'
    : storeState !== 'idle'

  const orbClass = ORB_CLASSES[effectiveState] || 'ai-orb'
  const statusColor = STATUS_COLORS[effectiveState] || 'text-cyan-400'

  return (
    <div className="relative flex items-center justify-center select-none">
      {/* Outermost ring — slow spin */}
      <motion.div
        className="absolute w-72 h-72 rounded-full border border-jarvis-border/20"
        animate={{ rotate: 360 }}
        transition={{ duration: 30, repeat: Infinity, ease: 'linear' }}
      >
        {/* Ring markers */}
        {[0, 90, 180, 270].map((deg) => (
          <div
            key={deg}
            className="absolute w-1.5 h-1.5 rounded-full bg-jarvis-accent/30"
            style={{
              top: '50%',
              left: '50%',
              transform: `rotate(${deg}deg) translateX(144px) translate(-50%, -50%)`,
            }}
          />
        ))}
      </motion.div>

      {/* Middle ring — counter-rotate */}
      <motion.div
        className="absolute w-56 h-56 rounded-full ai-orb-ring"
        animate={{ rotate: isActive ? -360 : 0 }}
        transition={{
          duration: isActive ? 8 : 0,
          repeat: isActive ? Infinity : 0,
          ease: 'linear',
        }}
      />

      {/* Pulse rings — visible when active */}
      {isActive && (
        <>
          <motion.div
            className="absolute w-48 h-48 rounded-full border-2 border-blue-500/30"
            animate={{ scale: [1, 1.6], opacity: [0.3, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
          />
          <motion.div
            className="absolute w-48 h-48 rounded-full border-2 border-violet-500/20"
            animate={{ scale: [1, 1.8], opacity: [0.2, 0] }}
            transition={{ duration: 2.5, repeat: Infinity, ease: 'easeOut', delay: 0.3 }}
          />
        </>
      )}

      {/* Main ORB */}
      <motion.div
        className={`w-40 h-40 rounded-full ${orbClass} relative`}
        animate={{
          scale: isActive ? [1, 1.06, 1] : [1, 1.02, 1],
        }}
        transition={{
          duration: isActive ? 1.5 : 4,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      >
        {/* Inner light */}
        <motion.div
          className="absolute inset-6 rounded-full bg-white/10"
          animate={{
            opacity: isActive ? [0.1, 0.3, 0.1] : [0.05, 0.15, 0.05],
          }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        />

        {/* Hot spot */}
        <div
          className="absolute w-4 h-4 rounded-full bg-white/25 blur-sm"
          style={{ top: '25%', left: '30%' }}
        />
      </motion.div>

      {/* Orbiting particles */}
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          className="absolute w-2 h-2 rounded-full"
          style={{
            background: i === 0 ? '#60a5fa' : i === 1 ? '#a78bfa' : '#22d3ee',
            boxShadow: `0 0 8px ${i === 0 ? '#60a5fa' : i === 1 ? '#a78bfa' : '#22d3ee'}`,
            top: '50%',
            left: '50%',
            // CSS custom property for orbit radius
            ['--orbit-radius' as any]: '100px',
          }}
          animate={{
            rotate: 360,
            x: [
              Math.cos(((i * 120) * Math.PI) / 180) * 100,
              Math.cos(((i * 120 + 360) * Math.PI) / 180) * 100,
            ],
            y: [
              Math.sin(((i * 120) * Math.PI) / 180) * 100,
              Math.sin(((i * 120 + 360) * Math.PI) / 180) * 100,
            ],
          }}
          transition={{
            duration: isActive ? 6 : 12,
            repeat: Infinity,
            ease: 'linear',
            delay: i * (isActive ? 2 : 4),
          }}
        />
      ))}

      {/* Status label */}
      <motion.div
        className="absolute -bottom-20 left-1/2 -translate-x-1/2 text-center"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        key={effectiveLabel}
      >
        <p className={`text-xs font-semibold tracking-[0.2em] uppercase ${statusColor}`}>
          {effectiveLabel}
        </p>
        {isActive && (
          <motion.div
            className="mx-auto mt-2 w-16 h-0.5 rounded-full progress-bar"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          />
        )}
      </motion.div>

      {/* "JARVIS" watermark */}
      <div className="absolute -bottom-32 left-1/2 -translate-x-1/2">
        <p className="text-[10px] font-light tracking-[0.5em] text-jarvis-muted/30 uppercase">
          J.A.R.V.I.S
        </p>
      </div>
    </div>
  )
}
