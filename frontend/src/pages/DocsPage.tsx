import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BookOpen,
  Terminal,
  Mic,
  Search,
  ShieldCheck,
  HelpCircle,
  ArrowRight,
  Copy,
  Check
} from 'lucide-react'

interface DocSection {
  id: string
  title: string
  icon: any
  content: {
    heading: string
    body: string
    codeSnippet?: string
    notes?: string[]
  }[]
}

const DOC_SECTIONS: DocSection[] = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    icon: Terminal,
    content: [
      {
        heading: 'Quickstart Installation',
        body: 'JARVIS requires Python 3.11+ for the backend and Node.js 18+ for the React frontend.',
        codeSnippet: `# Clone and setup backend
git clone https://github.com/your-org/jarvis-project.git
cd jarvis-project
pip install -e ".[dev]"

# Run database migrations (optional for persistent runs)
alembic upgrade head

# Start FastAPI backend server
uvicorn app.main:create_app --factory --reload --port 8000

# In a second terminal, launch React frontend
cd frontend
npm install
npm run dev`,
        notes: [
          'The frontend starts at http://localhost:3000 and connects via WebSocket to ws://localhost:8000/ws/jarvis.',
          'Sessions are in-memory by default and safely isolated per browser tab.',
        ],
      },
      {
        heading: 'Environment Configuration',
        body: 'Copy .env.example to .env. Most features run locally with zero API keys required.',
        codeSnippet: `# .env configuration
JARVIS_LOG_LEVEL=INFO
JARVIS_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/jarvis
SEARCHAPI_API_KEY=your_optional_searchapi_key`,
      },
    ],
  },
  {
    id: 'voice-agent',
    title: 'Voice Agent & Barge-In',
    icon: Mic,
    content: [
      {
        heading: 'Client-Side VAD & Instant Interruption',
        body: 'The voice agent uses browser-native Web Speech API or Web Audio API with local Voice Activity Detection. When the user speaks while JARVIS is responding, an interruption signal is dispatched immediately.',
        codeSnippet: `// Barge-in interruption protocol
function handleVoiceInterruption() {
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel();
  }
  socket.send(JSON.stringify({
    type: "voice_barge_in",
    timestamp: Date.now()
  }));
}`,
        notes: [
          'Interruption latency is sub-18 milliseconds.',
          'Audio frames are processed in-memory and never written to disk.',
        ],
      },
      {
        heading: 'FastIntentRouter Grammar',
        body: 'High-frequency operational commands bypass external LLMs and execute within 45ms using deterministic pattern matching.',
      },
    ],
  },
  {
    id: 'job-radar',
    title: 'Multi-Source Radar & Deduplication',
    icon: Search,
    content: [
      {
        heading: 'ATS Source Adapters',
        body: 'JARVIS queries authentic public career endpoints directly without screen scraping.',
        codeSnippet: `# Fetching from Greenhouse and Lever concurrently
jobs = await discover_jobs(
    boards=["datadog", "stripe", "anthropic"],
    lever_sites=["netflix", "palantir"],
    query="Staff Distributed Systems"
)`,
        notes: [
          'Lever uses v0 public API bare arrays only (rejects authenticated v1 structures).',
          'Google Jobs identity uses gj:<htidocid> or deterministic uuid5 fallback.',
        ],
      },
    ],
  },
  {
    id: 'truth-guard',
    title: 'Truth Guard (T1–T10) & ATS Audit',
    icon: ShieldCheck,
    content: [
      {
        heading: 'Mathematical Token Containment Guard',
        body: 'The Phase 6 Validation Engine executes read-only truth checks (T1–T10) and advisory ATS audits (A1–A8).',
        codeSnippet: `# Phase 6 Truth Validation
validation_report = validate_resume(
    tailored_resume=state["tailored_resume"],
    candidate_profile=state["candidate_profile"],
    jd_analysis=target_jd
)
if not validation_report.is_valid:
    logger.error("Truth guard rejected tailored resume: %s", validation_report.failures)`,
        notes: [
          'Any invented skill or hallucinated achievement fails the report immediately.',
          'T9 PII check reports counts only; captured contact values never appear in results or logs.',
        ],
      },
    ],
  },
  {
    id: 'troubleshooting',
    title: 'Troubleshooting & FAQ',
    icon: HelpCircle,
    content: [
      {
        heading: 'Common Questions',
        body: 'Frequently asked questions regarding permissions and local deployment.',
        notes: [
          'Microphone Not Detected: Ensure browser permissions allow microphone access for http://localhost:3000.',
          'WebSocket Disconnected: Check that the FastAPI server is running on port 8000 and CORS is enabled.',
          'Zero-Hallucination Rejection: If tailoring fails, verify that all skills in your resume are listed in explicit text.',
        ],
      },
    ],
  },
]

export function DocsPage() {
  const [activeSectionId, setActiveSectionId] = useState<string>('getting-started')
  const [copiedCode, setCopiedCode] = useState<string | null>(null)

  const activeSection = DOC_SECTIONS.find((s) => s.id === activeSectionId) || DOC_SECTIONS[0]

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedCode(text)
    setTimeout(() => setCopiedCode(null), 2000)
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      {/* Header */}
      <div className="border-b border-jarvis-border/40 pb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen className="text-cyan-400" size={20} />
            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Documentation Hub</h1>
          </div>
          <p className="text-xs sm:text-sm text-jarvis-muted mt-1">
            Developer guides, pipeline contracts, and operational reference manuals.
          </p>
        </div>

        <Link
          to="/app"
          className="self-start sm:self-auto px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs shadow-md shadow-blue-500/20 flex items-center gap-1.5"
        >
          <span>Open Application</span>
          <ArrowRight size={13} />
        </Link>
      </div>

      {/* Main Docs Grid: Sidebar + Content */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Sidebar (4 cols) */}
        <div className="lg:col-span-4 p-4 rounded-2xl glass border border-jarvis-border/50 space-y-1.5 sticky top-24">
          <div className="text-[11px] font-mono uppercase tracking-wider text-jarvis-muted px-3 py-1 font-bold">
            Documentation Index
          </div>
          {DOC_SECTIONS.map((section) => {
            const Icon = section.icon
            const isActive = activeSectionId === section.id
            return (
              <button
                key={section.id}
                onClick={() => setActiveSectionId(section.id)}
                className={`w-full p-2.5 rounded-xl text-left text-xs font-medium flex items-center gap-2.5 transition-all ${
                  isActive
                    ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20 font-semibold'
                    : 'text-jarvis-muted hover:text-white hover:bg-jarvis-surface/60'
                }`}
              >
                <Icon size={15} className={isActive ? 'text-white' : 'text-cyan-400'} />
                <span>{section.title}</span>
              </button>
            )
          })}

          <div className="pt-4 mt-4 border-t border-jarvis-border/30 px-3">
            <div className="text-[11px] text-jarvis-muted">
              Looking for architecture invariants? See the <Link to="/architecture" className="text-cyan-400 hover:underline">Architecture Spec</Link>.
            </div>
          </div>
        </div>

        {/* Content Area (8 cols) */}
        <div className="lg:col-span-8 space-y-8">
          {activeSection.content.map((block, idx) => (
            <div key={idx} className="p-6 sm:p-8 rounded-2xl glass border border-jarvis-border/50 space-y-4">
              <h2 className="text-xl font-bold text-white">{block.heading}</h2>
              <p className="text-sm text-jarvis-light leading-relaxed">{block.body}</p>

              {block.codeSnippet && (
                <div className="relative rounded-xl overflow-hidden border border-jarvis-border/60 bg-black/70">
                  <div className="h-8 bg-jarvis-surface/80 border-b border-jarvis-border/40 px-3 flex items-center justify-between text-[11px] font-mono text-jarvis-muted">
                    <span>bash / python</span>
                    <button
                      onClick={() => copyToClipboard(block.codeSnippet!)}
                      className="flex items-center gap-1 hover:text-white transition-colors"
                      title="Copy code"
                    >
                      {copiedCode === block.codeSnippet ? (
                        <>
                          <Check size={12} className="text-emerald-400" />
                          <span className="text-emerald-400">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy size={12} />
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                  </div>
                  <pre className="p-4 text-xs font-mono text-cyan-200 overflow-x-auto leading-relaxed">
                    {block.codeSnippet}
                  </pre>
                </div>
              )}

              {block.notes && block.notes.length > 0 && (
                <div className="p-4 rounded-xl bg-blue-950/20 border border-blue-500/20 space-y-1.5">
                  <div className="text-xs font-mono font-bold text-cyan-400">KEY CONSIDERATIONS:</div>
                  <ul className="space-y-1 text-xs text-jarvis-muted">
                    {block.notes.map((note, nIdx) => (
                      <li key={nIdx} className="flex items-start gap-2">
                        <span className="text-cyan-400 mt-0.5">•</span>
                        <span>{note}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
