import { useState } from 'react'
import {
  Activity,
  Briefcase,
  FileText,
  CheckCircle2,
  Mic,
  ShieldCheck,
  Download,
  Sparkles,
  Maximize2
} from 'lucide-react'
import { Link } from 'react-router-dom'

type WorkspaceTab = 'jobs' | 'intelligence' | 'tailor' | 'pdf'

export function ProductPreviewCard() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('jobs')

  return (
    <div className="w-full rounded-2xl glass-strong border border-jarvis-border/60 shadow-2xl shadow-blue-950/40 overflow-hidden text-left relative">
      {/* Fake Browser / Window Header */}
      <div className="h-12 bg-jarvis-surface/90 border-b border-jarvis-border/50 px-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-red-500/80" />
            <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
            <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
          </div>
          <div className="flex items-center gap-2 pl-3 border-l border-jarvis-border/40">
            <Activity className="text-cyan-400" size={15} />
            <span className="text-xs font-mono font-bold text-white tracking-wider">JARVIS DASHBOARD PREVIEW</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400 font-mono">
              LIVE APP INTERFACE
            </span>
          </div>
        </div>

        <Link
          to="/app"
          className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-500/20 transition-all hover:scale-[1.02]"
        >
          <span>Launch Full App</span>
          <Maximize2 size={12} />
        </Link>
      </div>

      {/* Main 3-Panel Preview Mock */}
      <div className="grid grid-cols-1 lg:grid-cols-12 min-h-[440px] bg-jarvis-darker">
        {/* Left Column (3 cols): Conversation & Voice Panel */}
        <div className="lg:col-span-4 border-r border-jarvis-border/40 p-4 flex flex-col justify-between bg-jarvis-darker/60">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs font-mono text-jarvis-muted pb-2 border-b border-jarvis-border/30">
              <span className="flex items-center gap-1 text-cyan-300">
                <Mic size={12} />
                <span>VOICE & INTENT STREAM</span>
              </span>
              <span className="text-[10px] text-emerald-400">Connected (127.0.0.1)</span>
            </div>

            {/* Chat Bubble 1: User */}
            <div className="p-2.5 rounded-xl bg-blue-600/15 border border-blue-500/30 text-xs text-white max-w-[90%]">
              <span className="text-[10px] text-blue-400 block font-mono mb-1">YOU (VOICE)</span>
              "Find Staff Backend roles in NYC with Kubernetes and Go. $200k+"
            </div>

            {/* Chat Bubble 2: Jarvis */}
            <div className="p-2.5 rounded-xl bg-jarvis-surface/70 border border-jarvis-border/40 text-xs text-jarvis-light max-w-[95%]">
              <div className="flex items-center gap-1 text-cyan-400 text-[10px] font-mono mb-1">
                <Sparkles size={11} />
                <span>JARVIS ORCHESTRATOR</span>
              </div>
              "Scanned 42 roles across Greenhouse and Lever. 4 roles meet your 8-factor criteria with a STRONG tier match."
            </div>

            {/* Event pill */}
            <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-300 flex items-center gap-1.5 font-mono">
              <ShieldCheck size={13} className="shrink-0" />
              <span>Phase 6 Truth Guard: 100% token containment verified</span>
            </div>
          </div>

          {/* Bottom input simulation */}
          <div className="pt-3 border-t border-jarvis-border/30 flex items-center gap-2">
            <div className="flex-1 px-3 py-1.5 rounded-lg bg-jarvis-surface text-xs text-jarvis-muted/60 border border-jarvis-border/40 font-mono">
              Ask Jarvis or speak...
            </div>
            <div className="p-2 rounded-lg bg-blue-600/30 text-cyan-300 border border-blue-500/40">
              <Mic size={14} />
            </div>
          </div>
        </div>

        {/* Right Area (8 cols): Workspaces & Visualizer */}
        <div className="lg:col-span-8 p-4 flex flex-col bg-jarvis-surface/20">
          {/* Workspace Tabs */}
          <div className="flex items-center gap-2 border-b border-jarvis-border/40 pb-3 mb-4 overflow-x-auto">
            <button
              onClick={() => setActiveTab('jobs')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
                activeTab === 'jobs'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'bg-jarvis-surface/60 text-jarvis-muted hover:text-white'
              }`}
            >
              <Briefcase size={13} />
              <span>Jobs Radar (4)</span>
            </button>

            <button
              onClick={() => setActiveTab('intelligence')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
                activeTab === 'intelligence'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'bg-jarvis-surface/60 text-jarvis-muted hover:text-white'
              }`}
            >
              <Activity size={13} />
              <span>JD & Profile Intelligence</span>
            </button>

            <button
              onClick={() => setActiveTab('tailor')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
                activeTab === 'tailor'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'bg-jarvis-surface/60 text-jarvis-muted hover:text-white'
              }`}
            >
              <FileText size={13} />
              <span>Tailored Resume</span>
            </button>

            <button
              onClick={() => setActiveTab('pdf')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
                activeTab === 'pdf'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'bg-jarvis-surface/60 text-jarvis-muted hover:text-white'
              }`}
            >
              <Download size={13} />
              <span>PDF Document Studio</span>
            </button>
          </div>

          {/* Dynamic Tab Contents */}
          <div className="flex-1 min-h-[300px]">
            {activeTab === 'jobs' && (
              <div className="space-y-3">
                <div className="p-3.5 rounded-xl bg-jarvis-surface/70 border border-blue-500/40 flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">Staff Distributed Systems Engineer</span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-semibold font-mono">
                        94% MATCH (STRONG)
                      </span>
                    </div>
                    <p className="text-xs text-jarvis-muted mt-0.5">Datadog · New York, NY (Hybrid) · $210,000 - $240,000</p>
                    <div className="flex gap-1.5 mt-2">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-jarvis-darker text-cyan-300 font-mono">Go</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-jarvis-darker text-cyan-300 font-mono">Kubernetes</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-jarvis-darker text-cyan-300 font-mono">Raft / Paxos</span>
                    </div>
                  </div>
                  <button className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-500">
                    Tailor
                  </button>
                </div>

                <div className="p-3.5 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">Principal Backend Architect</span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-semibold font-mono">
                        88% MATCH (STRONG)
                      </span>
                    </div>
                    <p className="text-xs text-jarvis-muted mt-0.5">Stripe · Remote (US) · $225,000 - $265,000</p>
                    <div className="flex gap-1.5 mt-2">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-jarvis-darker text-cyan-300 font-mono">Distributed Ledger</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-jarvis-darker text-cyan-300 font-mono">High Throughput</span>
                    </div>
                  </div>
                  <button className="px-3 py-1.5 rounded-lg bg-jarvis-surface text-jarvis-light text-xs font-semibold hover:bg-blue-600 hover:text-white">
                    Tailor
                  </button>
                </div>
              </div>
            )}

            {activeTab === 'intelligence' && (
              <div className="space-y-3 text-xs">
                <div className="p-3 rounded-xl bg-black/40 border border-jarvis-border/40 space-y-2 font-mono">
                  <div className="text-cyan-400 font-bold">DETERMINISTIC 8-WEIGHT SCORING FORMULA</div>
                  <div className="grid grid-cols-2 gap-2 text-[11px] text-jarvis-muted">
                    <div>Required Skills (30%): 28.5 / 30.0</div>
                    <div>Preferred Skills (10%): 9.2 / 10.0</div>
                    <div>Experience Duration (20%): 20.0 / 20.0</div>
                    <div>Location Alignment (12%): 12.0 / 12.0</div>
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-emerald-300 space-y-1">
                  <div className="font-semibold flex items-center gap-1.5">
                    <CheckCircle2 size={13} />
                    <span>Evidence Provenance: 100% Verifiable</span>
                  </div>
                  <p className="text-[11px] text-jarvis-muted leading-relaxed">
                    All candidate skills matched directly to explicit sentences within your uploaded resume. Zero inferred credentials.
                  </p>
                </div>
              </div>
            )}

            {activeTab === 'tailor' && (
              <div className="space-y-3 text-xs">
                <div className="p-3 rounded-xl bg-jarvis-surface/60 border border-jarvis-border/40 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-white">Synthesized Professional Summary</span>
                    <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                      Subset Guard PASS
                    </span>
                  </div>
                  <p className="text-jarvis-light italic text-xs leading-relaxed">
                    "Staff Software Engineer with 8+ years designing high-throughput distributed systems in Go and Kubernetes. Led architecture scaling for 14M daily queries with verifiable 99.99% availability."
                  </p>
                </div>

                <div className="p-2.5 rounded-lg bg-black/30 border border-jarvis-border/30 text-[11px] text-jarvis-muted flex items-center justify-between">
                  <span>ATS Keyword Coverage: 92% (14 of 15 targeted skills)</span>
                  <span className="text-emerald-400 font-mono">0 Keyword Stuffing</span>
                </div>
              </div>
            )}

            {activeTab === 'pdf' && (
              <div className="p-6 rounded-xl bg-gradient-to-br from-jarvis-surface/80 to-black border border-cyan-500/30 flex flex-col items-center justify-center text-center space-y-3">
                <div className="w-12 h-12 rounded-xl bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-cyan-400">
                  <FileText size={24} />
                </div>
                <div>
                  <h5 className="font-bold text-white text-sm">Full-Screen Document Studio Ready</h5>
                  <p className="text-xs text-jarvis-muted mt-1 max-w-sm">
                    Generate vector PDFs with live ATS typography guidelines, margin presets, and instant download.
                  </p>
                </div>
                <Link
                  to="/app"
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-500/30"
                >
                  Open Studio in App
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
