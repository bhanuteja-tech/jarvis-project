import { Link } from 'react-router-dom'
import {
  Zap,
  Radio,
  Shield,
  ArrowRight,
  Cpu,
  Terminal
} from 'lucide-react'
import { VoiceStateDemo } from '../components/public/VoiceStateDemo'
import { AgentDemoVisualizer } from '../components/public/AgentDemoVisualizer'

export function VoiceAgentPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16">
      {/* Header */}
      <div className="text-center space-y-4 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-mono font-semibold">
          <Radio size={13} />
          <span>SOVEREIGN VOICE ENGINE</span>
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold text-white tracking-tight">
          Real-Time Voice with Instant Barge-In
        </h1>
        <p className="text-base text-jarvis-muted leading-relaxed">
          Most voice assistants require 2 to 4 seconds of latency and lock you out while speaking. JARVIS delivers sub-180ms Time-to-First-Token responses with client-side barge-in interruption.
        </p>
      </div>

      {/* Voice State Interactive Demo */}
      <div className="space-y-4">
        <VoiceStateDemo />
      </div>

      {/* Deep-Dive Technical Architecture */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-2xl glass border border-jarvis-border/60 space-y-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <Zap size={20} />
          </div>
          <h3 className="text-base font-bold text-white">Sub-18ms Barge-In Cancellation</h3>
          <p className="text-xs text-jarvis-muted leading-relaxed">
            When speech is detected while JARVIS is speaking, an immediate interruption token is dispatched. The browser halts audio synthesis workers in under 18ms and safely re-arms the listener.
          </p>
        </div>

        <div className="p-6 rounded-2xl glass border border-jarvis-border/60 space-y-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400">
            <Cpu size={20} />
          </div>
          <h3 className="text-base font-bold text-white">FastIntentRouter Dual Path</h3>
          <p className="text-xs text-jarvis-muted leading-relaxed">
            Everyday operational intents ("pause", "show matches", "filter salary", "open PDF") execute through a deterministic state grammar, eliminating cloud LLM token generation latency.
          </p>
        </div>

        <div className="p-6 rounded-2xl glass border border-jarvis-border/60 space-y-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Shield size={20} />
          </div>
          <h3 className="text-base font-bold text-white">Zero Audio Cloud Retention</h3>
          <p className="text-xs text-jarvis-muted leading-relaxed">
            Voice Activity Detection (VAD) runs locally inside your browser window. Audio samples are never stored to disk, passed to advertisers, or retained for corporate model training.
          </p>
        </div>
      </div>

      {/* Live Agent Preview */}
      <div className="space-y-6">
        <div className="text-center space-y-2">
          <span className="text-xs font-mono uppercase tracking-widest text-cyan-400 font-bold">
            INTERACTIVE AGENT EXECUTION
          </span>
          <h2 className="text-2xl sm:text-3xl font-bold text-white">
            See Voice Transitions Drive LangGraph Nodes
          </h2>
        </div>
        <AgentDemoVisualizer />
      </div>

      {/* Acoustic State Machine Specifications */}
      <div className="p-6 sm:p-8 rounded-2xl glass border border-jarvis-border/60 space-y-6">
        <h3 className="text-lg font-bold text-white flex items-center gap-2">
          <Terminal className="text-cyan-400" size={18} />
          <span>Acoustic State Machine Specification</span>
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 font-mono text-xs">
          <div className="p-4 rounded-xl bg-black/40 border border-jarvis-border/40 space-y-1.5">
            <div className="text-cyan-400 font-bold">1. IDLE</div>
            <p className="text-jarvis-muted text-[11px]">WebSocket connected. Listener armed. Zero CPU usage.</p>
          </div>

          <div className="p-4 rounded-xl bg-black/40 border border-amber-500/30 space-y-1.5">
            <div className="text-amber-400 font-bold">2. LISTENING</div>
            <p className="text-jarvis-muted text-[11px]">VAD threshold crossed. Capturing audio tokens in-memory.</p>
          </div>

          <div className="p-4 rounded-xl bg-black/40 border border-blue-500/30 space-y-1.5">
            <div className="text-blue-400 font-bold">3. ACTING</div>
            <p className="text-jarvis-muted text-[11px]">Intent router classifies command; LangGraph state update begins.</p>
          </div>

          <div className="p-4 rounded-xl bg-black/40 border border-emerald-500/30 space-y-1.5">
            <div className="text-emerald-400 font-bold">4. SPEAKING</div>
            <p className="text-jarvis-muted text-[11px]">Streaming audio synthesized. Barge-in monitor active.</p>
          </div>
        </div>
      </div>

      {/* CTA */}
      <div className="p-8 rounded-2xl bg-gradient-to-r from-blue-900/30 via-cyan-950/30 to-jarvis-darker border border-cyan-500/30 flex flex-col sm:flex-row items-center justify-between gap-6">
        <div>
          <h3 className="text-lg font-bold text-white">Ready to speak with JARVIS?</h3>
          <p className="text-xs text-jarvis-muted mt-1">Open the app dashboard and click the microphone icon.</p>
        </div>
        <Link
          to="/app"
          className="px-6 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs shadow-lg shadow-cyan-500/25 flex items-center gap-2"
        >
          <span>Launch Voice App</span>
          <ArrowRight size={14} />
        </Link>
      </div>
    </div>
  )
}
