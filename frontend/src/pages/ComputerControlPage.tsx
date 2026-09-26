import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Monitor,
  CheckCircle,
  XCircle,
  AlertCircle,
  Clock,
  Globe,
  AppWindow,
  ChevronRight,
  ChevronDown,
  Terminal,
  Send,
  Sparkles,
  Layers,
  Check,
} from 'lucide-react'
import { useStore } from '../store/useStore'

interface ComputerControlPageProps {
  sendMessage: (text: string) => void
}

function VerifyBadge({ verified }: { verified: boolean | null }) {
  if (verified === true) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
        <CheckCircle size={11} className="text-emerald-400" />
        VERIFIED
      </span>
    )
  }
  if (verified === false) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-red-500/10 text-red-400 border border-red-500/30">
        <XCircle size={11} className="text-red-400" />
        FAILED
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
      <AlertCircle size={11} className="text-amber-400" />
      PENDING
    </span>
  )
}

export function ComputerControlPage({ sendMessage }: ComputerControlPageProps) {
  const { computerState, computerContext } = useStore()
  const [debugOpen, setDebugOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [computerState.stepResults.length, computerState.lastResponse])

  const handleSend = () => {
    const val = inputRef.current?.value.trim()
    if (val) {
      sendMessage(val)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Determine current active application display
  const isExplorer =
    (computerContext.activeApp || '').toLowerCase().includes('explorer') ||
    (computerContext.activeApp || '').toLowerCase().includes('desktop') ||
    (computerContext.activeApp || '').toLowerCase().includes('file')

  const activeApp =
    computerContext.activeApp ||
    (computerContext.activeBrowser ? 'Browser' : 'Desktop')
  const activeWindow =
    computerContext.activeWindow || computerContext.windowTitle || 'Foreground Window'
  const activeBrowser = isExplorer
    ? 'None'
    : (computerContext.activeBrowser || (computerContext.currentUrl ? 'Google Chrome' : 'None'))
  const activeUrl = isExplorer
    ? (computerContext.currentDirectory || 'Desktop')
    : (computerContext.currentUrl || (computerContext.domain ? `https://${computerContext.domain}` : 'No active page'))

  // Hierarchical breadcrumb items
  const breadcrumbItems: string[] = []
  if (isExplorer) {
    breadcrumbItems.push('FILESYSTEM')
    const dir = computerContext.currentDirectory || 'Desktop'
    const parts = dir.replace(/\\/g, '/').split('/').filter(Boolean)
    const tail = parts.slice(-2)
    tail.forEach(p => breadcrumbItems.push(p))
  } else {
    if (computerContext.site) breadcrumbItems.push(computerContext.site.toUpperCase())
    if (computerContext.channel) breadcrumbItems.push(computerContext.channel)
    if (computerContext.course || computerContext.playlist) {
      breadcrumbItems.push(computerContext.course || computerContext.playlist || '')
    }
    if (computerContext.video) breadcrumbItems.push(computerContext.video)
  }

  return (
    <div className="flex flex-col h-full bg-jarvis-bg/95 overflow-hidden">
      {/* Top Bar Header */}
      <div className="h-14 px-6 border-b border-jarvis-border/20 flex items-center justify-between flex-shrink-0 bg-jarvis-surface/20">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-violet-600/20 border border-violet-500/30 flex items-center justify-center text-violet-400">
            <Monitor size={16} />
          </div>
          <div>
            <h2 className="text-xs font-semibold text-white tracking-wide flex items-center gap-2">
              JARVIS Computer Control
              <span className="text-[10px] font-normal text-violet-400 bg-violet-500/10 px-2 py-0.5 rounded-full border border-violet-500/20">
                Agentic Desktop
              </span>
            </h2>
            <p className="text-[10px] text-jarvis-muted">
              Plan → Act → Observe → Verify
            </p>
          </div>
        </div>

        {/* Live Status Pill */}
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-[11px] font-medium border transition-colors ${
            computerState.isRunning
              ? 'bg-violet-500/10 border-violet-500/40 text-violet-300'
              : 'bg-jarvis-surface/40 border-jarvis-border/30 text-jarvis-muted'
          }`}>
            <span className={`w-2 h-2 rounded-full ${
              computerState.isRunning ? 'bg-violet-400 animate-ping' : 'bg-emerald-400'
            }`} />
            {computerState.isRunning ? 'Executing Task' : 'System Ready'}
          </div>
        </div>
      </div>

      {/* Main Body */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">

        {/* SECTION 1: CURRENT COMPUTER */}
        <div className="rounded-2xl border border-jarvis-border/30 bg-jarvis-surface/30 backdrop-blur-sm p-4">
          <div className="flex items-center justify-between mb-3 pb-2 border-b border-jarvis-border/20">
            <span className="text-[11px] font-semibold text-jarvis-muted tracking-wider uppercase flex items-center gap-1.5">
              <AppWindow size={13} className="text-violet-400" />
              Current Computer
            </span>
            <span className="text-[10px] text-jarvis-muted font-mono">
              Live Observation
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/20">
              <span className="text-[10px] text-jarvis-muted uppercase tracking-wider block mb-1">
                Application
              </span>
              <p className="text-xs font-semibold text-white truncate" title={activeApp}>
                {activeApp}
              </p>
            </div>

            <div className="p-3 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/20">
              <span className="text-[10px] text-jarvis-muted uppercase tracking-wider block mb-1">
                Window
              </span>
              <p className="text-xs font-semibold text-white truncate" title={activeWindow}>
                {activeWindow}
              </p>
            </div>

            <div className="p-3 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/20">
              <span className="text-[10px] text-jarvis-muted uppercase tracking-wider block mb-1">
                Browser
              </span>
              <p className="text-xs font-semibold text-white truncate" title={activeBrowser}>
                {activeBrowser}
              </p>
            </div>

            <div className="p-3 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/20">
              <span className="text-[10px] text-jarvis-muted uppercase tracking-wider block mb-1">
                {isExplorer ? 'Directory' : 'URL / Page'}
              </span>
              <p className="text-xs font-semibold text-white truncate" title={activeUrl}>
                {activeUrl}
              </p>
            </div>
          </div>
        </div>

        {/* SECTION 2: CURRENT CONTEXT HIERARCHY */}
        <div className="rounded-2xl border border-jarvis-border/30 bg-jarvis-surface/30 backdrop-blur-sm p-4">
          <div className="flex items-center justify-between mb-3 pb-2 border-b border-jarvis-border/20">
            <span className="text-[11px] font-semibold text-jarvis-muted tracking-wider uppercase flex items-center gap-1.5">
              <Layers size={13} className="text-emerald-400" />
              Current Context
            </span>
            {computerContext.ordinalBasis && (
              <span className="text-[10px] text-emerald-400 font-medium">
                {computerContext.ordinalBasis}
              </span>
            )}
          </div>

          {breadcrumbItems.length > 0 ? (
            <div className="flex items-center flex-wrap gap-2 py-1">
              {breadcrumbItems.map((item, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <div className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs font-medium text-emerald-300">
                    {item}
                  </div>
                  {idx < breadcrumbItems.length - 1 && (
                    <ChevronRight size={14} className="text-jarvis-muted/50" />
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="py-2 text-xs text-jarvis-muted flex items-center gap-2">
              <Globe size={13} className="text-jarvis-muted/60" />
              No active website or hierarchical media in context yet. Start by saying &ldquo;Open YouTube in Edge&rdquo; or &ldquo;Open File Explorer&rdquo;.
            </div>
          )}

          {/* Current List Preview if available */}
          {computerContext.currentList && computerContext.currentList.length > 0 && (
            <div className="mt-3 pt-3 border-t border-jarvis-border/10">
              <span className="text-[10px] text-jarvis-muted uppercase tracking-wider block mb-2">
                Available Context Items ({computerContext.currentList.length})
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {computerContext.currentList.slice(0, 6).map((item, i) => (
                  <div
                    key={i}
                    className="p-2 rounded-lg bg-jarvis-surface/40 border border-jarvis-border/20 text-[11px] text-jarvis-light truncate flex items-center gap-2"
                  >
                    <span className="w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-300 text-[9px] font-mono flex items-center justify-center flex-shrink-0">
                      {item.ordinal ?? i + 1}
                    </span>
                    <span className="truncate">{item.title || item.name || item.url}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* SECTION 3: CURRENT TASK & VERIFIED CHECKLIST */}
        <div className="rounded-2xl border border-jarvis-border/30 bg-jarvis-surface/30 backdrop-blur-sm p-4">
          <div className="flex items-center justify-between mb-3 pb-2 border-b border-jarvis-border/20">
            <span className="text-[11px] font-semibold text-jarvis-muted tracking-wider uppercase flex items-center gap-1.5">
              <Sparkles size={13} className="text-violet-400" />
              Current Task
            </span>
            {computerState.lastVerified !== null && (
              <VerifyBadge verified={computerState.lastVerified} />
            )}
          </div>

          {computerState.planDescription ? (
            <div className="space-y-4">
              <div className="p-3.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
                <p className="text-sm font-semibold text-white">
                  {computerState.planDescription}
                </p>
                {computerState.currentStepDescription && computerState.isRunning && (
                  <p className="text-xs text-violet-300 mt-1 flex items-center gap-1.5">
                    <Clock size={12} className="animate-spin text-violet-400" />
                    Executing: {computerState.currentStepDescription}
                  </p>
                )}
              </div>

              {/* Task Checklist */}
              {computerState.steps.length > 0 && (
                <div className="space-y-2">
                  {computerState.steps.map((step, idx) => {
                    const isDone = idx < computerState.currentStepIdx || idx < computerState.stepResults.length
                    const isActive = idx === computerState.currentStepIdx && computerState.isRunning
                    const result = computerState.stepResults[idx]

                    return (
                      <div
                        key={idx}
                        className={`flex items-center gap-3 p-3 rounded-xl border text-xs transition-colors ${
                          isActive
                            ? 'bg-violet-500/15 border-violet-500/40 text-violet-200'
                            : isDone
                            ? result?.verified === false
                              ? 'bg-red-500/10 border-red-500/20 text-red-300'
                              : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
                            : 'bg-jarvis-surface/20 border-jarvis-border/20 text-jarvis-muted'
                        }`}
                      >
                        <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold ${
                          isActive
                            ? 'bg-violet-500 text-white animate-pulse'
                            : isDone
                            ? result?.verified === false
                              ? 'bg-red-500 text-white'
                              : 'bg-emerald-500 text-white'
                            : 'bg-jarvis-border/40 text-jarvis-muted'
                        }`}>
                          {isDone ? (
                            result?.verified === false ? (
                              <XCircle size={12} />
                            ) : (
                              <Check size={12} />
                            )
                          ) : isActive ? (
                            '▶'
                          ) : (
                            '○'
                          )}
                        </div>

                        <span className="font-medium flex-1 truncate">{step}</span>

                        {result && (
                          <span className="text-[10px] opacity-80">
                            {result.verified === false ? 'Verification Failed' : 'Verified ✓'}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Final Verified Response */}
              {computerState.lastResponse && (
                <div className={`p-4 rounded-xl border text-xs leading-relaxed ${
                  computerState.lastVerified === true
                    ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-200'
                    : computerState.lastVerified === false
                    ? 'bg-red-950/20 border-red-500/30 text-red-200'
                    : 'bg-jarvis-surface/60 border-jarvis-border/30 text-white'
                }`}>
                  <span className="text-[10px] font-bold uppercase tracking-wider block mb-1 opacity-70">
                    Assistant Response
                  </span>
                  {computerState.lastResponse}
                </div>
              )}
            </div>
          ) : (
            <div className="py-6 text-center text-xs text-jarvis-muted">
              No active task running. Try issuing a natural command like:
              <div className="mt-3 flex flex-wrap justify-center gap-2">
                {[
                  'Open Edge and search LangGraph on YouTube',
                  'Open the third video',
                  'Open File Explorer and open Desktop',
                  'Open WhatsApp and send hi to Lohit',
                ].map((sample, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(sample)}
                    className="px-3 py-1.5 rounded-lg bg-jarvis-surface/60 hover:bg-violet-600/20 border border-jarvis-border/30 hover:border-violet-500/40 text-jarvis-light text-xs transition-colors"
                  >
                    &ldquo;{sample}&rdquo;
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Confirmation Required Alert */}
          {computerState.needsConfirm && (
            <div className="mt-4 p-4 rounded-xl border border-amber-500/40 bg-amber-500/10">
              <div className="flex items-center gap-2 text-amber-300 font-semibold text-xs mb-2">
                <AlertCircle size={15} />
                User Confirmation Required
              </div>
              <p className="text-xs text-jarvis-light mb-3">
                {computerState.lastResponse || 'Please confirm if you want to proceed with this high-risk action.'}
              </p>
              <div className="flex items-center gap-3">
                <button
                  id="confirm-action-yes"
                  onClick={() => sendMessage('yes, confirm and send')}
                  className="px-4 py-1.5 rounded-lg bg-amber-500 text-black font-semibold text-xs hover:bg-amber-400 transition-colors"
                >
                  Confirm & Send
                </button>
                <button
                  id="confirm-action-cancel"
                  onClick={() => sendMessage('cancel action')}
                  className="px-4 py-1.5 rounded-lg bg-jarvis-surface border border-jarvis-border/30 text-jarvis-muted text-xs hover:text-white transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        {/* SECTION 4: ADVANCED DEBUG (COLLAPSIBLE) */}
        <div className="rounded-2xl border border-jarvis-border/20 bg-jarvis-surface/20 overflow-hidden">
          <button
            onClick={() => setDebugOpen(!debugOpen)}
            className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-jarvis-surface/40 transition-colors"
          >
            <span className="text-xs font-semibold text-jarvis-muted tracking-wide flex items-center gap-2">
              <Terminal size={14} className="text-jarvis-muted" />
              Advanced Debug Telemetry
            </span>
            <span className="text-xs text-jarvis-muted flex items-center gap-1">
              {debugOpen ? 'Hide' : 'Show'}
              {debugOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
          </button>

          <AnimatePresence>
            {debugOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="border-t border-jarvis-border/20 p-4 font-mono text-[11px] text-jarvis-light/80 space-y-2 bg-jarvis-bg/40"
              >
                <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                  <div>
                    <span className="text-jarvis-muted">Intent:</span>{' '}
                    <span className="text-violet-300">{computerState.intent || 'None'}</span>
                  </div>
                  <div>
                    <span className="text-jarvis-muted">Browser Target:</span>{' '}
                    <span className="text-blue-300">{computerState.browser || 'None'}</span>
                  </div>
                  <div>
                    <span className="text-jarvis-muted">Target Entity:</span>{' '}
                    <span className="text-emerald-300">{computerState.target || 'None'}</span>
                  </div>
                  <div>
                    <span className="text-jarvis-muted">Current Tool:</span>{' '}
                    <span className="text-amber-300">
                      {computerState.stepResults.slice(-1)[0]?.tool || 'None'}
                    </span>
                  </div>
                  <div>
                    <span className="text-jarvis-muted">Task ID:</span>{' '}
                    <span className="text-jarvis-light">{computerState.taskId || 'session_task_0'}</span>
                  </div>
                  <div>
                    <span className="text-jarvis-muted">Verified Status:</span>{' '}
                    <span className={computerState.lastVerified ? 'text-emerald-400' : 'text-amber-400'}>
                      {computerState.lastVerified === null ? 'None' : String(computerState.lastVerified)}
                    </span>
                  </div>
                </div>

                {computerState.latencyMetrics && (
                  <div className="mt-3 pt-3 border-t border-jarvis-border/20">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-violet-400 font-bold uppercase text-[10px] tracking-wider">
                        Latency Breakdown ({computerState.latencyMetrics.system_tier || 'SYSTEM'})
                      </span>
                      <span className="text-emerald-400 font-bold text-xs">
                        TOTAL: {computerState.latencyMetrics.total_latency ?? 0}s
                      </span>
                    </div>
                    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-[10px]">
                      <div className="p-2 rounded bg-black/40 border border-jarvis-border/20">
                        <span className="text-jarvis-muted block text-[9px]">Router</span>
                        <span className="text-white font-mono">{computerState.latencyMetrics.routing_latency ?? 0}s</span>
                      </div>
                      <div className="p-2 rounded bg-black/40 border border-jarvis-border/20">
                        <span className="text-jarvis-muted block text-[9px]">Laya</span>
                        <span className="text-white font-mono">{computerState.latencyMetrics.laya_latency ?? 0}s</span>
                      </div>
                      <div className="p-2 rounded bg-black/40 border border-jarvis-border/20">
                        <span className="text-jarvis-muted block text-[9px]">Model</span>
                        <span className="text-white font-mono">{computerState.latencyMetrics.model_latency ?? 0}s</span>
                      </div>
                      <div className="p-2 rounded bg-black/40 border border-jarvis-border/20">
                        <span className="text-jarvis-muted block text-[9px]">Tool</span>
                        <span className="text-white font-mono">{computerState.latencyMetrics.tool_latency ?? 0}s</span>
                      </div>
                      <div className="p-2 rounded bg-black/40 border border-jarvis-border/20">
                        <span className="text-jarvis-muted block text-[9px]">Observation</span>
                        <span className="text-white font-mono">{computerState.latencyMetrics.observation_latency ?? 0}s</span>
                      </div>
                      <div className="p-2 rounded bg-black/40 border border-jarvis-border/20">
                        <span className="text-jarvis-muted block text-[9px]">Verification</span>
                        <span className="text-white font-mono">{computerState.latencyMetrics.verification_latency ?? 0}s</span>
                      </div>
                    </div>
                  </div>
                )}

                {computerState.observation && (
                  <div className="mt-2 pt-2 border-t border-jarvis-border/10">
                    <span className="text-jarvis-muted block mb-1">Observation:</span>
                    <p className="text-jarvis-light bg-black/30 p-2 rounded border border-jarvis-border/20">
                      {computerState.observation}
                    </p>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

      </div>

      {/* SECTION 5: COMMAND INPUT AT BOTTOM */}
      <div className="p-4 border-t border-jarvis-border/20 bg-jarvis-surface/40 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <input
              ref={inputRef}
              id="computer-agent-input"
              type="text"
              placeholder='Speak or type: "Open Edge and search LangGraph on YouTube", "Open the third video"...'
              onKeyDown={handleKeyDown}
              className="w-full bg-jarvis-surface/80 border border-jarvis-border/40 focus:border-violet-500/60 rounded-xl px-4 py-2.5 text-xs text-white placeholder:text-jarvis-muted/50 focus:outline-none focus:ring-1 focus:ring-violet-500/30 transition-all"
            />
          </div>
          <button
            id="computer-agent-submit"
            onClick={handleSend}
            disabled={computerState.isRunning}
            className="px-4 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-medium text-xs flex items-center gap-1.5 transition-all shadow-lg shadow-violet-600/20"
          >
            <Send size={13} />
            <span>Send</span>
          </button>
        </div>
      </div>
    </div>
  )
}
