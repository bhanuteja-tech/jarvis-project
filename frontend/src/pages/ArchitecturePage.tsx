import { Link } from 'react-router-dom'
import {
  Layers,
  Code2,
  Terminal,
  ArrowRight,
  GitBranch
} from 'lucide-react'
import { ArchitectureGraph } from '../components/public/ArchitectureGraph'

const LAYERING_RULES = [
  {
    layer: 'Presentation & UI',
    tech: 'React 18 · Vite 5 · Zustand · Web Audio API · TailwindCSS',
    rule: 'Zero direct API access to third-party ATSs; communicates exclusively through typed WebSocket envelopes with FastAPI.',
  },
  {
    layer: 'Gateway & Session',
    tech: 'FastAPI · Uvicorn · In-Memory Session Store · PII Boundary',
    rule: 'One active run per connection. Incoming runs cooperatively cancel prior running tasks. Sessions are memory-only.',
  },
  {
    layer: 'Orchestrator & Graph',
    tech: 'LangGraph · Python 3.11+ · asyncio · astream("updates")',
    rule: 'Strict layering: graph -> sources -> models. Models never import httpx, SQLAlchemy, or LangGraph. Graph is frozen.',
  },
  {
    layer: 'Data & Persistence',
    tech: 'PostgreSQL · SQLAlchemy · Alembic · Pydantic v2',
    rule: 'Canonical Job model never stores invented or guessed fields. Source timestamps remain distinct from internal DB timestamps.',
  },
]

export function ArchitecturePage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16">
      {/* Header */}
      <div className="text-center space-y-4 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-mono font-semibold">
          <Code2 size={13} />
          <span>TECHNICAL SPECIFICATION</span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold text-white tracking-tight">
          System Architecture & Engineering Conventions
        </h1>
        <p className="text-base text-jarvis-muted leading-relaxed">
          Deep-dive into the layering boundaries, state machines, and concurrency safety protocols governing the JARVIS Sovereign Career Operating System.
        </p>
      </div>

      {/* Interactive Topology Graph */}
      <div className="space-y-4">
        <ArchitectureGraph />
      </div>

      {/* Layering & Boundary Constraints */}
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Layers className="text-cyan-400" size={18} />
            <h2 className="text-2xl font-bold text-white">Strict Layering & Architectural Invariants</h2>
          </div>
          <p className="text-xs sm:text-sm text-jarvis-muted">
            The codebase enforces rigid isolation to prevent dependency contamination and data leakage.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {LAYERING_RULES.map((item) => (
            <div key={item.layer} className="p-6 rounded-2xl glass border border-jarvis-border/50 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-white">{item.layer}</h3>
                <span className="text-[10px] font-mono text-cyan-300 bg-blue-500/10 px-2 py-0.5 rounded">
                  ISOLATED
                </span>
              </div>
              <div className="text-xs font-mono text-violet-300">{item.tech}</div>
              <p className="text-xs text-jarvis-muted leading-relaxed">{item.rule}</p>
            </div>
          ))}
        </div>
      </div>

      {/* LangGraph State Machine Specification */}
      <div className="p-6 sm:p-8 rounded-3xl glass border border-jarvis-border/60 space-y-6">
        <div className="flex items-center justify-between border-b border-jarvis-border/40 pb-4">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <GitBranch className="text-violet-400" size={18} />
              <span>LangGraph Compilation & Execution Contract</span>
            </h3>
            <p className="text-xs text-jarvis-muted mt-1">
              Phases 1–6 form the single execution engine. Dispatched via <code className="text-cyan-300 font-mono">astream(stream_mode="updates")</code>.
            </p>
          </div>
          <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20">
            FROZEN & LOCKED
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 text-xs font-mono">
          <div className="p-4 rounded-xl bg-black/50 border border-jarvis-border/40 space-y-2">
            <div className="text-cyan-400 font-bold">STATE SCHEMA (Canonical)</div>
            <ul className="space-y-1 text-jarvis-muted text-[11px]">
              <li>• <span className="text-white">jobs:</span> list[Job] (Multi-source canonical list)</li>
              <li>• <span className="text-white">ranked_jobs:</span> list[RankedJob] (Deterministic scored views)</li>
              <li>• <span className="text-white">jd_analyses:</span> dict[str, JDAnalysis] (Untrusted extraction)</li>
              <li>• <span className="text-white">candidate_profile:</span> CandidateProfile (PII quarantined)</li>
              <li>• <span className="text-white">match_results:</span> list[MatchResult] (8-weight math)</li>
              <li>• <span className="text-white">tailored_resume:</span> TailoredResume (Subset guarded)</li>
              <li>• <span className="text-white">validation_report:</span> ValidationReport (T1-T10 + A1-A8)</li>
            </ul>
          </div>

          <div className="p-4 rounded-xl bg-black/50 border border-jarvis-border/40 space-y-2">
            <div className="text-violet-400 font-bold">CONCURRENCY & CANCELLATION</div>
            <p className="text-jarvis-muted text-[11px] leading-relaxed font-sans">
              Every WebSocket connection maintains at most ONE active background execution run. When a user submits a new prompt or triggers barge-in, the running task is cancelled via <code className="font-mono text-white">task.cancel()</code> before the new graph execution begins, ensuring zero race conditions or orphaned background processes.
            </p>
          </div>
        </div>
      </div>

      {/* Directory & Package Organization */}
      <div className="p-6 sm:p-8 rounded-3xl glass border border-jarvis-border/60 space-y-4">
        <h3 className="text-base font-bold text-white flex items-center gap-2">
          <Terminal className="text-cyan-400" size={18} />
          <span>Core Repository Layout</span>
        </h3>
        <div className="p-4 rounded-xl bg-black/60 border border-jarvis-border/40 font-mono text-xs text-jarvis-muted space-y-1">
          <div><span className="text-cyan-400">app/api/routes/jarvis.py</span> — WebSocket session endpoint and typed event channel</div>
          <div><span className="text-cyan-400">app/jarvis/orchestrator.py</span> — LangGraph runner executing astream("updates")</div>
          <div><span className="text-cyan-400">app/jarvis/intent.py</span> — Sub-45ms FastIntentRouter deterministic grammar</div>
          <div><span className="text-cyan-400">app/sources/</span> — Greenhouse, Lever, and SearchApi (Google Jobs) adapters</div>
          <div><span className="text-cyan-400">app/jdunderstanding/</span> — Untrusted JD analysis & deterministic taxonomy extraction</div>
          <div><span className="text-cyan-400">app/matching/</span> — Deterministic 8-factor mathematical scoring engine</div>
          <div><span className="text-cyan-400">app/tailoring/</span> — Sovereign resume tailor with token containment subset guard</div>
          <div><span className="text-cyan-400">app/validation/</span> — Read-only T1–T10 truth verification and A1–A8 ATS audits</div>
          <div><span className="text-cyan-400">frontend/src/</span> — React 18 SPA with Web Audio API, Zustand store & PDF studio</div>
        </div>
      </div>

      {/* CTA */}
      <div className="p-8 rounded-2xl bg-gradient-to-r from-blue-900/30 via-violet-950/30 to-jarvis-darker border border-violet-500/30 flex flex-col sm:flex-row items-center justify-between gap-6">
        <div>
          <h3 className="text-lg font-bold text-white">Inspect the code or run the application</h3>
          <p className="text-xs text-jarvis-muted mt-1">Read the documentation or launch the interactive dashboard.</p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/docs"
            className="px-5 py-2.5 rounded-xl glass hover:bg-jarvis-surface text-white text-xs font-semibold border border-jarvis-border"
          >
            Read Docs
          </Link>
          <Link
            to="/app"
            className="px-6 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-semibold text-xs shadow-lg shadow-violet-500/25 flex items-center gap-2"
          >
            <span>Launch App</span>
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  )
}
