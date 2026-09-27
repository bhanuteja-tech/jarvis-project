import { useEffect, useState } from 'react'
import { Clock, X, Check, ShieldAlert } from 'lucide-react'

export interface ConfirmationRequest {
  actionId: string
  tool: string
  target: string
  params?: Record<string, any>
  dangerLevel?: 'high' | 'medium' | 'critical'
  blastRadius?: string
  confirmationTimeoutSeconds?: number
  timeoutSeconds?: number
  onApprove: (actionId: string) => void
  onDecline: (actionId: string) => void
}

interface ConfirmationInterlockProps {
  request: ConfirmationRequest | null
  className?: string
  isMobileSticky?: boolean
}

export function ConfirmationInterlock({
  request,
  className = '',
  isMobileSticky = false,
}: ConfirmationInterlockProps) {
  // Authoritative human review countdown (default 120s per backend protocol)
  const [secondsRemaining, setSecondsRemaining] = useState<number>(120)

  useEffect(() => {
    if (!request) return
    // Read confirmation_timeout_seconds from the live action payload; do not use execution timeout
    const initialTime = request.confirmationTimeoutSeconds ?? 120
    setSecondsRemaining(initialTime)

    const timer = setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timer)
          request.onDecline(request.actionId)
          return 0
        }
        return prev - 1
      })
    }, 1000)

    // Global keyboard listener for instant human veto or approval
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        request.onDecline(request.actionId)
      } else if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        request.onApprove(request.actionId)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      clearInterval(timer)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [request])

  if (!request) return null

  const isCritical = request.dangerLevel === 'critical' || request.tool.includes('delete')

  const containerClasses = isMobileSticky
    ? 'fixed bottom-0 inset-x-0 z-50 border-t-2 border-[#D97736] bg-[#16191E] shadow-2xl p-4 md:static md:border md:rounded md:shadow-none'
    : 'border-l-4 border-l-[#D97736] border border-[#262B35] bg-[#16191E] rounded p-4 shadow-lg'

  return (
    <div className={`${containerClasses} ${className} text-[#E1E4EA]`}>
      {/* Top Banner: Status & Clock */}
      <div className="flex items-center justify-between pb-3 border-b border-[#262B35]">
        <div className="flex items-center gap-2">
          <span className="p-1 rounded bg-[#D97736]/15 text-[#D97736]">
            <ShieldAlert size={16} />
          </span>
          <div>
            <h4 className="text-xs font-semibold tracking-wide text-[#E1E4EA] font-sans">
              Action Requires Human Approval
            </h4>
            <p className="text-[11px] text-[#828997]">
              Safety barrier active on your local machine
            </p>
          </div>
        </div>

        {/* Real-time countdown timer */}
        <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#0E1013] border border-[#262B35] font-mono text-[11px] text-[#D97736]">
          <Clock size={12} className="animate-pulse" />
          <span>{secondsRemaining}s remaining</span>
        </div>
      </div>

      {/* Target & Blast Radius Body */}
      <div className="py-3 space-y-2 text-xs">
        <div className="flex items-start justify-between gap-2">
          <span className="text-[#828997] font-mono text-[11px] w-20 shrink-0">Command:</span>
          <span className="font-mono font-medium text-[#E1E4EA] bg-[#0E1013] px-2 py-0.5 rounded border border-[#262B35] truncate flex-1">
            {request.tool}
          </span>
        </div>

        <div className="flex items-start justify-between gap-2">
          <span className="text-[#828997] font-mono text-[11px] w-20 shrink-0">Target:</span>
          <span className="font-mono text-[#E1E4EA] bg-[#0E1013] px-2 py-0.5 rounded border border-[#262B35] break-all flex-1">
            {request.target}
          </span>
        </div>

        <div className="flex items-start justify-between gap-2">
          <span className="text-[#828997] font-mono text-[11px] w-20 shrink-0">Impact:</span>
          <span
            className={`font-sans font-medium text-[11px] ${
              isCritical ? 'text-[#E2604E]' : 'text-[#D97736]'
            }`}
          >
            {request.blastRadius || (isCritical ? 'Permanent alteration to local files' : 'Dispatches active external side-effect')}
          </span>
        </div>
      </div>

      {/* Primary Action Buttons with Keyboard Accents */}
      <div className="pt-3 border-t border-[#262B35] flex items-center justify-end gap-3">
        <button
          onClick={() => request.onDecline(request.actionId)}
          className="flex-1 md:flex-none flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-[#E1E4EA] bg-[#0E1013] hover:bg-[#262B35] border border-[#262B35] rounded transition-colors focus-visible:ring-2 focus-visible:ring-[#E2604E]"
          title="Press Escape to reject action"
        >
          <X size={14} className="text-[#E2604E]" />
          <span>Decline</span>
          <kbd className="hidden md:inline px-1 py-0.5 text-[9px] font-mono text-[#828997] bg-[#16191E] rounded border border-[#262B35]">
            Esc
          </kbd>
        </button>

        <button
          onClick={() => request.onApprove(request.actionId)}
          className="flex-1 md:flex-none flex items-center justify-center gap-2 px-4 py-2 text-xs font-semibold text-[#0E1013] bg-[#D97736] hover:bg-[#D97736]/90 rounded transition-colors focus-visible:ring-2 focus-visible:ring-[#D97736]"
          title="Press Enter to approve execution"
        >
          <Check size={14} />
          <span>Authorize</span>
          <kbd className="hidden md:inline px-1 py-0.5 text-[9px] font-mono text-[#0E1013]/80 bg-white/20 rounded">
            Enter
          </kbd>
        </button>
      </div>
    </div>
  )
}
