import { Link } from 'react-router-dom'
import {
  Laptop,
  ShieldCheck,
  Key,
  Eye,
  ArrowRight,
  Lock
} from 'lucide-react'

const CAPABILITY_PILLARS = [
  {
    id: 'permissions',
    title: 'The Human Gate & Permission Architecture',
    tagline: 'High-risk operations cannot happen on your machine without your active consent.',
    icon: Key,
    accent: '#D97736',
    items: [
      {
        name: 'The Safety Interlock Barrier',
        desc: 'Before executing any destructive operation (e.g. deleting files, dispatching outbound emails or WhatsApp messages, installing packages), the agent pauses and presents the exact blast radius for your physical approval.',
      },
      {
        name: 'Independent Timeout Clock',
        desc: 'Confirmation prompts run on their own countdown timer (default 30 seconds). If you step away from your keyboard and do not approve the prompt, the action aborts cleanly rather than executing in your absence.',
      },
      {
        name: 'No Ambient Auto-Approval',
        desc: 'Automatic approval is intentionally locked behind a verbose, explicit flag (--i-understand-this-disables-safety-prompts). The agent cannot silently default to bypass prompts.',
      },
    ],
  },
  {
    id: 'device-isolation',
    title: 'Physical Device Identity & Disconnect Recovery',
    tagline: 'Your computer is protected against transient network drops and unauthorized device takeovers.',
    icon: Laptop,
    accent: '#2EA069',
    items: [
      {
        name: 'Persistent Hardware Device ID',
        desc: 'Every local agent companion is issued a persistent hardware identifier (~/.jarvis/device_id). Only the exact physical machine that started an action can reconnect and resume it.',
      },
      {
        name: '15-Second Disconnect Grace Period',
        desc: 'If your laptop sleeps or your Wi-Fi blips mid-task, Jarvis freezes in-flight actions for 15 seconds. If your machine reconnects within the window, execution resumes cleanly without failure.',
      },
      {
        name: 'Duplicate Connection Rejection',
        desc: 'If another machine attempts to bind to your session during an active run or grace period, it is rejected immediately with a policy violation. A second computer can never quietly hijack control.',
      },
    ],
  },
  {
    id: 'grounding',
    title: 'Zero-Guess Grounding & Context Awareness',
    tagline: 'The agent navigates your desktop by inspecting verified system state, not guessing.',
    icon: Eye,
    accent: '#828997',
    items: [
      {
        name: 'Verified Application & Window Tracking',
        desc: 'Jarvis tracks the real active window title, process ID, and filesystem directory before and after every step. It never assumes an application launched just because it issued a launch command.',
      },
      {
        name: 'Natural Follow-Up Memory',
        desc: 'When you say "How many folders are in my Documents?", then "What are those?", and then "Open the second one", the agent resolves the ordinal reference against verified filesystem items rather than confusing it with a web tab.',
      },
      {
        name: 'Sub-18ms Voice Barge-In',
        desc: 'You can interrupt Jarvis at any time by speaking. Audio playback cuts off within 18 milliseconds, the agent clears pending narration, and adapts immediately to your spoken correction.',
      },
    ],
  },
  {
    id: 'privacy',
    title: 'Local Privacy & Strict Domain Boundaries',
    tagline: 'Your files, credentials, and browsing state remain on your hardware.',
    icon: Lock,
    accent: '#2EA069',
    items: [
      {
        name: 'Zero Cloud Sandbox Uploads',
        desc: 'Actions are dispatched to your machine through jarvis_agent. Your browser sessions, cookies, downloaded documents, and project folders stay strictly local.',
      },
      {
        name: 'Domain-Exclusive Endpoints',
        desc: 'Sessions are hard-locked to their respective domain (/ws/computer vs /ws/career). Career search tools cannot touch desktop APIs, and computer control tools cannot access unrelated resume profiles.',
      },
      {
        name: 'Quarantined Personal Data',
        desc: 'Sensitive user credentials and contact information are stored in an encrypted vault and never injected into conversational LLM prompts.',
      },
    ],
  },
]

export function FeaturesPage() {
  return (
    <div className="min-h-screen bg-[#0E1013] text-[#E1E4EA] selection:bg-[#D97736]/20 selection:text-[#E1E4EA] pb-20">
      {/* Header Rail */}
      <div className="border-b border-[#262B35] bg-[#16191E] px-4 sm:px-8 py-3 text-xs flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 hover:opacity-90">
          <span className="w-2 h-2 rounded-full bg-[#2EA069]" />
          <span className="font-semibold text-[#E1E4EA]">JARVIS</span>
          <span className="text-[#828997]">/ System Capabilities</span>
        </Link>
        <Link to="/app/computer" className="text-[#D97736] hover:underline font-mono text-[11px]">
          Launch Console →
        </Link>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-8 pt-10 space-y-16">
        {/* Title & Introduction */}
        <div className="space-y-4 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded bg-[#16191E] border border-[#262B35] text-xs font-mono text-[#2EA069]">
            <ShieldCheck size={14} />
            <span>Architecture & Safety Verification</span>
          </div>

          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-[#E1E4EA] font-sans">
            How Jarvis Keeps You in Control
          </h1>

          <p className="text-sm sm:text-base text-[#828997] leading-relaxed">
            Granting an autonomous agent access to your keyboard and screen requires uncompromising architectural safeguards.
            Here is the complete overview of how permissions, hardware isolation, and verified execution protect your machine.
          </p>
        </div>

        {/* Pillars */}
        <div className="space-y-12">
          {CAPABILITY_PILLARS.map((pillar) => {
            const Icon = pillar.icon
            return (
              <section
                key={pillar.id}
                className="border border-[#262B35] bg-[#16191E] rounded p-6 sm:p-8 space-y-6"
              >
                <div className="flex items-start gap-4">
                  <div
                    className="p-2.5 rounded bg-[#0E1013] border border-[#262B35] shrink-0"
                    style={{ color: pillar.accent }}
                  >
                    <Icon size={20} />
                  </div>
                  <div>
                    <h2 className="text-base sm:text-lg font-semibold text-[#E1E4EA] font-sans">
                      {pillar.title}
                    </h2>
                    <p className="text-xs sm:text-sm text-[#828997] pt-0.5">
                      {pillar.tagline}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                  {pillar.items.map((item, idx) => (
                    <div
                      key={idx}
                      className="p-4 rounded bg-[#0E1013] border border-[#262B35] space-y-2 text-xs"
                    >
                      <h3 className="font-semibold text-[#E1E4EA] font-sans">
                        {item.name}
                      </h3>
                      <p className="text-[#828997] leading-relaxed text-[11px]">
                        {item.desc}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            )
          })}
        </div>

        {/* Bottom CTA */}
        <div className="border border-[#262B35] bg-[#16191E] rounded p-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold text-[#E1E4EA] font-sans">
              Ready to verify it on your computer?
            </h3>
            <p className="text-xs text-[#828997] pt-0.5">
              Launch the local agent client and connect to your private session.
            </p>
          </div>

          <Link
            to="/app/computer"
            className="px-5 py-2 rounded bg-[#D97736] hover:bg-[#D97736]/90 text-[#0E1013] font-medium text-xs flex items-center gap-2 transition-colors shrink-0"
          >
            <span>Launch Computer Control</span>
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  )
}
