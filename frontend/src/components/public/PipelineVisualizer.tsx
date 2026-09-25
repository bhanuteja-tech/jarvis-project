import { useState } from 'react'
import {
  CheckCircle2,
  Search,
  Filter,
  FileSearch,
  UserCheck,
  Target,
  FileEdit,
  BadgeCheck,
  FileDown
} from 'lucide-react'

interface Stage {
  phase: string
  title: string
  icon: any
  stateKey: string
  description: string
  rules: string[]
  outputType: string
}

const STAGES: Stage[] = [
  {
    phase: 'Phase 1.1',
    title: 'Multi-Source Radar',
    icon: Search,
    stateKey: 'jobs: Job[]',
    description: 'Concurrent asynchronous fetching across Greenhouse, Lever public postings, and Google Jobs with jittered backoff.',
    rules: [
      'Bare-array envelopes only for Lever (rejects v1 authenticated format)',
      'Time_period parameter dropped on Google Jobs to prevent quota corruption',
      'No manufactured timestamps; source_created_at stays None if absent',
    ],
    outputType: 'Canonical Job[] with source provenance',
  },
  {
    phase: 'Phase 1.2',
    title: 'Cross-Source Deduplication',
    icon: Filter,
    stateKey: 'jobs: Job[] (deduped)',
    description: 'Deterministic clustering based on normalized employer domain, clean title stems, and geocoded location tokens.',
    rules: [
      'Preserves the earliest observed source while merging secondary application URLs',
      'Prevents identical multi-board syndications from distorting top-K rankings',
      'Zero loss of original metadata tags or posting links',
    ],
    outputType: 'Deduped canonical Job[]',
  },
  {
    phase: 'Phase 2',
    title: 'Untrusted JD Understanding',
    icon: FileSearch,
    stateKey: 'jd_analyses: Record<string, JDAnalysis>',
    description: 'Deterministic section, skill, experience, and education extraction. JD content is treated as untrusted data.',
    rules: [
      'Strip script/style tags and cap input size to prevent prompt-injection attacks',
      'Every extracted fact carries Evidence{text, field, method, confidence}',
      'Skills mapped from curated taxonomy; negative context guards prevent false matches',
    ],
    outputType: 'JDAnalysis with evidence provenance',
  },
  {
    phase: 'Phase 3',
    title: 'Candidate Profile & PII Quarantine',
    icon: UserCheck,
    stateKey: 'candidate_profile: CandidateProfile',
    description: 'Structured resume parsing with strict PII boundary isolation and explicit duration coverage calculation.',
    rules: [
      'PII (email, phone, address) quarantined immediately into non-narration storage',
      'Total years experience calculated ONLY when ≥80% duration coverage exists',
      'Deterministic taxonomy normalization across 400+ tech competencies',
    ],
    outputType: 'CandidateProfile (PII-quarantined)',
  },
  {
    phase: 'Phase 4',
    title: '8-Factor Deterministic Match',
    icon: Target,
    stateKey: 'match_results: MatchResult[]',
    description: 'Transparent mathematical scoring without black-box embeddings or unverifiable ranking models.',
    rules: [
      'Required Skills: 30pts · Preferred Skills: 10pts · Experience: 20pts',
      'Location: 12pts · Employment Type: 10pts · Education: 8pts · Level: 5pts · Salary: 5pts',
      'Tiers: Strong (≥75%), Moderate (≥50%), Gaps explicitly labeled',
    ],
    outputType: 'MatchResult[] with full scoring breakdown',
  },
  {
    phase: 'Phase 5',
    title: 'Sovereign Resume Tailoring',
    icon: FileEdit,
    stateKey: 'tailored_resume: TailoredResume',
    description: 'Dynamic section selection, highlight prioritization, and template summary synthesis from candidate evidence only.',
    rules: [
      'Original CandidateProfile is immutable source of truth (never mutated)',
      'Forbidden: inserting missing skills, inventing dates, or keyword stuffing',
      'Unaddressed requirements are surfaced separately to candidate, NEVER injected',
    ],
    outputType: 'TailoredResume artifact',
  },
  {
    phase: 'Phase 6',
    title: 'T1–T10 Truth & A1–A8 ATS Audit',
    icon: BadgeCheck,
    stateKey: 'validation_report: ValidationReport',
    description: 'Read-only mathematical verification. Token containment guard verifies that tailored content is a strict subset of evidence.',
    rules: [
      'T1-T10 Truth Checks (token containment, evidence resolvability) => FAIL if violated',
      'A1-A8 ATS Checks (coverage %, section order, keyword density caps) => WARN at most',
      'T9 PII Check: counts only reported; sensitive values never stored or echoed',
    ],
    outputType: 'ValidationReport (PASS/FAIL + Coverage metrics)',
  },
  {
    phase: 'Phase 7',
    title: 'PDF Studio & Agent Narration',
    icon: FileDown,
    stateKey: 'live_stream: WebSocket Update',
    description: 'Full-screen vector PDF generation with one-click export and synchronized voice summary.',
    rules: [
      'Instant typography and spacing adjustment with live ATS compatibility scores',
      'One-click PDF download with ATS-safe vector typography and clean margins',
      'Voice agent provides real-time verbal summary of top matches and validation status',
    ],
    outputType: 'Exportable PDF & Realtime Voice',
  },
]

export function PipelineVisualizer() {
  const [activeStage, setActiveStage] = useState<number>(4)

  const stage = STAGES[activeStage]
  const Icon = stage.icon

  return (
    <div className="w-full rounded-2xl glass-strong border border-jarvis-border/60 p-6 sm:p-8 space-y-6 text-left">
      <div>
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded bg-blue-500/10 text-cyan-400 font-mono text-[11px] border border-blue-500/20 font-semibold">
            LANGGRAPH PIPELINE
          </span>
          <h3 className="text-lg font-bold text-white">The 8-Stage Frozen Execution Pipeline</h3>
        </div>
        <p className="text-xs text-jarvis-muted mt-1">
          Every job search and tailoring run traverses this strict LangGraph state machine. No unverified hops, no hallucinations.
        </p>
      </div>

      {/* Horizontal Stage Stepper */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        {STAGES.map((s, idx) => {
          const isCurrent = activeStage === idx
          const isPassed = activeStage > idx
          const StageIcon = s.icon

          return (
            <button
              key={s.phase}
              onClick={() => setActiveStage(idx)}
              className={`p-3 rounded-xl flex flex-col items-center text-center transition-all border ${
                isCurrent
                  ? 'bg-blue-600/20 border-cyan-400 shadow-lg shadow-cyan-500/20 scale-[1.03]'
                  : isPassed
                  ? 'bg-jarvis-surface/70 border-jarvis-border/40 text-cyan-300'
                  : 'bg-jarvis-surface/30 border-jarvis-border/20 text-jarvis-muted/70 hover:bg-jarvis-surface/50'
              }`}
            >
              <div
                className={`w-7 h-7 rounded-lg flex items-center justify-center mb-2 transition-colors ${
                  isCurrent ? 'bg-cyan-500 text-slate-950 font-bold' : isPassed ? 'bg-blue-500/20 text-cyan-400' : 'bg-jarvis-surface text-jarvis-muted'
                }`}
              >
                <StageIcon size={14} />
              </div>
              <span className="text-[10px] font-mono font-semibold block">{s.phase}</span>
              <span className="text-[11px] font-medium text-white line-clamp-1 mt-0.5">{s.title}</span>
            </button>
          )
        })}
      </div>

      {/* Stage Detail Card */}
      <div className="p-6 rounded-2xl bg-gradient-to-br from-jarvis-surface/80 to-jarvis-darker/90 border border-jarvis-border/60 grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-cyan-500 flex items-center justify-center text-white shadow-lg shadow-blue-500/30">
              <Icon size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-cyan-400">{stage.phase}</span>
                <span className="text-xs text-jarvis-muted">·</span>
                <h4 className="text-base font-bold text-white">{stage.title}</h4>
              </div>
              <span className="text-[11px] font-mono text-jarvis-muted bg-black/40 px-2 py-0.5 rounded mt-1 inline-block">
                State Key: {stage.stateKey}
              </span>
            </div>
          </div>

          <p className="text-sm text-jarvis-light leading-relaxed">{stage.description}</p>

          <div className="space-y-2 pt-2">
            <span className="text-xs font-mono font-semibold uppercase tracking-wider text-jarvis-muted block">
              Execution Constraints & Truth Guards:
            </span>
            <ul className="space-y-1.5">
              {stage.rules.map((rule, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-jarvis-muted">
                  <CheckCircle2 size={13} className="text-emerald-400 shrink-0 mt-0.5" />
                  <span>{rule}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Right Info Box */}
        <div className="p-4 rounded-xl bg-black/40 border border-jarvis-border/40 flex flex-col justify-between space-y-4">
          <div className="space-y-3">
            <div className="text-xs font-mono text-jarvis-muted uppercase tracking-wider">OUTPUT ARTIFACT</div>
            <div className="p-3 rounded-lg bg-jarvis-surface/60 border border-cyan-500/30 text-xs font-mono text-cyan-300">
              {stage.outputType}
            </div>

            <div className="text-[11px] text-jarvis-muted leading-relaxed">
              Every stage updates additive state keys in the compiled LangGraph runtime without overwriting historical run traces.
            </div>
          </div>

          <div className="pt-3 border-t border-jarvis-border/30 flex items-center justify-between text-xs font-semibold">
            <button
              onClick={() => setActiveStage((prev) => Math.max(0, prev - 1))}
              disabled={activeStage === 0}
              className="text-jarvis-muted hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
            >
              ← Previous
            </button>
            <span className="text-xs font-mono text-jarvis-muted">{activeStage + 1} / {STAGES.length}</span>
            <button
              onClick={() => setActiveStage((prev) => Math.min(STAGES.length - 1, prev + 1))}
              disabled={activeStage === STAGES.length - 1}
              className="text-cyan-400 hover:text-cyan-300 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Next Phase →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
