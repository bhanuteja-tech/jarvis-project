import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Terminal,
  Send,
  AppWindow,
  Check
} from 'lucide-react'
import { useStore } from '../store/useStore'
import { ConfirmationInterlock } from '../components/ConfirmationInterlock'

interface ComputerControlPageProps {
  sendMessage: (text: string) => void
}

function StatusIndicator({ verified }: { verified: boolean | null }) {
  if (verified === true) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono text-[#2EA069] bg-[#2EA069]/10 border border-[#2EA069]/30">
        <CheckCircle2 size={12} />
        <span>Verified</span>
      </span>
    )
  }
  if (verified === false) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono text-[#E2604E] bg-[#E2604E]/10 border border-[#E2604E]/30">
        <XCircle size={12} />
        <span>Failed</span>
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono text-[#D97736] bg-[#D97736]/10 border border-[#D97736]/30">
      <AlertTriangle size={12} />
      <span>Pending</span>
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

  // OS-agnostic path and application display
  const rawApp = computerContext.activeApp || ''
  const isExplorer =
    rawApp.toLowerCase().includes('explorer') ||
    rawApp.toLowerCase().includes('desktop') ||
    rawApp.toLowerCase().includes('file') ||
    rawApp.toLowerCase().includes('finder')

  const activeApp = rawApp || (computerContext.activeBrowser ? 'Browser' : 'Desktop')
  const activeWindow = computerContext.activeWindow || computerContext.windowTitle || 'Main Display'

  // Format directory to OS-agnostic syntax (e.g. ~/Desktop)
  const normalizePath = (p: string | null | undefined): string => {
    if (!p) return '~/Desktop'
    const clean = p.replace(/\\/g, '/')
    if (clean.includes('/Users/') || clean.includes('/home/')) {
      const parts = clean.split('/')
      const idx = parts.findIndex(part => part === 'Users' || part === 'home')
      if (idx !== -1 && parts[idx + 2]) {
        return `~/${parts.slice(idx + 2).join('/')}`
      }
    }
    return clean.startsWith('~') ? clean : `~/${clean.split('/').pop() || clean}`
  }

  const activeDirectory = normalizePath(computerContext.currentDirectory)
  const activeUrl = isExplorer
    ? activeDirectory
    : (computerContext.currentUrl || (computerContext.domain ? `https://${computerContext.domain}` : 'No active page'))

  return (
    <div className="flex flex-col h-full bg-[#0E1013] text-[#E1E4EA] overflow-hidden select-none">
      {/* Sub-Header Status Rail */}
      <div className="h-12 px-4 sm:px-6 border-b border-[#262B35] flex items-center justify-between shrink-0 bg-[#16191E] text-xs">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${computerState.isRunning ? 'bg-[#D97736] animate-pulse' : 'bg-[#2EA069]'}`} />
            <span className="font-semibold text-[#E1E4EA]">Mission Console</span>
          </div>
          <span className="text-[#828997]">|</span>
          <span className="text-[#828997] font-mono text-[11px] truncate">
            {computerState.isRunning ? 'Executing step sequence' : 'System standing by'}
          </span>
        </div>

        <div className="flex items-center gap-3 font-mono text-[11px]">
          <span className="text-[#828997] hidden sm:inline">Verification:</span>
          <StatusIndicator verified={computerState.lastVerified} />
        </div>
      </div>

      {/* Main 60/40 Console Layout (Stacks on mobile) */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* LEFT COLUMN: COMMAND & EXECUTION JOURNAL (60%) */}
        <div className="flex-1 md:w-3/5 flex flex-col border-b md:border-b-0 md:border-r border-[#262B35] overflow-hidden">
          {/* Scrollable Journal */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 scrollbar-thin">
            {/* Active Goal / Plan Card */}
            {computerState.planDescription ? (
              <div className="p-4 rounded bg-[#16191E] border border-[#262B35] space-y-3">
                <div className="flex items-center justify-between border-b border-[#262B35] pb-2 text-xs">
                  <span className="text-[#828997] font-mono text-[11px]">Active Plan</span>
                  {computerState.isRunning && (
                    <span className="text-[#D97736] font-mono text-[11px] flex items-center gap-1">
                      <Clock size={11} className="animate-spin" />
                      <span>Running</span>
                    </span>
                  )}
                </div>

                <p className="text-sm font-medium text-[#E1E4EA]">
                  {computerState.planDescription}
                </p>

                {/* Step List */}
                {computerState.steps.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    {computerState.steps.map((step, idx) => {
                      const isDone = idx < computerState.currentStepIdx || idx < computerState.stepResults.length
                      const isActive = idx === computerState.currentStepIdx && computerState.isRunning
                      const result = computerState.stepResults[idx]

                      return (
                        <div
                          key={idx}
                          className={`flex items-center gap-2.5 p-2 rounded border text-xs font-mono transition-colors ${
                            isActive
                              ? 'bg-[#D97736]/10 border-[#D97736]/40 text-[#E1E4EA]'
                              : isDone
                              ? result?.verified === false
                                ? 'bg-[#E2604E]/10 border-[#E2604E]/30 text-[#E2604E]'
                                : 'bg-[#16191E] border-[#262B35] text-[#828997]'
                              : 'bg-[#0E1013] border-[#262B35]/60 text-[#828997]/60'
                          }`}
                        >
                          <span className="w-4 text-center shrink-0">
                            {isDone ? (
                              result?.verified === false ? (
                                <XCircle size={13} className="text-[#E2604E]" />
                              ) : (
                                <Check size={13} className="text-[#2EA069]" />
                              )
                            ) : isActive ? (
                              <span className="text-[#D97736] animate-pulse">▶</span>
                            ) : (
                              '○'
                            )}
                          </span>

                          <span className="flex-1 truncate text-[11px] font-sans text-[#E1E4EA]">{step}</span>

                          {result && (
                            <span className="text-[10px] text-[#828997]">
                              {result.verified === false ? 'Failed' : 'Verified'}
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Output Response */}
                {computerState.lastResponse && (
                  <div className="mt-3 p-3 rounded bg-[#0E1013] border border-[#262B35] text-xs text-[#E1E4EA] font-sans leading-relaxed">
                    <span className="text-[#828997] font-mono text-[10px] block mb-1">
                      Assistant Report
                    </span>
                    {computerState.lastResponse}
                  </div>
                )}
              </div>
            ) : (
              <div className="p-8 text-center text-xs text-[#828997] space-y-4">
                <p>No task currently executing. Enter an instruction below to begin:</p>
                <div className="flex flex-wrap justify-center gap-2 max-w-md mx-auto">
                  {[
                    'Open Chrome and search GitHub',
                    'Open File Explorer to Desktop',
                    'List folders in my project directory',
                    'Find all recent PDF downloads',
                  ].map((sample, i) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(sample)}
                      className="px-2.5 py-1 rounded bg-[#16191E] hover:bg-[#262B35] border border-[#262B35] text-xs text-[#E1E4EA] transition-colors"
                    >
                      &ldquo;{sample}&rdquo;
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Bottom Command Input Bar */}
          <div className="p-3 border-t border-[#262B35] bg-[#16191E]">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                placeholder="Instruct Jarvis... (e.g. 'Open ~/Desktop and find report.pdf')"
                onKeyDown={handleKeyDown}
                className="flex-1 px-3 py-2 rounded bg-[#0E1013] border border-[#262B35] text-xs text-[#E1E4EA] placeholder-[#828997] focus-visible:ring-2 focus-visible:ring-[#D97736] focus-visible:outline-none"
              />
              <button
                onClick={handleSend}
                className="px-3.5 py-2 rounded bg-[#D97736] hover:bg-[#D97736]/90 text-[#0E1013] font-medium text-xs flex items-center gap-1.5 transition-colors"
              >
                <span>Send</span>
                <Send size={12} />
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: MACHINE TELEMETRY & CONFIRMATION INTERLOCK (40%) */}
        <div className="md:w-2/5 p-4 sm:p-6 space-y-4 overflow-y-auto scrollbar-thin bg-[#16191E]/40">
          {/* Active OS Focus Telemetry Bay */}
          <div className="border border-[#262B35] bg-[#16191E] rounded p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-[#262B35] pb-2 text-xs">
              <span className="font-semibold text-[#E1E4EA] flex items-center gap-1.5 font-sans">
                <AppWindow size={13} className="text-[#D97736]" />
                Active Machine Focus
              </span>
              <span className="text-[10px] font-mono text-[#828997]">Grounded Telemetry</span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 rounded bg-[#0E1013] border border-[#262B35]">
                <span className="text-[#828997] font-mono text-[10px] block">Application</span>
                <p className="font-semibold text-[#E1E4EA] truncate pt-0.5">{activeApp}</p>
              </div>

              <div className="p-2.5 rounded bg-[#0E1013] border border-[#262B35]">
                <span className="text-[#828997] font-mono text-[10px] block">Active Window</span>
                <p className="font-semibold text-[#E1E4EA] truncate pt-0.5" title={activeWindow}>{activeWindow}</p>
              </div>

              <div className="p-2.5 rounded bg-[#0E1013] border border-[#262B35] col-span-2">
                <span className="text-[#828997] font-mono text-[10px] block">
                  {isExplorer ? 'Working Directory' : 'Target URL'}
                </span>
                <p className="font-mono text-[#E1E4EA] text-[11px] truncate pt-0.5">{activeUrl}</p>
              </div>
            </div>
          </div>

          {/* Confirmation Interlock Gate (when required) */}
          {computerState.needsConfirm && (
            <ConfirmationInterlock
              request={{
                actionId: computerState.taskId || 'action_confirm_pending',
                tool: computerState.target || 'high_risk_action',
                target: activeUrl || computerState.target || '~/Desktop',
                blastRadius: computerState.blastRadius || computerState.lastResponse || 'Physical change on your local machine',
                dangerLevel: computerState.dangerLevel || 'high',
                confirmationTimeoutSeconds: computerState.confirmationTimeoutSeconds ?? 120,
                timeoutSeconds: computerState.timeoutSeconds ?? 30,
                onApprove: () => sendMessage('yes, confirm and send'),
                onDecline: () => sendMessage('cancel action'),
              }}
              isMobileSticky={true}
            />
          )}

          {/* Advanced Diagnostic Telemetry Accordion */}
          <div className="border border-[#262B35] bg-[#16191E] rounded overflow-hidden text-xs">
            <button
              onClick={() => setDebugOpen(!debugOpen)}
              className="w-full px-4 py-2.5 flex items-center justify-between text-left hover:bg-[#262B35]/50 transition-colors"
            >
              <span className="font-mono text-[11px] text-[#828997] flex items-center gap-1.5">
                <Terminal size={12} />
                <span>Protocol Telemetry</span>
              </span>
              <span className="text-[10px] font-mono text-[#828997]">
                {debugOpen ? 'Hide' : 'Inspect'}
              </span>
            </button>

            <AnimatePresence>
              {debugOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="border-t border-[#262B35] p-3 font-mono text-[11px] space-y-2 bg-[#0E1013]"
                >
                  <div className="grid grid-cols-2 gap-2 text-[#828997]">
                    <div>
                      <span>Intent:</span>{' '}
                      <span className="text-[#E1E4EA]">{computerState.intent || 'idle'}</span>
                    </div>
                    <div>
                      <span>Task ID:</span>{' '}
                      <span className="text-[#E1E4EA]">{computerState.taskId?.slice(0, 10) || 'none'}</span>
                    </div>
                    <div>
                      <span>Verified:</span>{' '}
                      <span className={computerState.lastVerified ? 'text-[#2EA069]' : 'text-[#828997]'}>
                        {String(computerState.lastVerified)}
                      </span>
                    </div>
                    <div>
                      <span>Step Count:</span>{' '}
                      <span className="text-[#E1E4EA]">{computerState.steps.length}</span>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  )
}
