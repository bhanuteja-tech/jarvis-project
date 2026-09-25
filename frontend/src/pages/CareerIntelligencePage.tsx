import { Link } from 'react-router-dom'
import {
  Target,
  ShieldCheck,
  ArrowRight,
  Lock
} from 'lucide-react'

const MATCHING_WEIGHTS = [
  { factor: 'Required Skills Overlap', weight: '30%', desc: 'Hard requirements extracted from explicit JD sections with curated taxonomy mapping.' },
  { factor: 'Candidate Experience Duration', weight: '20%', desc: 'Calculated only when explicit dates provide ≥80% total employment coverage.' },
  { factor: 'Location & Work Mode Alignment', weight: '12%', desc: 'Remote, Hybrid, or On-site tolerance matched against candidate preferences.' },
  { factor: 'Preferred / Bonus Skills', weight: '10%', desc: 'Nice-to-have competencies that enhance match tier without hard disqualification.' },
  { factor: 'Employment Type', weight: '10%', desc: 'Full-time, Contract, or Part-time matching.' },
  { factor: 'Education Credentials', weight: '8%', desc: 'Degree level and discipline alignment.' },
  { factor: 'Seniority Level', weight: '5%', desc: 'Staff, Principal, Senior, or Lead career positioning.' },
  { factor: 'Compensation Range', weight: '5%', desc: 'Currency-anchored salary floor and target ceiling verification.' },
]

const TRUTH_CHECKS = [
  { id: 'T1', name: 'Token Containment Guard', desc: 'Guarantees that every token in the tailored resume exists within verified candidate evidence.' },
  { id: 'T2', name: 'Original Text Fidelity', desc: 'Verifies verbatim accuracy of historical titles, companies, and quantifiable metrics.' },
  { id: 'T3', name: 'Evidence-Ref Resolvability', desc: 'Every bullet point must trace directly to a valid candidate profile citation.' },
  { id: 'T4', name: 'Unsupported Skill Detection', desc: 'Catches and rejects any technical skill not explicitly confirmed in your profile.' },
  { id: 'T5', name: 'Missing Required Insertion Guard', desc: 'Prevents the model from fabricating skills just to boost ATS keyword scores.' },
  { id: 'T6', name: 'Employer & Title Consistency', desc: 'Strict chronological and organizational coherence check.' },
  { id: 'T7', name: 'Project & Technology Consistency', desc: 'Confirms that listed technologies match the actual projects they were used in.' },
  { id: 'T8', name: 'Duplicate Bullet Suppression', desc: 'Eliminates repetitive or stuffed achievement statements.' },
  { id: 'T9', name: 'PII Absence Count-Only Check', desc: 'Confirms that personal phone numbers and street addresses never leak into outputs.' },
  { id: 'T10', name: 'Metadata Consistency', desc: 'Validates version stamps, timestamp formats, and schema compliance.' },
]

const ATS_CHECKS = [
  { id: 'A1', name: 'Required Skill Keyword Density', desc: 'Measures verbatim keyword coverage across target job requirements.' },
  { id: 'A2', name: 'Responsibility Token Coverage', desc: 'Analyzes semantic alignment with target position duties.' },
  { id: 'A3', name: 'Keyword Stuffing Suspicion Cap', desc: 'Flags any keyword repeated >2x above normal natural distribution.' },
  { id: 'A4', name: 'Section Order Standard', desc: 'Enforces standard ATS parsing flow: Summary, Experience, Skills, Education.' },
  { id: 'A5', name: 'Clean Typography & Hierarchy', desc: 'Audits font compatibility, header weights, and bullet structures.' },
  { id: 'A6', name: 'Date-Range Standard Separators', desc: 'Standardizes date formats (e.g., YYYY-MM – Present) for accurate scanner OCR.' },
  { id: 'A7', name: 'Unverifiable Metric Warning', desc: 'Highlights any metric requiring explicit context clarification.' },
  { id: 'A8', name: 'Length & Format Constraints', desc: 'Checks 1-to-2 page length boundaries and column readability.' },
]

export function CareerIntelligencePage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16">
      {/* Header */}
      <div className="text-center space-y-4 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono font-semibold">
          <Target size={13} />
          <span>DETERMINISTIC CAREER INTELLIGENCE</span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold text-white tracking-tight">
          Math Over Magic. Evidence Over Guesswork.
        </h1>
        <p className="text-base text-jarvis-muted leading-relaxed">
          Career matching is too important to leave to black-box LLMs that hallucinate metrics and fabricate qualifications. JARVIS applies rigorous mathematical containment and transparent scoring algorithms.
        </p>
      </div>

      {/* 8-Factor Match Engine Breakdown */}
      <div className="p-6 sm:p-8 rounded-3xl glass border border-emerald-500/30 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-jarvis-border/40 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono uppercase tracking-widest text-emerald-400 font-bold">PHASE 4 ENGINE</span>
              <span className="text-xs text-jarvis-muted">·</span>
              <h2 className="text-xl font-bold text-white">The 8-Factor Deterministic Matching Algorithm</h2>
            </div>
            <p className="text-xs sm:text-sm text-jarvis-muted mt-1">
              Every job match score is a transparent weighted sum. Tiers: Strong Match (≥75%) and Moderate Match (≥50%).
            </p>
          </div>
          <span className="text-xs font-mono px-3 py-1.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 whitespace-nowrap">
            100% Explainable
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {MATCHING_WEIGHTS.map((item) => (
            <div
              key={item.factor}
              className="p-4 rounded-2xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2 hover:border-emerald-500/30 transition-all"
            >
              <div className="flex items-center justify-between">
                <span className="text-xl font-bold font-mono text-emerald-400">{item.weight}</span>
                <span className="text-[10px] font-mono text-jarvis-muted uppercase">Weight</span>
              </div>
              <h3 className="text-sm font-bold text-white">{item.factor}</h3>
              <p className="text-xs text-jarvis-muted leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Truth Guard Token Containment */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
        <div className="lg:col-span-6 space-y-4">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-mono font-semibold">
            <Lock size={12} />
            <span>MATHEMATICAL TRUTH ENFORCEMENT</span>
          </div>
          <h2 className="text-3xl font-bold text-white tracking-tight">
            The Token Containment Guard: C_tailored ⊆ C_evidence
          </h2>
          <p className="text-sm text-jarvis-muted leading-relaxed">
            When other AI tools tailor resumes, they often fabricate achievements, invent missing technologies, and manufacture dates to bypass ATS filters. This leads to awkward interviews and revoked job offers.
          </p>
          <p className="text-sm text-jarvis-muted leading-relaxed">
            JARVIS treats your verified profile as an immutable ground truth. The tailored resume can highlight, re-order, and summarize verified evidence, but can <strong>never invent a single token</strong>. Any unaddressed job requirement is explicitly flagged to you, never covertly inserted.
          </p>
          <div className="p-4 rounded-xl bg-cyan-950/20 border border-cyan-500/30 text-xs font-mono text-cyan-300">
            Truth Rule: For every fact F in TailoredResume, there exists an explicit citation E in CandidateProfile such that F ⊆ E.
          </div>
        </div>

        <div className="lg:col-span-6 p-6 rounded-2xl glass border border-jarvis-border/60 space-y-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <ShieldCheck className="text-cyan-400" size={18} />
            <span>T1–T10 Truth Verification Suite (Immediate FAIL)</span>
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            {TRUTH_CHECKS.map((chk) => (
              <div key={chk.id} className="p-2.5 rounded-lg bg-black/40 border border-jarvis-border/30">
                <div className="flex items-center gap-1.5 font-bold text-cyan-300">
                  <span className="font-mono text-[10px] px-1.5 py-0.2 rounded bg-cyan-500/10">{chk.id}</span>
                  <span>{chk.name}</span>
                </div>
                <p className="text-[11px] text-jarvis-muted mt-1">{chk.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ATS Compliance Suite */}
      <div className="p-6 sm:p-8 rounded-3xl glass border border-amber-500/30 space-y-6">
        <div className="flex items-center justify-between border-b border-jarvis-border/40 pb-4">
          <div>
            <span className="text-xs font-mono uppercase tracking-widest text-amber-400 font-bold">ADVISORY AUDIT</span>
            <h2 className="text-xl font-bold text-white mt-1">A1–A8 ATS Scanner Compliance Matrix</h2>
          </div>
          <span className="text-xs font-mono px-3 py-1 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/30">
            Advisory WARN Only
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {ATS_CHECKS.map((chk) => (
            <div key={chk.id} className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs font-bold text-amber-300">
                <span className="font-mono text-[10px] px-1.5 py-0.2 rounded bg-amber-500/10">{chk.id}</span>
                <span>{chk.name}</span>
              </div>
              <p className="text-[11px] text-jarvis-muted leading-relaxed">{chk.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* CTA */}
      <div className="p-8 rounded-2xl bg-gradient-to-r from-blue-900/30 via-emerald-950/30 to-jarvis-darker border border-emerald-500/30 flex flex-col sm:flex-row items-center justify-between gap-6">
        <div>
          <h3 className="text-lg font-bold text-white">Upload your resume to see your verified match score.</h3>
          <p className="text-xs text-jarvis-muted mt-1">Test your resume against live Greenhouse and Lever job postings.</p>
        </div>
        <Link
          to="/app"
          className="px-6 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs shadow-lg shadow-emerald-500/25 flex items-center gap-2"
        >
          <span>Open Career Radar</span>
          <ArrowRight size={14} />
        </Link>
      </div>
    </div>
  )
}
