import { useState } from 'react'
import {
  Layers,
  Shield,
  Code2
} from 'lucide-react'

interface ArchitectureNode {
  id: string
  name: string
  category: 'client' | 'gateway' | 'orchestrator' | 'pipeline' | 'validation'
  shortDesc: string
  details: string
  inputs: string[]
  outputs: string[]
  guarantees: string
  sourceFile: string
}

const NODES: ArchitectureNode[] = [
  {
    id: 'client',
    name: 'React 18 SPA & Audio Engine',
    category: 'client',
    shortDesc: 'Vite 5, Zustand, Web Audio API with local VAD & Barge-in',
    details: 'Zero-latency UI with reactive multi-workspace panels (Conversation, AI Core, Workspaces, PDF Studio). Interruption token dispatch cuts off audio playback in under 18ms.',
    inputs: ['Microphone audio', 'User queries', 'Resume PDF/TXT'],
    outputs: ['Typed WebSocket envelopes', 'Local audio stream'],
    guarantees: 'Zero audio sent to external third parties; in-memory stream only.',
    sourceFile: 'frontend/src/App.tsx, useWebSocket.ts',
  },
  {
    id: 'gateway',
    name: 'FastAPI Gateway & PII Quarantine',
    category: 'gateway',
    shortDesc: 'Realtime WebSocket endpoint with session isolation',
    details: 'Manages single-active-run state machines per connection. Any incoming resume or user profile data is scrubbed with strict PII boundary isolation before entering state memory.',
    inputs: ['WebSocket frames', 'Resume payload'],
    outputs: ['Sanitized candidate tokens', 'Streamed updates'],
    guarantees: 'PII never enters event narration, model contexts, or system logs.',
    sourceFile: 'app/api/routes/jarvis.py, app/candidate/pii.py',
  },
  {
    id: 'fast_router',
    name: 'FastIntentRouter & Grammar',
    category: 'orchestrator',
    shortDesc: 'Sub-45ms deterministic regex/cue intent parser',
    details: 'Routes high-frequency commands (barge-in stops, filter changes, workspace switches, query criteria) directly without invoking external LLMs, delivering 180ms TTFT responses.',
    inputs: ['Transcribed text tokens'],
    outputs: ['Fast UI action', 'Pipeline trigger event'],
    guarantees: 'Deterministic grammar fallback with zero hallucination.',
    sourceFile: 'app/jarvis/intent.py',
  },
  {
    id: 'langgraph',
    name: 'LangGraph Orchestration Engine',
    category: 'orchestrator',
    shortDesc: 'Compiled, stateful, multi-phase execution graph',
    details: 'The compiled graph (Phases 1–6) is the single execution engine. Dispatched via astream(stream_mode="updates"), with cooperative cancellation if the user interrupts.',
    inputs: ['Pipeline trigger', 'CandidateProfile', 'Search criteria'],
    outputs: ['Incremental state updates (jobs, matches, tailored_resume)'],
    guarantees: 'One active run per connection; guaranteed cleanup on abort.',
    sourceFile: 'app/jarvis/orchestrator.py',
  },
  {
    id: 'sources',
    name: 'Multi-Source Discovery Radar',
    category: 'pipeline',
    shortDesc: 'Greenhouse, Lever, and Google Jobs adapters with cross-source deduplication',
    details: 'Fetches postings across multiple ATS APIs with jittered exponential backoff. Cross-source deduplication prevents identical job records from cluttering rankings.',
    inputs: ['Keyword criteria', 'Location filter'],
    outputs: ['Canonical Job[] objects with source provenance'],
    guarantees: 'Zero manufactured timestamps; displays exact raw posting provenance.',
    sourceFile: 'app/sources/greenhouse.py, lever.py, searchapi.py',
  },
  {
    id: 'jd_understanding',
    name: 'Untrusted JD Understanding',
    category: 'pipeline',
    shortDesc: 'Deterministic skill, requirement & experience deconstruction',
    details: 'Treats job descriptions as untrusted external input (script/style stripped, character capped). Extracts requirements with explicit Evidence tags (text, field, method, confidence).',
    inputs: ['Raw untrusted JD HTML/text'],
    outputs: ['Structured JDAnalysis with verifiable evidence'],
    guarantees: 'Claims must quote verbatim evidence or they are rejected.',
    sourceFile: 'app/jdunderstanding/analyzer.py',
  },
  {
    id: 'matching',
    name: 'Deterministic 8-Weight Match Engine',
    category: 'pipeline',
    shortDesc: 'Transparent math-based candidate-to-job matching',
    details: 'Applies fixed weights: Required Skills (30), Preferred Skills (10), Experience (20), Location (12), Employment Type (10), Education (8), Level (5), Salary (5). Tiers: Strong ≥ 75, Moderate ≥ 50.',
    inputs: ['CandidateProfile', 'JDAnalysis[]'],
    outputs: ['MatchResult[] with score breakdown and gap analysis'],
    guarantees: 'No black-box scoring; every percentage point is explainable.',
    sourceFile: 'app/matching/engine.py',
  },
  {
    id: 'truth_guard',
    name: 'Phase 6 Truth Guard & ATS Validator',
    category: 'validation',
    shortDesc: 'Read-only T1–T10 Truth Checks and A1–A8 ATS Compliance Audits',
    details: 'Mathematically verifies token containment (C_tailored ⊆ C_candidate). Any invented skill, fabricated title, or non-verifiable metric causes an immediate FAIL.',
    inputs: ['TailoredResume', 'CandidateProfile Evidence', 'JDAnalysis'],
    outputs: ['ValidationReport (PASS/FAIL, Coverage %, Warnings)'],
    guarantees: '100% token containment. Zero invented qualifications.',
    sourceFile: 'app/validation/truth.py, ats.py',
  },
]

export function ArchitectureGraph() {
  const [selectedNode, setSelectedNode] = useState<ArchitectureNode>(NODES[0])

  return (
    <div className="w-full rounded-2xl glass-strong border border-jarvis-border/60 p-6 lg:p-8 space-y-6 text-left">
      <div>
        <div className="flex items-center gap-2">
          <Layers className="text-cyan-400" size={20} />
          <h3 className="text-lg font-bold text-white tracking-wide">Interactive Architecture Topology</h3>
        </div>
        <p className="text-xs text-jarvis-muted mt-1">
          Select any node to inspect its execution boundaries, data inputs/outputs, and sovereign safety guarantees.
        </p>
      </div>

      {/* Topology Map */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Node Selection Grid */}
        <div className="lg:col-span-2 space-y-3">
          {/* Layer Headers */}
          <div className="space-y-4">
            {/* Layer 1: Client & Gateway */}
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-400 font-bold mb-2 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                <span>Presentation & Gateway Tier</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {NODES.filter((n) => n.category === 'client' || n.category === 'gateway').map((node) => {
                  const isSelected = selectedNode.id === node.id
                  return (
                    <button
                      key={node.id}
                      onClick={() => setSelectedNode(node)}
                      className={`p-3 rounded-xl text-left transition-all border ${
                        isSelected
                          ? 'bg-blue-600/20 border-blue-500 shadow-lg shadow-blue-500/20'
                          : 'bg-jarvis-surface/40 hover:bg-jarvis-surface/80 border-jarvis-border/40'
                      }`}
                    >
                      <div className="text-xs font-semibold text-white flex items-center justify-between">
                        <span>{node.name}</span>
                        <span className="text-[10px] text-cyan-400 font-mono">{node.category}</span>
                      </div>
                      <p className="text-[11px] text-jarvis-muted mt-1 line-clamp-2">{node.shortDesc}</p>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Layer 2: Orchestration & Grammar */}
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-violet-400 font-bold mb-2 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                <span>Orchestration & Fast Routing</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {NODES.filter((n) => n.category === 'orchestrator').map((node) => {
                  const isSelected = selectedNode.id === node.id
                  return (
                    <button
                      key={node.id}
                      onClick={() => setSelectedNode(node)}
                      className={`p-3 rounded-xl text-left transition-all border ${
                        isSelected
                          ? 'bg-violet-600/20 border-violet-500 shadow-lg shadow-violet-500/20'
                          : 'bg-jarvis-surface/40 hover:bg-jarvis-surface/80 border-jarvis-border/40'
                      }`}
                    >
                      <div className="text-xs font-semibold text-white flex items-center justify-between">
                        <span>{node.name}</span>
                        <span className="text-[10px] text-violet-400 font-mono">{node.category}</span>
                      </div>
                      <p className="text-[11px] text-jarvis-muted mt-1 line-clamp-2">{node.shortDesc}</p>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Layer 3: Pipeline & Truth Verification */}
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-emerald-400 font-bold mb-2 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <span>Frozen Pipeline & Truth Verification</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {NODES.filter((n) => n.category === 'pipeline' || n.category === 'validation').map((node) => {
                  const isSelected = selectedNode.id === node.id
                  return (
                    <button
                      key={node.id}
                      onClick={() => setSelectedNode(node)}
                      className={`p-3 rounded-xl text-left transition-all border ${
                        isSelected
                          ? 'bg-emerald-600/20 border-emerald-500 shadow-lg shadow-emerald-500/20'
                          : 'bg-jarvis-surface/40 hover:bg-jarvis-surface/80 border-jarvis-border/40'
                      }`}
                    >
                      <div className="text-xs font-semibold text-white flex items-center justify-between">
                        <span>{node.name}</span>
                        <span className="text-[10px] text-emerald-400 font-mono">{node.category}</span>
                      </div>
                      <p className="text-[11px] text-jarvis-muted mt-1 line-clamp-2">{node.shortDesc}</p>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Selected Node Deep-Dive Card */}
        <div className="col-span-1 p-5 rounded-2xl bg-gradient-to-b from-jarvis-surface/90 to-jarvis-darker border border-jarvis-border/60 flex flex-col justify-between space-y-4">
          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-blue-500/10 text-cyan-400 border border-blue-500/20">
                  {selectedNode.category}
                </span>
                <span className="text-[10px] font-mono text-jarvis-muted">ACTIVE INSPECTION</span>
              </div>
              <h4 className="text-base font-bold text-white mt-2">{selectedNode.name}</h4>
              <p className="text-xs text-jarvis-muted leading-relaxed mt-2">{selectedNode.details}</p>
            </div>

            {/* Inputs & Outputs */}
            <div className="space-y-3 pt-2 border-t border-jarvis-border/30 text-xs">
              <div>
                <span className="text-[11px] font-mono text-jarvis-muted uppercase tracking-wider block mb-1">
                  Inputs:
                </span>
                <div className="flex flex-wrap gap-1">
                  {selectedNode.inputs.map((inItem) => (
                    <span
                      key={inItem}
                      className="px-2 py-0.5 rounded bg-jarvis-surface text-[10px] text-jarvis-light font-mono"
                    >
                      {inItem}
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <span className="text-[11px] font-mono text-jarvis-muted uppercase tracking-wider block mb-1">
                  Outputs:
                </span>
                <div className="flex flex-wrap gap-1">
                  {selectedNode.outputs.map((outItem) => (
                    <span
                      key={outItem}
                      className="px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-300 text-[10px] font-mono border border-cyan-500/20"
                    >
                      {outItem}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Sovereign Guarantee */}
            <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 space-y-1">
              <div className="flex items-center gap-1.5 text-emerald-400 font-bold text-[11px] font-mono">
                <Shield size={12} />
                <span>SOVEREIGN GUARANTEE</span>
              </div>
              <p className="text-[11px] text-emerald-200/90 leading-normal">{selectedNode.guarantees}</p>
            </div>
          </div>

          {/* Source code path */}
          <div className="pt-2 border-t border-jarvis-border/30 flex items-center justify-between text-[11px] font-mono text-jarvis-muted/70">
            <span className="flex items-center gap-1">
              <Code2 size={12} />
              <span>Path:</span>
            </span>
            <span className="text-cyan-300/80 truncate max-w-[190px]">{selectedNode.sourceFile}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
