import { Link } from 'react-router-dom'
import {
  Mic,
  Search,
  Cpu,
  Target,
  FileCheck,
  ShieldCheck,
  ArrowRight,
  CheckCircle2,
  Layers
} from 'lucide-react'

const FEATURE_CATEGORIES = [
  {
    id: 'voice',
    title: 'Voice Sovereignty & Real-Time Orchestration',
    subtitle: 'Conversational voice built for speed, safety, and instant user interruption.',
    icon: Mic,
    color: 'text-cyan-400',
    borderColor: 'border-cyan-500/30',
    features: [
      {
        name: 'Instant Barge-In (Sub-18ms Interruption)',
        description: 'Speak at any moment while JARVIS is responding. The client immediately mutes audio output and cleanly renews the execution task without state corruption.',
      },
      {
        name: 'FastIntentRouter Dual Path (180ms TTFT)',
        description: 'High-frequency workspace navigation and filtering commands run through a deterministic regex grammar, bypassing cloud LLMs for near-instant execution.',
      },
      {
        name: 'Client-Side VAD & Privacy Isolation',
        description: 'Voice Activity Detection executes locally in your browser. Audio streams are kept in volatile memory and never retained or uploaded to third-party ad networks.',
      },
      {
        name: 'Web Speech API & Local STT/TTS Fallback',
        description: 'Seamless browser-native voice synthesis with optional local Whisper/Piper STT/TTS backend protocols.',
      },
    ],
  },
  {
    id: 'discovery',
    title: 'Multi-Source Radar & Deduplication',
    subtitle: 'Authentic job opportunities fetched directly from primary ATS APIs.',
    icon: Search,
    color: 'text-blue-400',
    borderColor: 'border-blue-500/30',
    features: [
      {
        name: 'Direct Greenhouse & Lever Public Adapters',
        description: 'Zero screen scraping. Connects directly to public ATS endpoints with jittered exponential backoff and strict token sanitization.',
      },
      {
        name: 'Cross-Source Entity Resolution & Deduplication',
        description: 'Clusters cross-posted jobs across multiple platforms, preserving the earliest source while consolidating distinct application endpoints.',
      },
      {
        name: 'Zero Timestamp Manufacture',
        description: 'Internal timestamps are UTC-aware and never hallucinated from vague display strings like "posted recently". Missing source dates remain explicitly None.',
      },
      {
        name: 'Google Jobs Engine Integration',
        description: 'Safe discovery integration with strict query whitelisting to eliminate quota burning and raw external URL execution.',
      },
    ],
  },
  {
    id: 'jd',
    title: 'Untrusted JD Understanding Engine',
    subtitle: 'Deterministic skill and requirement extraction with verifiable provenance.',
    icon: Cpu,
    color: 'text-violet-400',
    borderColor: 'border-violet-500/30',
    features: [
      {
        name: 'Untrusted Data Security Model',
        description: 'External job descriptions are fenced, script/style stripped, and character capped (JD_MAX_CHARS) to prevent prompt injection attacks.',
      },
      {
        name: 'Verifiable Evidence Architecture',
        description: 'Every extracted requirement, skill, and qualification carries Evidence{text, field, method, confidence} directly quoting the raw posting.',
      },
      {
        name: 'Curated 400+ Skill Taxonomy & Negative Guards',
        description: 'Recognizes industry technologies while applying negative-context guards (e.g., "no Kubernetes experience needed" will not match Kubernetes).',
      },
      {
        name: 'Currency-Anchored Salary Deconstruction',
        description: 'Converts compensation prose into structured min/max bounds only when anchored by unambiguous currency tokens.',
      },
    ],
  },
  {
    id: 'matching',
    title: '8-Factor Deterministic Match Engine',
    subtitle: 'Explainable, pure mathematical scoring with zero black-box bias.',
    icon: Target,
    color: 'text-emerald-400',
    borderColor: 'border-emerald-500/30',
    features: [
      {
        name: 'Fixed Weight Scoring Architecture',
        description: 'Required Skills (30), Preferred Skills (10), Experience (20), Location (12), Employment Type (10), Education (8), Level (5), Salary (5).',
      },
      {
        name: 'Tiered Affinity Classification',
        description: 'Clear classification into Strong (≥75%) and Moderate (≥50%) tiers. Missing job data never triggers hard rejections; evidence gaps are labeled.',
      },
      {
        name: 'Explicit Gap Analysis',
        description: 'Instantly surfaces exactly which requirements are missing or unaddressed, providing candidates with actionable feedback rather than silent rejections.',
      },
      {
        name: 'Deterministic Tie-Breaking',
        description: 'Identical scores break deterministically based on verified required skill count, then experience duration, eliminating random shuffling.',
      },
    ],
  },
  {
    id: 'tailoring',
    title: 'Truth-Guarded Resume Tailoring',
    subtitle: 'Dynamic re-alignment strictly constrained to candidate profile evidence.',
    icon: FileCheck,
    color: 'text-cyan-400',
    borderColor: 'border-cyan-500/30',
    features: [
      {
        name: 'Mathematical Token Containment Guard',
        description: 'Enforces C_tailored ⊆ C_candidate. Tailored resumes may emphasize or re-order existing achievements, but can NEVER invent new claims.',
      },
      {
        name: 'Immutable Profile Source of Truth',
        description: 'The candidate profile is never modified during tailoring. Tailoring generates a fresh artifact without contaminating your master history.',
      },
      {
        name: 'Verifiable Summary Synthesis',
        description: 'Generates professional career summaries composed exclusively of verified facts, technologies, and quantified achievements.',
      },
      {
        name: 'Missing Requirement Insulation',
        description: 'Unaddressed JD requirements are surfaced in a separate candidate advisory pane, never covertly inserted into your resume.',
      },
    ],
  },
  {
    id: 'validation',
    title: 'T1–T10 Truth & A1–A8 ATS Audit',
    subtitle: 'Automated dual-layer audit guaranteeing fact containment and ATS compliance.',
    icon: ShieldCheck,
    color: 'text-amber-400',
    borderColor: 'border-amber-500/30',
    features: [
      {
        name: 'T1–T10 Truth Verification (Immediate FAIL)',
        description: 'Validates original-text fidelity, evidence-ref resolvability, unsupported-skill detection, employer/title/date consistency, and duplicate suppression.',
      },
      {
        name: 'A1–A8 ATS Compliance Audits (Advisory WARN)',
        description: 'Measures keyword coverage %, responsibility token overlap, keyword density caps (<2x to prevent stuffing), and clean standard date-range separators.',
      },
      {
        name: 'T9 PII Quarantine & Zero-Retention Audit',
        description: 'Verifies that candidate phone numbers, emails, and street addresses are quarantined and never present in narration streams or public outputs.',
      },
      {
        name: 'Read-Only Integrity Guarantee',
        description: 'The validation node is strictly read-only. It reports objective scores and warnings without silently mutating or corrupting the tailored artifact.',
      },
    ],
  },
]

export function FeaturesPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16">
      {/* Header */}
      <div className="text-center space-y-4 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-cyan-400 text-xs font-mono font-semibold">
          <Layers size={13} />
          <span>CAPABILITY MATRIX</span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold text-white tracking-tight">
          Engineered Without Compromise
        </h1>
        <p className="text-base text-jarvis-muted leading-relaxed">
          Explore the technical capabilities powering JARVIS. Every feature is deterministically designed to maximize job search precision while guaranteeing zero hallucination.
        </p>
      </div>

      {/* Feature Categories Grid */}
      <div className="space-y-12">
        {FEATURE_CATEGORIES.map((cat) => {
          const Icon = cat.icon
          return (
            <div
              key={cat.id}
              className={`p-6 sm:p-8 rounded-3xl glass border ${cat.borderColor} space-y-6 relative overflow-hidden`}
            >
              {/* Top Category Title */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-jarvis-border/40 pb-5">
                <div className="flex items-center gap-3.5">
                  <div className="w-12 h-12 rounded-2xl bg-jarvis-surface flex items-center justify-center border border-jarvis-border/60">
                    <Icon className={cat.color} size={24} />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-white">{cat.title}</h2>
                    <p className="text-xs sm:text-sm text-jarvis-muted mt-0.5">{cat.subtitle}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono px-2.5 py-1 rounded-lg bg-jarvis-surface text-jarvis-light border border-jarvis-border/40">
                    Deterministic v0.2.0
                  </span>
                </div>
              </div>

              {/* 4 Feature Items */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {cat.features.map((feat) => (
                  <div
                    key={feat.name}
                    className="p-5 rounded-2xl bg-jarvis-surface/40 hover:bg-jarvis-surface/70 border border-jarvis-border/40 transition-all space-y-2"
                  >
                    <div className="flex items-center gap-2">
                      <CheckCircle2 size={16} className={cat.color} />
                      <h3 className="text-sm font-bold text-white">{feat.name}</h3>
                    </div>
                    <p className="text-xs text-jarvis-muted leading-relaxed pl-6">
                      {feat.description}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* Bottom CTA */}
      <div className="p-8 rounded-2xl bg-gradient-to-r from-blue-900/30 via-indigo-950/40 to-jarvis-darker border border-blue-500/30 flex flex-col sm:flex-row items-center justify-between gap-6 text-center sm:text-left">
        <div>
          <h3 className="text-lg font-bold text-white">Experience the full capability stack live.</h3>
          <p className="text-xs text-jarvis-muted mt-1">
            Launch the interactive JARVIS application with zero installation required.
          </p>
        </div>
        <Link
          to="/app"
          className="px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs shadow-lg shadow-blue-500/25 flex items-center gap-2 whitespace-nowrap"
        >
          <span>Launch JARVIS App</span>
          <ArrowRight size={14} />
        </Link>
      </div>
    </div>
  )
}
