import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  ShieldAlert,
  ShieldCheck,
  Check,
  X,
  Clock,
  Terminal,
  Laptop,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Eye,
  Key
} from 'lucide-react'

export function LandingPage() {
  // Interactive Safety Simulator state (default 120s confirmation review budget)
  const [simState, setSimState] = useState<'pending' | 'declined' | 'authorized'>('pending')
  const [simTimer, setSimTimer] = useState<number>(120)

  useEffect(() => {
    if (simState !== 'pending') return
    const interval = setInterval(() => {
      setSimTimer((t) => {
        if (t <= 1) {
          setSimState('declined')
          return 0
        }
        return t - 1
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [simState])

  const handleResetSim = () => {
    setSimState('pending')
    setSimTimer(120)
  }

  return (
    <div className="min-h-screen bg-[#0E1013] text-[#E1E4EA] selection:bg-[#D97736]/20 selection:text-[#E1E4EA]">
      {/* Top Engineering Rail */}
      <div className="border-b border-[#262B35] bg-[#16191E] px-4 sm:px-8 py-3 text-xs flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#2EA069]" />
            <span className="font-semibold tracking-wide text-[#E1E4EA]">JARVIS</span>
          </div>
          <span className="text-[#828997] hidden sm:inline">|</span>
          <span className="text-[#828997] font-mono text-[11px] hidden sm:inline">
            Local Computer Controller
          </span>
        </div>

        <div className="flex items-center gap-4 text-[#828997] text-[11px]">
          <span className="hidden md:inline font-mono">Device-Bound Security</span>
          <Link
            to="/docs"
            className="hover:text-[#E1E4EA] transition-colors"
          >
            Safety Docs
          </Link>
          <Link
            to="/app/computer"
            className="text-[#D97736] hover:underline font-medium"
          >
            Open Console →
          </Link>
        </div>
      </div>

      {/* Main Content Area */}
      <main className="max-w-6xl mx-auto px-4 sm:px-8 py-12 md:py-16 space-y-20">
        {/* 1. HERO SECTION (Strict Left-Aligned) */}
        <section className="space-y-6 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded bg-[#16191E] border border-[#262B35] text-xs font-mono text-[#D97736]">
            <ShieldCheck size={14} />
            <span>Permission-Gated Autonomous Agent</span>
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight text-[#E1E4EA] leading-[1.15] font-sans">
            An autonomous agent with hands on your computer. <br className="hidden sm:inline" />
            <span className="text-[#828997]">Governed by your explicit permission.</span>
          </h1>

          <p className="text-base sm:text-lg text-[#828997] leading-relaxed max-w-2xl font-normal">
            You instruct in plain voice or text. Jarvis operates your browser, organizes your filesystem,
            and runs desktop tools directly on your physical machine. When an action could delete data,
            send a message, or modify system files, it halts and waits for your confirmation.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              to="/app/computer"
              className="px-5 py-2.5 rounded bg-[#D97736] hover:bg-[#D97736]/90 text-[#0E1013] font-medium text-sm flex items-center gap-2 transition-colors focus-visible:ring-2 focus-visible:ring-[#D97736]"
            >
              <span>Open Control Console</span>
              <ArrowRight size={15} />
            </Link>

            <a
              href="#safety-interlock"
              className="px-4 py-2.5 rounded bg-[#16191E] hover:bg-[#262B35] text-[#E1E4EA] border border-[#262B35] text-sm font-medium transition-colors"
            >
              How Permission Works
            </a>
          </div>
        </section>

        {/* 2. THE LIVE SAFETY INTERLOCK SIMULATOR */}
        <section id="safety-interlock" className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold tracking-wide text-[#E1E4EA] font-sans">
                The Confirmation Barrier in Action
              </h2>
              <p className="text-xs text-[#828997]">
                Try the exact decision screen that appears before high-risk actions execute on your computer.
              </p>
            </div>
            {simState !== 'pending' && (
              <button
                onClick={handleResetSim}
                className="text-xs text-[#D97736] hover:underline font-mono"
              >
                Reset demo
              </button>
            )}
          </div>

          <div className="border border-[#262B35] bg-[#16191E] rounded p-5 space-y-4">
            {simState === 'pending' ? (
              <div className="space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-[#262B35] gap-2">
                  <div className="flex items-center gap-2">
                    <span className="p-1 rounded bg-[#D97736]/15 text-[#D97736]">
                      <ShieldAlert size={16} />
                    </span>
                    <div>
                      <span className="text-xs font-semibold text-[#E1E4EA]">
                        Confirmation Required: Destructive Action
                      </span>
                      <p className="text-[11px] text-[#828997]">
                        The local agent has suspended execution until you approve or decline.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#0E1013] border border-[#262B35] font-mono text-[11px] text-[#D97736] self-start sm:self-auto">
                    <Clock size={12} className="animate-pulse" />
                    <span>{simTimer}s until automatic timeout</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs bg-[#0E1013] p-3 rounded border border-[#262B35]">
                  <div>
                    <span className="text-[#828997] block font-mono text-[11px]">Command</span>
                    <span className="font-mono text-[#E1E4EA]">delete_directory</span>
                  </div>
                  <div>
                    <span className="text-[#828997] block font-mono text-[11px]">Target path</span>
                    <span className="font-mono text-[#E1E4EA]">~/Projects/drafts</span>
                  </div>
                  <div>
                    <span className="text-[#828997] block font-mono text-[11px]">Blast radius</span>
                    <span className="text-[#E2604E] font-medium">14 files permanently removed</span>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 pt-2">
                  <button
                    onClick={() => setSimState('declined')}
                    className="flex items-center gap-2 px-4 py-2 text-xs font-medium text-[#E1E4EA] bg-[#0E1013] hover:bg-[#262B35] border border-[#262B35] rounded transition-colors"
                  >
                    <X size={14} className="text-[#E2604E]" />
                    <span>Decline action</span>
                    <kbd className="px-1 text-[9px] font-mono text-[#828997] bg-[#16191E] rounded border border-[#262B35]">
                      Esc
                    </kbd>
                  </button>

                  <button
                    onClick={() => setSimState('authorized')}
                    className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#0E1013] bg-[#D97736] hover:bg-[#D97736]/90 rounded transition-colors"
                  >
                    <Check size={14} />
                    <span>Authorize execution</span>
                    <kbd className="px-1 text-[9px] font-mono text-[#0E1013]/80 bg-white/20 rounded">
                      Enter
                    </kbd>
                  </button>
                </div>
              </div>
            ) : simState === 'declined' ? (
              <div className="p-4 rounded bg-[#E2604E]/10 border border-[#E2604E]/30 text-xs space-y-2">
                <div className="flex items-center gap-2 text-[#E2604E] font-medium">
                  <XCircle size={16} />
                  <span>Action declined by user — task aborted cleanly.</span>
                </div>
                <p className="text-[#828997] text-[11px]">
                  Zero files were modified on your filesystem. The agent dropped the queued step, returned to standby, and reported the cancellation safely.
                </p>
              </div>
            ) : (
              <div className="p-4 rounded bg-[#2EA069]/10 border border-[#2EA069]/30 text-xs space-y-2">
                <div className="flex items-center gap-2 text-[#2EA069] font-medium">
                  <CheckCircle2 size={16} />
                  <span>Action authorized — execution completed and verified.</span>
                </div>
                <p className="text-[#828997] text-[11px]">
                  The local agent executed the deletion on your machine and inspected the directory to verify the outcome before reporting back.
                </p>
              </div>
            )}
          </div>
        </section>

        {/* 3. UNNUMBERED TRIPTYCH: THE THREE ARCHITECTURAL GUARANTEES */}
        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold tracking-wide text-[#E1E4EA] font-sans">
              Three Architectural Guarantees
            </h2>
            <p className="text-xs text-[#828997]">
              Engineered constraints that make granting computer control safe.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 border border-[#262B35] divide-y md:divide-y-0 md:divide-x divide-[#262B35] bg-[#16191E] rounded">
            {/* Card 1: Local Machine Execution */}
            <div className="p-5 space-y-3">
              <div className="w-8 h-8 rounded bg-[#0E1013] border border-[#262B35] flex items-center justify-center text-[#828997]">
                <Laptop size={16} />
              </div>
              <h3 className="text-sm font-semibold text-[#E1E4EA]">Local machine execution</h3>
              <p className="text-xs text-[#828997] leading-relaxed">
                Jarvis operates directly on your physical machine through the lightweight local agent (<code className="text-[#E1E4EA] font-mono text-[11px]">jarvis_agent</code>). Your personal files, cookies, and local credentials stay on your laptop and are never uploaded to a shared server.
              </p>
            </div>

            {/* Card 2: Physical Human Veto */}
            <div className="p-5 space-y-3">
              <div className="w-8 h-8 rounded bg-[#0E1013] border border-[#262B35] flex items-center justify-center text-[#D97736]">
                <Key size={16} />
              </div>
              <h3 className="text-sm font-semibold text-[#E1E4EA]">Physical human veto</h3>
              <p className="text-xs text-[#828997] leading-relaxed">
                Destructive operations (deleting files, dispatching external messages, running scripts) freeze and wait for your explicit authorization. Automatic approval cannot be enabled by default and requires a deliberate safety flag.
              </p>
            </div>

            {/* Card 3: Zero-Guess Grounding */}
            <div className="p-5 space-y-3">
              <div className="w-8 h-8 rounded bg-[#0E1013] border border-[#262B35] flex items-center justify-center text-[#2EA069]">
                <Eye size={16} />
              </div>
              <h3 className="text-sm font-semibold text-[#E1E4EA]">Zero-guess grounding</h3>
              <p className="text-xs text-[#828997] leading-relaxed">
                The agent never assumes an action succeeded. It inspects verified window titles, process IDs, and filesystem changes before and after every step. If reality does not match the expected state, it stops and asks.
              </p>
            </div>
          </div>
        </section>

        {/* 4. WHAT HAPPENS WHEN THINGS GO WRONG */}
        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold tracking-wide text-[#E1E4EA] font-sans">
              What Happens When Things Go Wrong
            </h2>
            <p className="text-xs text-[#828997]">
              Real-world computers experience sleep modes, Wi-Fi drops, and accidental inputs. Here is how Jarvis behaves under pressure.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded bg-[#16191E] border border-[#262B35] space-y-2 text-xs">
              <span className="font-semibold text-[#E1E4EA] flex items-center gap-2">
                <Clock size={14} className="text-[#D97736]" />
                When your connection drops mid-task
              </span>
              <p className="text-[#828997] leading-relaxed text-[11px]">
                A 15-second grace period timer starts. If your computer wakes or Wi-Fi reconnects within that window, your task resumes seamlessly. If the deadline expires without reconnection, all pending in-flight tasks fail safe rather than executing blindly.
              </p>
            </div>

            <div className="p-4 rounded bg-[#16191E] border border-[#262B35] space-y-2 text-xs">
              <span className="font-semibold text-[#E1E4EA] flex items-center gap-2">
                <Laptop size={14} className="text-[#2EA069]" />
                When another device logs in
              </span>
              <p className="text-[#828997] leading-relaxed text-[11px]">
                Every connection is bound to a persistent hardware device identifier. A second laptop under your account cannot silently hijack or resolve actions meant for your primary machine; duplicate registrations are rejected with policy violations.
              </p>
            </div>

            <div className="p-4 rounded bg-[#16191E] border border-[#262B35] space-y-2 text-xs">
              <span className="font-semibold text-[#E1E4EA] flex items-center gap-2">
                <AlertTriangle size={14} className="text-[#E2604E]" />
                When an action fails or gets stuck
              </span>
              <p className="text-[#828997] leading-relaxed text-[11px]">
                Instead of retrying in a loop or fabricating a completion report, the circuit breaker opens, drops remaining queued steps, and reports the exact operating system error back to you so you stay in control.
              </p>
            </div>

            <div className="p-4 rounded bg-[#16191E] border border-[#262B35] space-y-2 text-xs">
              <span className="font-semibold text-[#E1E4EA] flex items-center gap-2">
                <Terminal size={14} className="text-[#828997]" />
                When you speak while Jarvis is talking
              </span>
              <p className="text-[#828997] leading-relaxed text-[11px]">
                Audio generation cuts off in under 18ms the instant you start speaking. The agent halts its narration immediately, listens to your correction, and adapts without requiring you to wait for a long voice prompt to finish.
              </p>
            </div>
          </div>
        </section>

        {/* 5. HONEST COMPARISON */}
        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold tracking-wide text-[#E1E4EA] font-sans">
              How Jarvis Compares
            </h2>
            <p className="text-xs text-[#828997]">
              Why direct computer control requires an architecture fundamentally different from cloud chatbots.
            </p>
          </div>

          <div className="border border-[#262B35] bg-[#16191E] rounded overflow-hidden text-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-[#262B35] bg-[#0E1013] text-[#828997] font-mono text-[11px]">
                    <th className="p-3 font-medium">Capability</th>
                    <th className="p-3 font-medium text-[#D97736]">Jarvis</th>
                    <th className="p-3 font-medium">Cloud Chatbots</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#262B35] text-[#828997]">
                  <tr>
                    <td className="p-3 font-medium text-[#E1E4EA]">Machine Execution</td>
                    <td className="p-3 text-[#2EA069]">Runs on your actual OS via local agent</td>
                    <td className="p-3">Isolated cloud sandbox with no local access</td>
                  </tr>
                  <tr>
                    <td className="p-3 font-medium text-[#E1E4EA]">High-Risk Veto</td>
                    <td className="p-3 text-[#2EA069]">Physical confirmation prompt for deletions/sends</td>
                    <td className="p-3">N/A (cannot touch real files)</td>
                  </tr>
                  <tr>
                    <td className="p-3 font-medium text-[#E1E4EA]">State Grounding</td>
                    <td className="p-3 text-[#2EA069]">Inspects real HWNDs, URLs, and folders</td>
                    <td className="p-3">Guesses state from prompt memory</td>
                  </tr>
                  <tr>
                    <td className="p-3 font-medium text-[#E1E4EA]">Voice Barge-in</td>
                    <td className="p-3 text-[#2EA069]">Instant sub-18ms interruption cutoff</td>
                    <td className="p-3">Audio must finish before next turn</td>
                  </tr>
                  <tr>
                    <td className="p-3 font-medium text-[#E1E4EA]">Device Identity</td>
                    <td className="p-3 text-[#2EA069]">Hardware-bound token prevents cross-machine takeovers</td>
                    <td className="p-3">Shared web session without device gating</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* 6. LOCAL AGENT QUICKSTART */}
        <section className="p-5 rounded bg-[#16191E] border border-[#262B35] space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#E1E4EA] font-sans">
              Connect Your Machine
            </h2>
            <span className="text-[11px] font-mono text-[#828997]">CLI Quickstart</span>
          </div>

          <p className="text-xs text-[#828997]">
            Launch the local companion on your computer. It connects securely over WebSocket to receive and execute approved actions.
          </p>

          <div className="p-3 rounded bg-[#0E1013] border border-[#262B35] font-mono text-xs text-[#E1E4EA] flex items-center justify-between overflow-x-auto">
            <code>pip install -e . && python -m jarvis_agent.cli --session-id &lt;session&gt; --token &lt;token&gt;</code>
          </div>
        </section>
      </main>

      {/* Bottom Footer */}
      <footer className="border-t border-[#262B35] py-6 px-4 sm:px-8 text-xs text-[#828997] bg-[#16191E]">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#2EA069]" />
            <span>JARVIS Autonomous Computer Control — Verified Execution Architecture</span>
          </div>
          <div className="flex items-center gap-4 text-[11px]">
            <Link to="/app/computer" className="hover:text-[#E1E4EA]">Control Console</Link>
            <Link to="/docs" className="hover:text-[#E1E4EA]">Documentation</Link>
            <Link to="/features" className="hover:text-[#E1E4EA]">Capabilities</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
