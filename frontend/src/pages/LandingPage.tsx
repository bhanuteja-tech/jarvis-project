import { Link } from 'react-router-dom'
import {
  Mic,
  ArrowRight,
  ShieldCheck,
  Cpu,
  Target,
  FileCheck,
  Search,
  CheckCircle2,
  XCircle,
  HelpCircle
} from 'lucide-react'
import { AgentDemoVisualizer } from '../components/public/AgentDemoVisualizer'
import { VoiceStateDemo } from '../components/public/VoiceStateDemo'
import { ArchitectureGraph } from '../components/public/ArchitectureGraph'
import { PipelineVisualizer } from '../components/public/PipelineVisualizer'
import { ProductPreviewCard } from '../components/public/ProductPreviewCard'

const CAPABILITIES = [
  {
    icon: Mic,
    title: 'Sovereign Voice & Barge-in',
    tag: '180ms TTFT',
    description: 'Natural voice interaction with sub-18ms interruption handling. Speak freely; JARVIS stops talking the instant you speak.',
    accent: 'from-blue-500/20 to-cyan-500/10',
    border: 'border-cyan-500/30',
  },
  {
    icon: Search,
    title: 'Multi-Source Radar',
    tag: 'Greenhouse · Lever · Google',
    description: 'Scrapes and normalizes authentic postings across primary ATS platforms. Deduplicates postings and extracts verifiable requirements.',
    accent: 'from-indigo-500/20 to-blue-500/10',
    border: 'border-blue-500/30',
  },
  {
    icon: Cpu,
    title: 'Untrusted JD Understanding',
    tag: 'Strict Provenance',
    description: 'Treats job descriptions as untrusted text. Extracts required skills, experience thresholds, and salary markers with evidence tags.',
    accent: 'from-violet-500/20 to-purple-500/10',
    border: 'border-violet-500/30',
  },
  {
    icon: Target,
    title: '8-Factor Deterministic Match',
    tag: 'Transparent Math',
    description: 'Fixed-weight scoring model (Required 30, Preferred 10, Experience 20, Location 12, etc.). No black-box embeddings or phantom rejections.',
    accent: 'from-emerald-500/20 to-teal-500/10',
    border: 'border-emerald-500/30',
  },
  {
    icon: FileCheck,
    title: 'Truth-Guarded Tailoring',
    tag: 'Subset Enforced',
    description: 'Re-aligns resume highlights and synthesizes targeted summaries exclusively from your verified profile evidence. Zero invented claims.',
    accent: 'from-cyan-500/20 to-blue-500/10',
    border: 'border-cyan-500/30',
  },
  {
    icon: ShieldCheck,
    title: 'ATS Audit & PII Quarantine',
    tag: 'T1–T10 & A1–A8',
    description: 'Rigorous 10-point mathematical truth verification and 8-point ATS compliance check. Contact PII is quarantined from narration contexts.',
    accent: 'from-amber-500/20 to-orange-500/10',
    border: 'border-amber-500/30',
  },
]

const COMPARISON_ROWS = [
  {
    feature: 'Hallucination Prevention',
    jarvis: 'Mathematical Token Containment Guard (T1–T10) guarantees 0% invented claims',
    chatbots: 'High risk of inventing dates, skills, and metrics to please user',
    jobBoards: 'N/A (static keyword matching)',
  },
  {
    feature: 'Scoring Transparency',
    jarvis: 'Deterministic 8-factor math with exact percentage breakdown',
    chatbots: 'Opaque black-box reasoning; unpredictable re-runs',
    jobBoards: 'Hidden sponsored ranking algorithms',
  },
  {
    feature: 'Voice Interruption (Barge-in)',
    jarvis: '< 18ms client-side audio cutoff & clean connection renewal',
    chatbots: 'Laggy or unavailable; full audio clip must finish playing',
    jobBoards: 'None',
  },
  {
    feature: 'Job Source Integrity',
    jarvis: 'Direct public ATS adapters (Greenhouse, Lever) + Google Jobs deduplication',
    chatbots: 'Stale web search or fabricated job links',
    jobBoards: 'Cluttered with expired sponsored listings and scrapers',
  },
  {
    feature: 'Candidate Privacy',
    jarvis: 'Strict PII quarantine; contact data never enters narration or model contexts',
    chatbots: 'Sends full resumes with phone/address to third-party model APIs',
    jobBoards: 'Monetizes candidate resume data to third-party recruiters',
  },
]

export function LandingPage() {
  return (
    <div className="space-y-24 pb-20">
      {/* 1. HERO SECTION */}
      <section className="relative px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto pt-8 sm:pt-14">
        <div className="text-center space-y-6 max-w-4xl mx-auto">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full glass border border-blue-500/30 text-xs font-mono font-medium text-cyan-300 shadow-lg shadow-blue-500/10 animate-fade-in">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
            <span>SOVEREIGN VOICE AI & AUTONOMOUS CAREER OPERATING SYSTEM</span>
          </div>

          {/* Headline */}
          <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-white leading-[1.1]">
            Real-Time Voice Intelligence. <br />
            <span className="text-gradient-cyan">Deterministic Career Execution.</span>
          </h1>

          {/* Subhead */}
          <p className="text-base sm:text-lg lg:text-xl text-jarvis-muted leading-relaxed max-w-3xl mx-auto font-normal">
            Stop wrestling with black-box chatbots and hallucinated resumes. JARVIS connects natural conversational voice to an 8-stage LangGraph pipeline that hunts real jobs, scores fit with pure math, and tailors resumes with mathematical truth containment.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3.5 pt-2">
            <Link
              to="/app"
              className="w-full sm:w-auto px-7 py-3.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-500 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-sm shadow-xl shadow-blue-600/30 flex items-center justify-center gap-2 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <span>Launch Application</span>
              <ArrowRight size={16} />
            </Link>

            <Link
              to="/voice-agent"
              className="w-full sm:w-auto px-6 py-3.5 rounded-xl glass hover:bg-jarvis-surface text-jarvis-light hover:text-white font-semibold text-sm border border-jarvis-border/60 flex items-center justify-center gap-2 transition-all"
            >
              <Mic size={16} className="text-cyan-400" />
              <span>Voice Agent Showcase</span>
            </Link>

            <Link
              to="/docs"
              className="w-full sm:w-auto px-5 py-3.5 rounded-xl text-jarvis-muted hover:text-white text-sm font-medium transition-colors"
            >
              Documentation →
            </Link>
          </div>
        </div>

        {/* Hero Interactive Agent Visualizer */}
        <div className="mt-12 sm:mt-16 max-w-5xl mx-auto">
          <AgentDemoVisualizer />
        </div>
      </section>

      {/* 2. LIVE METRICS STRIP */}
      <section className="border-y border-jarvis-border/40 bg-jarvis-surface/20 py-8 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-2 lg:grid-cols-4 gap-6 text-center">
          <div className="space-y-1">
            <div className="text-2xl sm:text-3xl font-extrabold font-mono text-cyan-400">100%</div>
            <div className="text-xs font-semibold uppercase tracking-wider text-white">Truth Guard Containment</div>
            <p className="text-[11px] text-jarvis-muted">C_tailored ⊆ C_candidate verified</p>
          </div>

          <div className="space-y-1">
            <div className="text-2xl sm:text-3xl font-extrabold font-mono text-emerald-400">~180ms</div>
            <div className="text-xs font-semibold uppercase tracking-wider text-white">Voice TTFT Latency</div>
            <p className="text-[11px] text-jarvis-muted">FastIntentRouter sub-45ms dispatch</p>
          </div>

          <div className="space-y-1">
            <div className="text-2xl sm:text-3xl font-extrabold font-mono text-blue-400">8 Stages</div>
            <div className="text-xs font-semibold uppercase tracking-wider text-white">Frozen LangGraph Pipeline</div>
            <p className="text-[11px] text-jarvis-muted">Phases 1–6 deterministic engine</p>
          </div>

          <div className="space-y-1">
            <div className="text-2xl sm:text-3xl font-extrabold font-mono text-violet-400">0%</div>
            <div className="text-xs font-semibold uppercase tracking-wider text-white">Hallucination Tolerance</div>
            <p className="text-[11px] text-jarvis-muted">T1-T10 audits fail on fabricated claims</p>
          </div>
        </div>
      </section>

      {/* 3. 6 CORE CAPABILITIES GRID */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
        <div className="text-center space-y-3 max-w-3xl mx-auto">
          <div className="text-xs font-mono uppercase tracking-widest text-cyan-400 font-bold">
            ARCHITECTED FOR SOVEREIGNTY
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
            Six Autonomous Pillars of Career Intelligence
          </h2>
          <p className="text-sm sm:text-base text-jarvis-muted leading-relaxed">
            Every layer is engineered to remove guesswork, eliminate fabricated resume claims, and respect your privacy.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {CAPABILITIES.map((cap) => {
            const Icon = cap.icon
            return (
              <div
                key={cap.title}
                className={`p-6 rounded-2xl glass hover:border-blue-500/50 transition-all duration-300 group border ${cap.border} flex flex-col justify-between space-y-4`}
              >
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600/30 to-violet-600/20 border border-blue-500/30 flex items-center justify-center group-hover:scale-110 transition-transform">
                      <Icon className="text-cyan-400" size={22} />
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-jarvis-surface text-cyan-300 border border-jarvis-border/50">
                      {cap.tag}
                    </span>
                  </div>

                  <div>
                    <h3 className="text-lg font-bold text-white group-hover:text-cyan-300 transition-colors">
                      {cap.title}
                    </h3>
                    <p className="text-xs sm:text-sm text-jarvis-muted mt-2 leading-relaxed">
                      {cap.description}
                    </p>
                  </div>
                </div>

                <div className="pt-3 border-t border-jarvis-border/30 flex items-center text-xs font-medium text-cyan-400 group-hover:translate-x-1 transition-transform">
                  <span>Explore capability details →</span>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* 4. PRODUCT DASHBOARD PREVIEW */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <span className="text-xs font-mono uppercase tracking-widest text-blue-400 font-bold">
            FULL WORKSPACE EXPERIENCE
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
            The Three-Panel Unified Dashboard
          </h2>
          <p className="text-xs sm:text-sm text-jarvis-muted leading-relaxed">
            Real-time conversational voice, glowing AI Core state machine, and dedicated multi-tab workspaces for job radar, matching math, and PDF document studio.
          </p>
        </div>

        <ProductPreviewCard />
      </section>

      {/* 5. 8-STAGE LANGGRAPH PIPELINE */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <PipelineVisualizer />
      </section>

      {/* 6. VOICE ENGINE SHOWCASE */}
      <section id="voice-demo" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <VoiceStateDemo />
      </section>

      {/* 7. ARCHITECTURE TOPOLOGY */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <ArchitectureGraph />
      </section>

      {/* 8. COMPARISON MATRIX */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <span className="text-xs font-mono uppercase tracking-widest text-emerald-400 font-bold">
            ARCHITECTURAL HONESTY
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
            Why Deterministic AI Outclasses Generic LLMs
          </h2>
          <p className="text-xs sm:text-sm text-jarvis-muted leading-relaxed">
            We reject fuzzy reasoning for critical career decisions. Here is how JARVIS compares to common chatbots and legacy job aggregators.
          </p>
        </div>

        <div className="overflow-x-auto rounded-2xl glass border border-jarvis-border/60">
          <table className="w-full text-left text-xs sm:text-sm border-collapse">
            <thead>
              <tr className="border-b border-jarvis-border/60 bg-jarvis-surface/60 font-mono text-xs">
                <th className="p-4 sm:p-5 text-white font-bold">Dimension</th>
                <th className="p-4 sm:p-5 text-cyan-300 font-bold bg-blue-950/20">J.A.R.V.I.S (Sovereign OS)</th>
                <th className="p-4 sm:p-5 text-jarvis-muted">Generic Chatbots</th>
                <th className="p-4 sm:p-5 text-jarvis-muted">Traditional Job Boards</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-jarvis-border/30">
              {COMPARISON_ROWS.map((row) => (
                <tr key={row.feature} className="hover:bg-jarvis-surface/30 transition-colors">
                  <td className="p-4 sm:p-5 font-semibold text-white">{row.feature}</td>
                  <td className="p-4 sm:p-5 text-cyan-200 bg-blue-950/20 font-medium">
                    <div className="flex items-start gap-2">
                      <CheckCircle2 size={16} className="text-cyan-400 shrink-0 mt-0.5" />
                      <span>{row.jarvis}</span>
                    </div>
                  </td>
                  <td className="p-4 sm:p-5 text-jarvis-muted">
                    <div className="flex items-start gap-2">
                      <XCircle size={16} className="text-red-400/70 shrink-0 mt-0.5" />
                      <span>{row.chatbots}</span>
                    </div>
                  </td>
                  <td className="p-4 sm:p-5 text-jarvis-muted">
                    <div className="flex items-start gap-2">
                      <HelpCircle size={16} className="text-yellow-500/70 shrink-0 mt-0.5" />
                      <span>{row.jobBoards}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 9. TARGET AUDIENCE */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <span className="text-xs font-mono uppercase tracking-widest text-violet-400 font-bold">
            ENGINEERED FOR HIGH-IMPACT TALENT
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
            Built for Professionals Who Demand Precision
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 rounded-2xl glass border border-jarvis-border/60 space-y-3">
            <h3 className="text-base font-bold text-white">Staff & Principal Engineers</h3>
            <p className="text-xs sm:text-sm text-jarvis-muted leading-relaxed">
              Cut through recruiter noise. Target specific distributed systems, Kubernetes, and high-throughput architectures without losing control of your credentials.
            </p>
          </div>

          <div className="p-6 rounded-2xl glass border border-jarvis-border/60 space-y-3">
            <h3 className="text-base font-bold text-white">AI & ML Research Practitioners</h3>
            <p className="text-xs sm:text-sm text-jarvis-muted leading-relaxed">
              Surface roles with explicit GPU cluster management, CUDA kernel optimization, and LLM orchestration requirements matched directly against your publications.
            </p>
          </div>

          <div className="p-6 rounded-2xl glass border border-jarvis-border/60 space-y-3">
            <h3 className="text-base font-bold text-white">Technical Leaders & Architects</h3>
            <p className="text-xs sm:text-sm text-jarvis-muted leading-relaxed">
              Verify executive competencies and compensation boundaries transparently without risking sensitive profile details across public aggregators.
            </p>
          </div>
        </div>
      </section>

      {/* 10. FINAL CTA BANNER */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="p-8 sm:p-12 lg:p-16 rounded-3xl bg-gradient-to-br from-blue-900/40 via-indigo-950/50 to-jarvis-darker border border-blue-500/40 shadow-2xl shadow-blue-950/60 relative overflow-hidden text-center space-y-6">
          {/* Ambient light inside banner */}
          <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-96 h-96 bg-cyan-500/20 rounded-full blur-3xl pointer-events-none" />

          <div className="relative z-10 space-y-3 max-w-2xl mx-auto">
            <h2 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
              Ready to take sovereign control of your career search?
            </h2>
            <p className="text-sm sm:text-base text-cyan-200/80 leading-relaxed">
              Launch the JARVIS dashboard immediately. Experience voice orchestration, transparent mathematical scoring, and 100% truth-guarded resume generation.
            </p>
          </div>

          <div className="relative z-10 flex flex-col sm:flex-row items-center justify-center gap-4 pt-2">
            <Link
              to="/app"
              className="px-8 py-3.5 rounded-xl bg-gradient-to-r from-blue-500 to-cyan-400 hover:from-blue-400 hover:to-cyan-300 text-slate-950 font-bold text-sm shadow-xl shadow-cyan-500/25 flex items-center gap-2 transition-all hover:scale-105 active:scale-95"
            >
              <span>Launch JARVIS App Now</span>
              <ArrowRight size={16} />
            </Link>
            <Link
              to="/features"
              className="px-6 py-3.5 rounded-xl glass hover:bg-jarvis-surface text-white text-sm font-semibold border border-jarvis-border/60 transition-colors"
            >
              Explore Full Features Matrix
            </Link>
          </div>

          <div className="relative z-10 flex items-center justify-center gap-6 text-[11px] text-jarvis-muted font-mono pt-4">
            <span>✓ Zero Credit Card Required</span>
            <span>✓ Instant Guest / Demo Mode</span>
            <span>✓ 100% Open Architecture</span>
          </div>
        </div>
      </section>
    </div>
  )
}
