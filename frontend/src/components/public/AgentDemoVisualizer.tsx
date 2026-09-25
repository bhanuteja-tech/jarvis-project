import { useState, useEffect } from 'react'
import {
  Mic,
  Cpu,
  Activity,
  CheckCircle2,
  Play,
  RotateCcw,
  Volume2,
  ShieldCheck,
  Terminal
} from 'lucide-react'

type AgentState = 'IDLE' | 'LISTENING' | 'THINKING' | 'ACTING' | 'SPEAKING'

interface Scenario {
  id: string
  label: string
  query: string
  audioDuration: number
  steps: {
    phase: string
    node: string
    output: string
    latency: string
    truthVerified: boolean
  }[]
  finalResponse: string
}

const DEMO_SCENARIOS: Scenario[] = [
  {
    id: 'discovery',
    label: 'Job Discovery & Radar',
    query: '"Jarvis, find Staff Backend or Distributed Systems roles in NYC or Remote, $190k+."',
    audioDuration: 3500,
    steps: [
      { phase: 'Phase 1', node: 'discover_jobs', output: 'Fetched 48 jobs from Greenhouse, Lever, and Google Jobs', latency: '42ms', truthVerified: true },
      { phase: 'Phase 1', node: 'deduplicate_jobs', output: 'Deduped 48 raw postings into 29 unique canonical opportunities', latency: '6ms', truthVerified: true },
      { phase: 'Phase 2', node: 'understand_jds', output: 'Extracted 114 explicit facts & skills with provenance markers', latency: '85ms', truthVerified: true },
      { phase: 'Phase 4', node: 'match_candidate', output: 'Applied deterministic 8-weight match; Tier: STRONG (88.4%)', latency: '12ms', truthVerified: true },
    ],
    finalResponse: 'Found 4 high-affinity matches led by Staff Distributed Systems Engineer at Datadog ($210k-$240k). All requirements verified against your profile evidence.',
  },
  {
    id: 'tailor',
    label: 'Resume Tailoring & Truth Guard',
    query: '"Tailor my resume for Anthropic Infrastructure Engineer without exaggerating my experience."',
    audioDuration: 3800,
    steps: [
      { phase: 'Phase 3', node: 'candidate_profile', output: 'Parsed profile: 8.5 yrs exp, Kubernetes, Rust, Distributed Storage', latency: '18ms', truthVerified: true },
      { phase: 'Phase 5', node: 'tailor_resume', output: 'Synthesized targeted summary & re-ordered 6 bullet highlights', latency: '110ms', truthVerified: true },
      { phase: 'Phase 6', node: 'validate_resume (T1-T10)', output: 'Token-containment confirmed: 100% facts ⊆ Candidate Evidence', latency: '15ms', truthVerified: true },
      { phase: 'Phase 6', node: 'ats_audit (A1-A8)', output: 'Coverage: 91% required, 0% keyword stuffing, PII quarantined', latency: '9ms', truthVerified: true },
    ],
    finalResponse: 'Resume tailored for Anthropic with 91% verified keyword coverage. T1-T10 mathematical truth guard verified zero invented facts.',
  },
  {
    id: 'barge_in',
    label: 'Realtime Voice & Interruption',
    query: '"Hold on Jarvis, filter out any roles requiring on-call rotations!"',
    audioDuration: 2900,
    steps: [
      { phase: 'FastIntent', node: 'voice_barge_in', output: 'Interruption token recognized; cancelled background audio playback', latency: '<18ms', truthVerified: true },
      { phase: 'FastIntent', node: 'filter_update', output: 'Injected negative constraint: exclude on_call=True', latency: '8ms', truthVerified: true },
      { phase: 'Phase 4', node: 'rerank_jobs', output: 'Re-ranked 29 jobs; 18 roles remain compliant with zero on-call', latency: '14ms', truthVerified: true },
    ],
    finalResponse: 'Understood. Immediately halted narration and excluded on-call roles. 18 qualified positions remain.',
  },
]

export function AgentDemoVisualizer() {
  const [activeScenario, setActiveScenario] = useState<Scenario>(DEMO_SCENARIOS[0])
  const [agentState, setAgentState] = useState<AgentState>('IDLE')
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(-1)
  const [transcript, setTranscript] = useState<string>('')
  const [interrupted, setInterrupted] = useState<boolean>(false)

  // Simulation execution loop
  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout>

    if (agentState === 'LISTENING') {
      timeoutId = setTimeout(() => {
        setTranscript(activeScenario.query)
        setAgentState('THINKING')
      }, 1400)
    } else if (agentState === 'THINKING') {
      timeoutId = setTimeout(() => {
        setAgentState('ACTING')
        setCurrentStepIndex(0)
      }, 800)
    } else if (agentState === 'ACTING') {
      if (currentStepIndex < activeScenario.steps.length - 1) {
        timeoutId = setTimeout(() => {
          setCurrentStepIndex((prev) => prev + 1)
        }, 550)
      } else {
        timeoutId = setTimeout(() => {
          setAgentState('SPEAKING')
        }, 600)
      }
    } else if (agentState === 'SPEAKING') {
      timeoutId = setTimeout(() => {
        setAgentState('IDLE')
      }, 4500)
    }

    return () => clearTimeout(timeoutId)
  }, [agentState, currentStepIndex, activeScenario])

  const startSimulation = (scenario: Scenario) => {
    setActiveScenario(scenario)
    setInterrupted(false)
    setCurrentStepIndex(-1)
    setTranscript('')
    setAgentState('LISTENING')
  }

  const triggerBargeIn = () => {
    setInterrupted(true)
    const bargeScenario = DEMO_SCENARIOS[2]
    setActiveScenario(bargeScenario)
    setCurrentStepIndex(-1)
    setTranscript(bargeScenario.query)
    setAgentState('THINKING')
  }

  const resetSimulation = () => {
    setAgentState('IDLE')
    setCurrentStepIndex(-1)
    setTranscript('')
    setInterrupted(false)
  }

  return (
    <div className="w-full rounded-2xl glass-strong border border-jarvis-border/60 shadow-2xl shadow-blue-950/40 overflow-hidden text-left relative">
      {/* Top Console Bar */}
      <div className="h-11 bg-jarvis-surface/80 border-b border-jarvis-border/50 px-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
          </div>
          <span className="text-[11px] font-mono text-jarvis-muted ml-2">jarvis_runtime_live_preview.ts</span>
        </div>

        {/* State Badge */}
        <div className="flex items-center gap-2">
          <div
            className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold flex items-center gap-1.5 transition-colors ${
              agentState === 'LISTENING'
                ? 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
                : agentState === 'THINKING'
                ? 'bg-blue-500/10 text-cyan-300 border border-cyan-500/30'
                : agentState === 'ACTING'
                ? 'bg-violet-500/10 text-violet-300 border border-violet-500/30'
                : agentState === 'SPEAKING'
                ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                : 'bg-jarvis-surface text-jarvis-muted border border-jarvis-border/40'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                agentState === 'IDLE' ? 'bg-jarvis-muted' : 'bg-current animate-ping'
              }`}
            />
            <span>{agentState}</span>
          </div>
          <span className="text-[10px] font-mono text-jarvis-muted/70 hidden sm:inline">180ms TTFT</span>
        </div>
      </div>

      {/* Main Visualizer Body */}
      <div className="p-5 lg:p-6 space-y-5">
        {/* Scenario Selectors */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-jarvis-muted font-mono mr-1 hidden sm:inline">Demo Scenarios:</span>
          {DEMO_SCENARIOS.map((sc) => (
            <button
              key={sc.id}
              onClick={() => startSimulation(sc)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                activeScenario.id === sc.id && agentState !== 'IDLE'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/25 border border-blue-400'
                  : 'bg-jarvis-surface/60 hover:bg-jarvis-surface text-jarvis-muted hover:text-white border border-jarvis-border/40'
              }`}
            >
              {sc.label}
            </button>
          ))}
          {agentState !== 'IDLE' && (
            <button
              onClick={resetSimulation}
              className="p-1.5 rounded-lg text-jarvis-muted hover:text-white bg-jarvis-surface/40 hover:bg-jarvis-surface ml-auto"
              title="Reset"
            >
              <RotateCcw size={13} />
            </button>
          )}
        </div>

        {/* Dynamic Voice Core & Transcript Box */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Visual AI Orb / Waveform panel */}
          <div className="col-span-1 p-4 rounded-xl bg-gradient-to-b from-jarvis-surface/60 to-jarvis-darker/60 border border-jarvis-border/40 flex flex-col items-center justify-center relative min-h-[170px] overflow-hidden">
            {/* Background energy circles */}
            <div
              className={`absolute w-28 h-28 rounded-full blur-2xl transition-all duration-700 ${
                agentState === 'SPEAKING'
                  ? 'bg-cyan-500/30 scale-125'
                  : agentState === 'THINKING'
                  ? 'bg-blue-600/30 scale-110'
                  : agentState === 'ACTING'
                  ? 'bg-violet-600/30 scale-115'
                  : agentState === 'LISTENING'
                  ? 'bg-amber-500/25 scale-105'
                  : 'bg-transparent'
              }`}
            />

            {/* Glowing Orb */}
            <div className="relative z-10 flex flex-col items-center gap-3">
              <div
                className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all duration-300 shadow-xl ${
                  agentState === 'SPEAKING'
                    ? 'bg-gradient-to-tr from-cyan-500 to-blue-600 shadow-cyan-500/40 scale-110 animate-pulse'
                    : agentState === 'LISTENING'
                    ? 'bg-gradient-to-tr from-amber-500 to-yellow-400 shadow-amber-500/30 scale-105'
                    : agentState === 'THINKING'
                    ? 'bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-blue-500/30 animate-spin'
                    : agentState === 'ACTING'
                    ? 'bg-gradient-to-tr from-violet-600 to-fuchsia-600 shadow-violet-500/30'
                    : 'bg-jarvis-surface border border-jarvis-border/60'
                }`}
              >
                {agentState === 'SPEAKING' ? (
                  <Volume2 size={24} className="text-white" />
                ) : agentState === 'LISTENING' ? (
                  <Mic size={24} className="text-slate-950 animate-bounce" />
                ) : agentState === 'THINKING' ? (
                  <Cpu size={24} className="text-white" />
                ) : agentState === 'ACTING' ? (
                  <Activity size={24} className="text-white" />
                ) : (
                  <Play size={20} className="text-blue-400 translate-x-0.5" />
                )}
              </div>

              {/* Dynamic Waveform Bars */}
              <div className="flex items-center gap-1 h-7">
                {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((bar) => {
                  const isActive = agentState === 'SPEAKING' || agentState === 'LISTENING'
                  return (
                    <span
                      key={bar}
                      className={`w-1 rounded-full transition-all duration-200 ${
                        isActive
                          ? bar % 2 === 0
                            ? 'bg-cyan-400 animate-waveform-1 h-6'
                            : 'bg-blue-500 animate-waveform-2 h-4'
                          : 'bg-jarvis-border h-1.5'
                      }`}
                    />
                  )
                })}
              </div>
            </div>

            {/* Quick Action Button */}
            {agentState === 'IDLE' && (
              <button
                onClick={() => startSimulation(activeScenario)}
                className="mt-2 text-xs font-semibold text-cyan-400 hover:text-cyan-300 flex items-center gap-1 relative z-10"
              >
                <span>Run Interactive Demo</span>
                <Play size={11} />
              </button>
            )}
            {agentState === 'SPEAKING' && (
              <button
                onClick={triggerBargeIn}
                className="mt-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/30 relative z-10 transition-colors"
              >
                Test Barge-in (Interrupt)
              </button>
            )}
          </div>

          {/* Transcript and Speech Bubble */}
          <div className="col-span-2 p-4 rounded-xl bg-jarvis-darker/70 border border-jarvis-border/40 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-[11px] text-jarvis-muted mb-2 font-mono">
                <span className="flex items-center gap-1.5">
                  <Mic size={12} className="text-blue-400" />
                  <span>VOICE INPUT STREAM</span>
                </span>
                {interrupted && (
                  <span className="text-red-400 font-semibold text-[10px] px-1.5 py-0.2 rounded bg-red-500/10 border border-red-500/20">
                    Barge-in Interruption Detected
                  </span>
                )}
              </div>

              <div className="min-h-[44px] flex items-center">
                {agentState === 'IDLE' ? (
                  <p className="text-xs text-jarvis-muted italic">
                    Click "Run Interactive Demo" or select a scenario above to test JARVIS voice and autonomous execution.
                  </p>
                ) : agentState === 'LISTENING' ? (
                  <div className="flex items-center gap-2 text-amber-300 text-sm font-medium">
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                    <span>Listening to vocal intent...</span>
                  </div>
                ) : (
                  <p className="text-sm text-white font-medium italic">
                    {transcript || activeScenario.query}
                  </p>
                )}
              </div>
            </div>

            {/* Final Agent Speech Output */}
            <div className="mt-3 pt-3 border-t border-jarvis-border/30">
              <div className="text-[11px] text-jarvis-muted font-mono mb-1 flex items-center gap-1">
                <Activity size={12} className="text-cyan-400" />
                <span>JARVIS RESPONSE</span>
              </div>
              <p
                className={`text-xs leading-relaxed transition-opacity ${
                  agentState === 'SPEAKING' ? 'text-cyan-200 font-medium' : 'text-jarvis-muted'
                }`}
              >
                {agentState === 'SPEAKING'
                  ? activeScenario.finalResponse
                  : agentState === 'ACTING' || agentState === 'THINKING'
                  ? 'Computing deterministic LangGraph transitions...'
                  : activeScenario.finalResponse}
              </p>
            </div>
          </div>
        </div>

        {/* Observable Pipeline Execution Stream */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-mono text-jarvis-muted">
            <span className="flex items-center gap-1.5">
              <Terminal size={12} className="text-violet-400" />
              <span>LANGGRAPH DETERMINISTIC EXECUTION STREAM</span>
            </span>
            <span className="text-[10px]">Zero Hallucination Guaranteed</span>
          </div>

          <div className="space-y-1.5 bg-black/40 rounded-xl p-3 border border-jarvis-border/40 font-mono text-[11px]">
            {activeScenario.steps.map((step, idx) => {
              const isDone = currentStepIndex >= idx
              const isCurrent = currentStepIndex === idx && agentState === 'ACTING'
              return (
                <div
                  key={step.node}
                  className={`p-2 rounded-lg transition-all flex items-center justify-between gap-3 ${
                    isCurrent
                      ? 'bg-blue-950/60 border border-blue-500/50 text-white'
                      : isDone
                      ? 'bg-jarvis-surface/40 text-jarvis-light border border-jarvis-border/20'
                      : 'text-jarvis-muted/40 border border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {isDone ? (
                      <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                    ) : isCurrent ? (
                      <span className="w-3 h-3 rounded-full border-2 border-cyan-400 border-t-transparent animate-spin shrink-0" />
                    ) : (
                      <div className="w-3 h-3 rounded-full border border-jarvis-muted/30 shrink-0" />
                    )}
                    <span className="text-[10px] px-1 py-0.2 rounded bg-jarvis-surface font-semibold text-cyan-300">
                      {step.phase}
                    </span>
                    <span className="font-semibold text-white/90">{step.node}:</span>
                    <span className="truncate text-jarvis-muted">{step.output}</span>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {step.truthVerified && (
                      <span className="flex items-center gap-1 text-[10px] text-emerald-400 hidden sm:flex">
                        <ShieldCheck size={11} />
                        <span>Truth Verified</span>
                      </span>
                    )}
                    <span className="text-[10px] text-jarvis-muted bg-jarvis-surface/80 px-1.5 py-0.5 rounded">
                      {step.latency}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
