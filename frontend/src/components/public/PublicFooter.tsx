import { Link } from 'react-router-dom'
import { Activity, Github, Shield, Zap, ArrowUpRight, Cpu } from 'lucide-react'

export function PublicFooter() {
  return (
    <footer className="border-t border-jarvis-border/40 bg-jarvis-darker/90 backdrop-blur-xl text-jarvis-muted relative z-10">
      {/* Top Border Glow Accent */}
      <div className="h-[1px] w-full bg-gradient-to-r from-transparent via-blue-500/30 to-transparent" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-14 lg:py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-10 lg:gap-8">
          {/* Brand Column */}
          <div className="lg:col-span-2 space-y-4">
            <Link to="/" className="flex items-center gap-3 group focus:outline-none">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 via-indigo-600 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-500/25 group-hover:scale-105 transition-transform">
                <Activity className="text-white" size={18} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-base font-bold text-white tracking-wider font-mono">J.A.R.V.I.S</span>
                  <span className="text-[10px] uppercase font-semibold tracking-widest px-1.5 py-0.5 rounded bg-blue-500/10 text-cyan-400 border border-cyan-500/30">
                    Agentic OS
                  </span>
                </div>
                <p className="text-[10px] text-jarvis-muted tracking-widest uppercase font-medium">Career Intelligence</p>
              </div>
            </Link>

            <p className="text-sm text-jarvis-muted leading-relaxed max-w-sm">
              Sovereign real-time voice AI and deterministic career operating system. Powered by LangGraph, strict truth-guarded tailoring, and untrusted-data containment.
            </p>

            <div className="flex items-center gap-3 pt-2">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[11px] font-medium text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span>All Engines Operational</span>
              </div>
              <span className="text-xs text-jarvis-muted/60 font-mono">v0.2.0-FROZEN</span>
            </div>
          </div>

          {/* Product Links */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white font-mono">Product</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/features" className="hover:text-cyan-400 transition-colors flex items-center gap-1">
                  Features
                </Link>
              </li>
              <li>
                <Link to="/voice-agent" className="hover:text-cyan-400 transition-colors flex items-center gap-1.5">
                  Voice Agent
                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-300 font-mono">Realtime</span>
                </Link>
              </li>
              <li>
                <Link to="/career-intelligence" className="hover:text-cyan-400 transition-colors">
                  Career Radar
                </Link>
              </li>
              <li>
                <Link to="/how-it-works" className="hover:text-cyan-400 transition-colors">
                  How It Works
                </Link>
              </li>
              <li>
                <Link to="/app" className="hover:text-cyan-400 transition-colors flex items-center gap-1 text-blue-400 font-medium">
                  Launch Dashboard
                  <ArrowUpRight size={13} />
                </Link>
              </li>
            </ul>
          </div>

          {/* Technical Architecture */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white font-mono">Architecture</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/architecture" className="hover:text-cyan-400 transition-colors">
                  LangGraph Engine
                </Link>
              </li>
              <li>
                <Link to="/architecture" className="hover:text-cyan-400 transition-colors flex items-center gap-1">
                  Truth Guard (T1–T10)
                </Link>
              </li>
              <li>
                <Link to="/career-intelligence" className="hover:text-cyan-400 transition-colors">
                  ATS Audit (A1–A8)
                </Link>
              </li>
              <li>
                <Link to="/voice-agent" className="hover:text-cyan-400 transition-colors">
                  Fast Intent Router
                </Link>
              </li>
              <li>
                <Link to="/about" className="hover:text-cyan-400 transition-colors">
                  Sovereign AI Manifesto
                </Link>
              </li>
            </ul>
          </div>

          {/* Resources & Docs */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white font-mono">Resources</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/docs" className="hover:text-cyan-400 transition-colors">
                  Documentation Hub
                </Link>
              </li>
              <li>
                <Link to="/docs" className="hover:text-cyan-400 transition-colors">
                  API & WebSocket Protocol
                </Link>
              </li>
              <li>
                <Link to="/about" className="hover:text-cyan-400 transition-colors">
                  About the Project
                </Link>
              </li>
              <li>
                <a
                  href="https://github.com"
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-cyan-400 transition-colors flex items-center gap-1.5"
                >
                  <Github size={14} />
                  <span>GitHub Repository</span>
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="mt-12 pt-8 border-t border-jarvis-border/20 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-4 text-jarvis-muted/70">
            <span>© 2026 J.A.R.V.I.S Project. Open architecture.</span>
            <span>•</span>
            <span className="flex items-center gap-1">
              <Shield size={12} className="text-emerald-400" />
              <span>PII-Quarantine Enforced</span>
            </span>
          </div>

          <div className="flex items-center gap-5 text-jarvis-muted/70">
            <span className="flex items-center gap-1">
              <Cpu size={12} className="text-cyan-400" />
              <span>Zero-Hallucination Guarantee</span>
            </span>
            <span>•</span>
            <span className="flex items-center gap-1">
              <Zap size={12} className="text-yellow-400" />
              <span>LangGraph Frozen Pipeline</span>
            </span>
          </div>
        </div>
      </div>
    </footer>
  )
}
