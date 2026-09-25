import { Link } from 'react-router-dom'
import {
  Mic,
  Search,
  Filter,
  BarChart3,
  Cpu,
  UserCheck,
  Target,
  FileCheck,
  ShieldCheck,
  ArrowRight,
  Activity
} from 'lucide-react'

const STEPS = [
  {
    number: '01',
    title: 'Voice & Natural Intent Ingestion',
    icon: Mic,
    color: 'text-cyan-400',
    tag: 'FastIntentRouter',
    summary: 'You speak naturally to JARVIS in plain language. The browser captures audio, runs client-side Voice Activity Detection, and converts tokens via WebSocket in real-time.',
    details: 'The FastIntentRouter checks for deterministic grammar cues (e.g. "stop", "switch to jobs", "filter remote"). If a deep search is requested, the compiled LangGraph execution graph is initialized.',
    code: 'ws.send(JSON.stringify({ type: "user_message", content: "Find Staff Distributed Systems roles in NYC" }))',
  },
  {
    number: '02',
    title: 'Parallel Multi-Source Discovery',
    icon: Search,
    color: 'text-blue-400',
    tag: 'Phase 1 · Sources',
    summary: 'JARVIS queries authentic public career endpoints concurrently, including Greenhouse API, Lever Postings API, and Google Jobs.',
    details: 'Each adapter runs with jittered exponential backoff and source-level identity tracking (source, source_job_id). Time periods and undocumented parameters are strictly sanitised to prevent API burn.',
    code: 'await asyncio.gather(greenhouse.fetch(boards), lever.fetch(sites), searchapi.fetch(query))',
  },
  {
    number: '03',
    title: 'Cross-Source Deduplication',
    icon: Filter,
    color: 'text-indigo-400',
    tag: 'Phase 1 · Deduplication',
    summary: 'The same role posted across Greenhouse and Google Jobs is merged into a single canonical posting record.',
    details: 'Identity resolution clusters postings using employer domain matching, clean title stem parsing, and geocoded location tokens, preserving all valid application endpoints without cluttering the candidate pipeline.',
    code: 'canonical_jobs = deduplicate_postings(raw_jobs, identity_map=source_provenance)',
  },
  {
    number: '04',
    title: 'Deterministic Ranking & Filtering',
    icon: BarChart3,
    color: 'text-violet-400',
    tag: 'Phase 1 · Ranking',
    summary: 'Initial discovery rankings apply hard constraints (eliminating unworkable locations or salary floors) and soft preferences.',
    details: 'Freshness scoring uses exact source_created_at UTC timestamps. If a posting omits a timestamp, JARVIS marks it as posting_date_unavailable rather than guessing.',
    code: 'ranked_jobs = rank_candidates(canonical_jobs, hard_filters=filters, soft_weights=prefs)',
  },
  {
    number: '05',
    title: 'Untrusted JD Understanding & Fact Extraction',
    icon: Cpu,
    color: 'text-fuchsia-400',
    tag: 'Phase 2 · JD Understanding',
    summary: 'Job descriptions are treated as untrusted data. Content is stripped of HTML scripts, length-capped, and parsed for verifiable requirements.',
    details: 'Every extracted fact carries an Evidence{text, field, method, confidence} tag quoting the verbatim JD text. Skills are mapped to a 400+ curated taxonomy with negative-context guards.',
    code: 'jd_analysis = analyze_jd(job.description, taxonomy=tech_taxonomy, fence_untrusted=True)',
  },
  {
    number: '06',
    title: 'Candidate Profile & PII Quarantine',
    icon: UserCheck,
    color: 'text-emerald-400',
    tag: 'Phase 3 · Candidate Intelligence',
    summary: 'Your uploaded resume is parsed into structured experience blocks, taxonomy skills, education credentials, and career preferences.',
    details: 'Contact PII (phone number, email address, physical location) is quarantined into an isolated security boundary so sensitive personal data never enters narration streams or external model prompts.',
    code: 'candidate_profile = parse_resume(raw_text, quarantine_pii=True, duration_threshold=0.8)',
  },
  {
    number: '07',
    title: '8-Factor Weighted Match & Gap Analysis',
    icon: Target,
    color: 'text-yellow-400',
    tag: 'Phase 4 · Match Engine',
    summary: 'Candidate skills and experiences are mathematically evaluated against JD requirements across 8 fixed weights.',
    details: 'Weights: Required Skills (30), Preferred Skills (10), Experience (20), Location (12), Employment Type (10), Education (8), Level (5), Salary (5). Tiers: Strong (≥75%), Moderate (≥50%). Missing items are flagged as actionable gaps.',
    code: 'match_score = (req_score * 0.30) + (pref_score * 0.10) + (exp_score * 0.20) + ...',
  },
  {
    number: '08',
    title: 'Strict Subset Resume Tailoring',
    icon: FileCheck,
    color: 'text-cyan-400',
    tag: 'Phase 5 · Tailoring Engine',
    summary: 'A tailored resume is synthesized to emphasize the experiences and keywords most relevant to the target job description.',
    details: 'Mathematical truth constraint: C_tailored ⊆ C_candidate. Tailoring re-orders highlights and selects matched achievements, but is forbidden from inserting unverified skills or fabricating metrics.',
    code: 'tailored_resume = tailor_resume(candidate_profile, target_jd, token_subset_guard=True)',
  },
  {
    number: '09',
    title: 'ATS Audit, T1–T10 Truth Verification & PDF Export',
    icon: ShieldCheck,
    color: 'text-rose-400',
    tag: 'Phase 6 & 7 · Audit & Studio',
    summary: 'The tailored resume undergoes a rigorous read-only verification before being rendered into an ATS-optimized vector PDF.',
    details: 'T1–T10 truth checks guarantee 100% fact containment and evidence resolvability (immediate FAIL if violated). A1–A8 checks audit keyword stuffing and layout standards. One-click PDF download exports your verified application.',
    code: 'validation_report = validate_tailored_resume(tailored_resume, evidence=candidate_evidence)',
  },
]

export function HowItWorksPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16">
      {/* Header */}
      <div className="text-center space-y-4 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-mono font-semibold">
          <Activity size={13} />
          <span>AUTONOMOUS PIPELINE LIFECYCLE</span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold text-white tracking-tight">
          How JARVIS Executes From Intent to Application
        </h1>
        <p className="text-base text-jarvis-muted leading-relaxed">
          Walk through the exact 9-step execution path taken by the sovereign LangGraph agent. Every single hop is deterministic, verifiable, and observable.
        </p>
      </div>

      {/* 9 Step Timeline */}
      <div className="space-y-6">
        {STEPS.map((step) => {
          const Icon = step.icon
          return (
            <div
              key={step.number}
              className="p-6 sm:p-8 rounded-2xl glass border border-jarvis-border/50 hover:border-blue-500/40 transition-all grid grid-cols-1 lg:grid-cols-12 gap-6 items-start"
            >
              {/* Step indicator (2 cols) */}
              <div className="lg:col-span-2 flex items-center lg:flex-col lg:items-start gap-3">
                <span className="text-3xl sm:text-4xl font-extrabold font-mono text-jarvis-muted/40">
                  {step.number}
                </span>
                <div className="w-10 h-10 rounded-xl bg-jarvis-surface flex items-center justify-center border border-jarvis-border">
                  <Icon className={step.color} size={20} />
                </div>
              </div>

              {/* Step Description (6 cols) */}
              <div className="lg:col-span-6 space-y-3">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono font-semibold uppercase px-2 py-0.5 rounded bg-blue-500/10 text-cyan-400 border border-blue-500/20">
                    {step.tag}
                  </span>
                  <h2 className="text-lg font-bold text-white">{step.title}</h2>
                </div>

                <p className="text-xs sm:text-sm text-jarvis-light leading-relaxed font-medium">
                  {step.summary}
                </p>

                <p className="text-xs text-jarvis-muted leading-relaxed">
                  {step.details}
                </p>
              </div>

              {/* Code Snippet / Guarantee (4 cols) */}
              <div className="lg:col-span-4 p-4 rounded-xl bg-black/50 border border-jarvis-border/40 font-mono text-[11px] space-y-2">
                <div className="flex items-center justify-between text-jarvis-muted/70 pb-1 border-b border-jarvis-border/30 text-[10px]">
                  <span>PIPELINE LOGIC</span>
                  <span className="text-emerald-400">Deterministic</span>
                </div>
                <div className="text-cyan-300 break-all leading-relaxed">{step.code}</div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Bottom Launch Banner */}
      <div className="p-8 sm:p-10 rounded-3xl bg-gradient-to-r from-blue-900/40 via-indigo-950/40 to-jarvis-darker border border-blue-500/30 text-center space-y-4">
        <h3 className="text-2xl font-bold text-white">Watch this pipeline execute live in the dashboard</h3>
        <p className="text-xs sm:text-sm text-jarvis-muted max-w-xl mx-auto">
          Connect your microphone or upload a resume to observe real-time LangGraph node transitions as they happen.
        </p>
        <div className="pt-2">
          <Link
            to="/app"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-500/25"
          >
            <span>Launch Interactive App</span>
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  )
}
