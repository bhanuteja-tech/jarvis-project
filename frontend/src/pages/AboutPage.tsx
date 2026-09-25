import { Link } from 'react-router-dom'
import {
  Activity,
  ShieldCheck,
  Cpu,
  ArrowRight,
  Lock,
  Target
} from 'lucide-react'

const PRINCIPLES = [
  {
    title: 'Zero-Hallucination Guarantee',
    desc: 'We believe career tools should never lie. When tailoring resumes, JARVIS enforces mathematical token containment. Any fabricated skill, unverified metric, or exaggerated job title immediately fails validation.',
    icon: ShieldCheck,
    color: 'text-cyan-400',
  },
  {
    title: 'Transparent Mathematical Scoring',
    desc: 'Job matching should not be an opaque lottery. Every percentage point in JARVIS is derived from a published 8-factor fixed-weight equation. You can audit exactly why a role scored 88% vs 62%.',
    icon: Target,
    color: 'text-emerald-400',
  },
  {
    title: 'Candidate Privacy Sovereignty',
    desc: 'Your contact details, current employer, and salary requirements are your private property. JARVIS quarantines PII so that sensitive personal identifiers never enter narration streams or model prompt contexts.',
    icon: Lock,
    color: 'text-violet-400',
  },
  {
    title: 'Auditable & Open Architecture',
    desc: 'Built with LangGraph, FastAPI, and React 18. All graph state transitions, source adapters, and scoring functions are strictly layered and frozen against silent breaking changes.',
    icon: Cpu,
    color: 'text-blue-400',
  },
]

export function AboutPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16">
      {/* Header */}
      <div className="text-center space-y-4 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-cyan-400 text-xs font-mono font-semibold">
          <Activity size={13} />
          <span>OUR MISSION & PHILOSOPHY</span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold text-white tracking-tight">
          Restoring Sovereignty and Truth to Career Intelligence
        </h1>
        <p className="text-base text-jarvis-muted leading-relaxed">
          The modern job market is plagued by recruiter spam, opaque algorithmic rejections, and hallucinating AI chatbots that fabricate resumes. JARVIS was founded on a simple principle: your career deserves deterministic truth.
        </p>
      </div>

      {/* The Problem We Solved */}
      <div className="p-8 sm:p-10 rounded-3xl glass border border-jarvis-border/60 space-y-6">
        <h2 className="text-2xl font-bold text-white tracking-tight">The Modern Career Search is Broken</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-xs sm:text-sm text-jarvis-muted leading-relaxed">
          <div className="space-y-2">
            <h3 className="font-bold text-white text-base">1. Hallucinating Chatbots</h3>
            <p>
              When candidates ask generic LLMs to tailor their resumes, the models enthusiastically fabricate technologies, invent years of experience, and manufacture metrics. This results in devastating interview failures and revoked offers.
            </p>
          </div>

          <div className="space-y-2">
            <h3 className="font-bold text-white text-base">2. Opaque Black-Box Matching</h3>
            <p>
              Corporate job boards hide sponsored postings behind proprietary algorithms. Candidates have zero visibility into why their application was rejected, or whether the role even matched their background.
            </p>
          </div>

          <div className="space-y-2">
            <h3 className="font-bold text-white text-base">3. Privacy Monetization</h3>
            <p>
              Traditional job portals monetize your personal data by selling phone numbers, emails, and employment histories to third-party headhunters and automated email scrapers.
            </p>
          </div>
        </div>
      </div>

      {/* The 4 Sovereign Principles */}
      <div className="space-y-8">
        <div className="text-center space-y-2 max-w-2xl mx-auto">
          <span className="text-xs font-mono uppercase tracking-widest text-cyan-400 font-bold">
            FOUNDATIONAL VALUES
          </span>
          <h2 className="text-3xl font-bold text-white">The Four Sovereign Pillars</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {PRINCIPLES.map((item) => {
            const Icon = item.icon
            return (
              <div key={item.title} className="p-6 sm:p-8 rounded-2xl glass border border-jarvis-border/50 space-y-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-jarvis-surface flex items-center justify-center border border-jarvis-border">
                    <Icon className={item.color} size={20} />
                  </div>
                  <h3 className="text-base font-bold text-white">{item.title}</h3>
                </div>
                <p className="text-xs sm:text-sm text-jarvis-muted leading-relaxed">
                  {item.desc}
                </p>
              </div>
            )
          })}
        </div>
      </div>

      {/* CTA */}
      <div className="p-8 rounded-2xl bg-gradient-to-r from-blue-900/30 via-indigo-950/40 to-jarvis-darker border border-blue-500/30 flex flex-col sm:flex-row items-center justify-between gap-6">
        <div>
          <h3 className="text-lg font-bold text-white">Experience sovereign career search firsthand.</h3>
          <p className="text-xs text-jarvis-muted mt-1">Free, open architecture, and ready to use in your browser.</p>
        </div>
        <Link
          to="/app"
          className="px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs shadow-lg shadow-blue-500/25 flex items-center gap-2"
        >
          <span>Launch Application</span>
          <ArrowRight size={14} />
        </Link>
      </div>
    </div>
  )
}
