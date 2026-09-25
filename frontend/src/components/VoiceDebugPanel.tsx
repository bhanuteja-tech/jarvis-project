import { useState, useEffect } from 'react'
import { continuousVoiceController, VoiceDebugData } from '../utils/ContinuousVoiceController'
import { Activity, Mic, Volume2, ShieldAlert, Cpu, Radio, Zap } from 'lucide-react'

export function VoiceDebugPanel() {
  const [debugData, setDebugData] = useState<VoiceDebugData>(continuousVoiceController.getDebugData())
  const [isMinimized, setIsMinimized] = useState<boolean>(false)

  useEffect(() => {
    const unsub = continuousVoiceController.subscribeDebug((data) => {
      setDebugData(data)
    })
    return unsub
  }, [])

  const {
    state,
    isActive,
    recognitionRunning,
    generation,
    currentTranscript,
    interimTranscript,
    normalizedTranscript,
    routerType,
    intent,
    entity,
    confidence,
    execution,
    verification,
    activeApplication,
    currentDirectory,
    taskId,
    currentStep,
    currentTask,
    ttsStatus,
    errorMessage,
    recentEvents,
    latencies,
  } = debugData

  return (
    <div className="fixed bottom-4 right-4 z-50 w-96 max-w-[calc(100vw-2rem)] rounded-2xl bg-zinc-950/95 border border-cyan-500/30 shadow-2xl backdrop-blur-xl text-xs font-mono text-zinc-300 overflow-hidden flex flex-col">
      {/* Header */}
      <div className="px-4 py-2.5 bg-gradient-to-r from-cyan-950/80 to-blue-950/80 border-b border-cyan-500/20 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            {isActive && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            )}
            <span
              className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                isActive ? 'bg-cyan-500' : 'bg-zinc-600'
              }`}
            />
          </span>
          <span className="font-semibold text-cyan-300 tracking-wider text-[11px] uppercase flex items-center gap-1.5">
            <Radio className="w-3.5 h-3.5 text-cyan-400" />
            Computer Agent Debug
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
            GEN {generation}
          </span>
          <button
            type="button"
            onClick={() => setIsMinimized((v) => !v)}
            className="text-zinc-400 hover:text-white px-1.5 py-0.5 text-xs rounded hover:bg-white/5 transition-colors cursor-pointer"
          >
            {isMinimized ? '▲ Expand' : '▼ Minimize'}
          </button>
        </div>
      </div>

      {/* Body */}
      {!isMinimized && (
        <div className="p-3.5 space-y-3 max-h-[70vh] overflow-y-auto">
          {/* Status Matrix Grid */}
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="p-2 rounded-lg bg-zinc-900/80 border border-zinc-800 flex items-center justify-between">
              <span className="text-zinc-400 flex items-center gap-1.5">
                <Activity className="w-3 h-3 text-cyan-400" /> Session:
              </span>
              <span
                className={`font-semibold ${
                  isActive ? 'text-emerald-400' : 'text-zinc-500'
                }`}
              >
                {isActive ? 'ACTIVE' : 'INACTIVE'}
              </span>
            </div>

            <div className="p-2 rounded-lg bg-zinc-900/80 border border-zinc-800 flex items-center justify-between">
              <span className="text-zinc-400 flex items-center gap-1.5">
                <Mic className="w-3 h-3 text-amber-400" /> Recognition:
              </span>
              <span
                className={`font-semibold ${
                  recognitionRunning ? 'text-amber-300' : 'text-zinc-500'
                }`}
              >
                {recognitionRunning ? 'RUNNING' : 'STOPPED'}
              </span>
            </div>

            <div className="p-2 rounded-lg bg-zinc-900/80 border border-zinc-800 flex items-center justify-between">
              <span className="text-zinc-400 flex items-center gap-1.5">
                <Volume2 className="w-3 h-3 text-emerald-400" /> TTS State:
              </span>
              <span
                className={`font-semibold ${
                  ttsStatus === 'SPEAKING' ? 'text-emerald-300 animate-pulse' : 'text-zinc-500'
                }`}
              >
                {ttsStatus}
              </span>
            </div>

            <div className="p-2 rounded-lg bg-zinc-900/80 border border-zinc-800 flex items-center justify-between">
              <span className="text-zinc-400 flex items-center gap-1.5">
                <Cpu className="w-3 h-3 text-violet-400" /> Verification:
              </span>
              <span className={`font-semibold ${verification === 'SUCCESS' ? 'text-emerald-400' : verification ? 'text-amber-400' : 'text-zinc-500'}`}>
                {verification || 'PENDING'}
              </span>
            </div>
          </div>

          {/* Router & Intent & Computer State */}
          <div className="p-2.5 rounded-lg bg-zinc-900/90 border border-zinc-800/80 space-y-1 text-[11px]">
            <div className="flex items-center justify-between">
              <span className="text-zinc-400">Router / State:</span>
              <span className="text-cyan-300 font-semibold">{routerType} ({state})</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-zinc-400">Intent:</span>
              <span className="text-amber-300 font-semibold">{intent}</span>
            </div>
            {currentTask && currentTask !== 'idle' && (
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Task:</span>
                <span className="text-zinc-300 truncate max-w-[170px]">{currentTask}</span>
              </div>
            )}
            {entity && (
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Entity:</span>
                <span className="text-cyan-300 font-semibold">{entity}</span>
              </div>
            )}
            {confidence !== undefined && (
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Confidence:</span>
                <span className="text-emerald-400">{confidence.toFixed(2)}</span>
              </div>
            )}
            {execution && (
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Execution:</span>
                <span className="text-violet-300">{execution}</span>
              </div>
            )}
            {activeApplication && (
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Active App:</span>
                <span className="text-white font-medium truncate max-w-[170px]">{activeApplication}</span>
              </div>
            )}
            {currentDirectory && (
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Directory:</span>
                <span className="text-zinc-300 truncate max-w-[170px]" title={currentDirectory}>
                  {currentDirectory.split('\\').pop() || currentDirectory}
                </span>
              </div>
            )}
            {taskId && (
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-zinc-500">Task / Step:</span>
                <span className="text-zinc-400">{taskId.slice(-8)} {currentStep ? `(#${currentStep})` : ''}</span>
              </div>
            )}
          </div>

          {/* Live Transcript Display */}
          <div className="p-2.5 rounded-lg bg-zinc-900/90 border border-zinc-800/80 space-y-1">
            <div className="text-[10px] uppercase text-zinc-400 font-semibold flex items-center justify-between">
              <span>Transcript</span>
              {interimTranscript && (
                <span className="text-amber-400 animate-pulse text-[10px]">Listening...</span>
              )}
            </div>
            <div className="text-xs text-white bg-black/40 p-2 rounded border border-zinc-800 min-h-[36px] break-words">
              {currentTranscript ? (
                <div>
                  <span className="text-emerald-300">"{currentTranscript}"</span>
                  {normalizedTranscript && normalizedTranscript !== currentTranscript && (
                    <div className="text-[10px] text-cyan-400 mt-1">
                      ➔ Normalized: "{normalizedTranscript}"
                    </div>
                  )}
                </div>
              ) : interimTranscript ? (
                <span className="text-zinc-400 italic">"{interimTranscript}"</span>
              ) : (
                <span className="text-zinc-600 italic">Waiting for speech...</span>
              )}
            </div>
          </div>

          {/* Latency Breakdown */}
          <div className="p-2.5 rounded-lg bg-zinc-900/90 border border-zinc-800/80 space-y-1.5 text-[10px]">
            <div className="text-zinc-400 uppercase font-semibold flex items-center gap-1">
              <Zap className="w-3 h-3 text-yellow-400" /> Measured Latencies
            </div>
            <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-zinc-300">
              <div>Speech end → Final:</div>
              <div className="text-right text-cyan-400">{latencies.speechEndToFinalMs} ms</div>
              <div>Final → Router send:</div>
              <div className="text-right text-cyan-400">{latencies.finalToRouterMs} ms</div>
              <div>Response → TTS start:</div>
              <div className="text-right text-cyan-400">{latencies.responseToTtsStartMs} ms</div>
            </div>
          </div>

          {/* Error Message */}
          {errorMessage && (
            <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-500/40 text-red-300 text-xs flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-red-400 flex-shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Event Log (last 8 events) */}
          <div className="space-y-1">
            <div className="text-[10px] uppercase text-zinc-400 font-semibold">
              Recognition Events
            </div>
            <div className="p-2 rounded-lg bg-black/40 border border-zinc-800/80 max-h-28 overflow-y-auto space-y-1 text-[10px]">
              {recentEvents.slice(0, 8).map((ev) => (
                <div key={ev.id} className="flex items-center justify-between text-zinc-400">
                  <span className="text-cyan-400 font-medium">{ev.event}</span>
                  <span className="text-zinc-500 truncate max-w-[140px]">{ev.detail || ''}</span>
                  <span className="text-zinc-600 text-[9px]">
                    {new Date(ev.time).toLocaleTimeString().slice(3)}
                  </span>
                </div>
              ))}
              {recentEvents.length === 0 && (
                <div className="text-zinc-600 italic">No events recorded yet.</div>
              )}
            </div>
          </div>

          {/* Interactive Debug Controls */}
          <div className="pt-1 flex items-center gap-2">
            {isActive ? (
              <>
                <button
                  type="button"
                  onClick={() => continuousVoiceController.bargeIn()}
                  className="flex-1 py-1.5 px-2.5 rounded-lg bg-amber-600/80 hover:bg-amber-500 text-white font-semibold text-[11px] transition-all cursor-pointer flex items-center justify-center gap-1 shadow-lg shadow-amber-900/30"
                >
                  ⚡ Test Barge-In
                </button>
                <button
                  type="button"
                  onClick={() => continuousVoiceController.stopSession()}
                  className="py-1.5 px-3 rounded-lg bg-red-600/80 hover:bg-red-500 text-white font-semibold text-[11px] transition-all cursor-pointer"
                >
                  Stop
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => continuousVoiceController.startSession()}
                className="w-full py-1.5 px-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-[11px] transition-all cursor-pointer flex items-center justify-center gap-1.5 shadow-lg shadow-cyan-900/30"
              >
                <Mic className="w-3.5 h-3.5" /> Start Continuous Voice
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
