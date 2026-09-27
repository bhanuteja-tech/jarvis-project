import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Settings, X, Cpu, Wifi, WifiOff, Monitor, Briefcase } from 'lucide-react'
import { useStore } from '../store/useStore'

interface TopBarProps {
  connectionStatus: 'connecting' | 'connected' | 'disconnected'
  sessionId: string
}

interface ProviderInfo {
  name: string
  configured: boolean
  model: string
  reachable?: boolean
  model_available?: boolean
  health_status?: string
  capabilities: string[]
}

export function TopBar({ connectionStatus, sessionId }: TopBarProps) {
  const { settingsOpen, setSettingsOpen, appMode, setAppMode } = useStore()
  const navigate = useNavigate()
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [llmEnabled, setLlmEnabled] = useState(false)

  const handleModeSwitch = (mode: 'career' | 'computer') => {
    setAppMode(mode)
    if (mode === 'computer') navigate('/app/computer')
    else navigate('/app/career')
  }

  const statusConfig = {
    connected: { color: 'text-[#2EA069]', dot: 'bg-[#2EA069]', label: 'Online' },
    connecting: { color: 'text-[#D97736]', dot: 'bg-[#D97736]', label: 'Connecting' },
    disconnected: { color: 'text-[#E2604E]', dot: 'bg-[#E2604E]', label: 'Offline' },
  }

  const status = statusConfig[connectionStatus]

  useEffect(() => {
    if (settingsOpen) {
      fetch(`/api/llm/providers?session_id=${sessionId}`)
        .then(r => r.json())
        .then(data => {
          setProviders(data.providers || [])
        })
        .catch(() => {})

      fetch(`/api/llm/status?session_id=${sessionId}`)
        .then(r => r.json())
        .then(data => {
          setLlmEnabled(data.enabled || false)
        })
        .catch(() => {})
    }
  }, [settingsOpen, sessionId])

  const activeProvider = providers.find(p => p.reachable)

  return (
    <>
      <div className="h-14 bg-[#16191E] border-b border-[#262B35] flex items-center justify-between px-4 sm:px-6 z-30 relative select-none">
        {/* Brand / Logo */}
        <Link to="/" className="flex items-center gap-2.5 group hover:opacity-90 transition-opacity" title="Back to JARVIS Home">
          <div className="w-7 h-7 rounded bg-[#0E1013] border border-[#262B35] flex items-center justify-center">
            <span className="w-2 h-2 rounded-full bg-[#D97736]" />
          </div>
          <div>
            <h1 className="text-xs font-semibold text-[#E1E4EA] tracking-wide flex items-center gap-1.5 font-sans">
              JARVIS
              <span className="text-[10px] font-normal px-1 py-0.2 rounded bg-[#0E1013] text-[#828997] border border-[#262B35]">
                {appMode === 'computer' ? 'computer' : 'career'}
              </span>
            </h1>
          </div>
        </Link>

        {/* Center: Mode Switcher + Connection */}
        <div className="hidden sm:flex items-center gap-4">
          <div className="flex items-center gap-1 bg-[#0E1013] border border-[#262B35] rounded p-0.5">
            <button
              id="mode-computer"
              onClick={() => handleModeSwitch('computer')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-colors ${
                appMode === 'computer'
                  ? 'bg-[#16191E] text-[#E1E4EA] border border-[#262B35]'
                  : 'text-[#828997] hover:text-[#E1E4EA]'
              }`}
            >
              <Monitor size={13} />
              <span>Computer control</span>
            </button>
            <button
              id="mode-career"
              onClick={() => handleModeSwitch('career')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-colors ${
                appMode === 'career'
                  ? 'bg-[#16191E] text-[#E1E4EA] border border-[#262B35]'
                  : 'text-[#828997] hover:text-[#E1E4EA]'
              }`}
            >
              <Briefcase size={13} />
              <span>Career</span>
            </button>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs">
            {connectionStatus === 'connected' ? (
              <Wifi size={14} className={status.color} />
            ) : (
              <WifiOff size={14} className={status.color} />
            )}
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${status.dot} ${connectionStatus === 'connecting' ? 'animate-pulse' : ''}`} />
              <span className={status.color}>{status.label}</span>
            </div>
          </div>
        </div>

        {/* Right Controls */}
        <div className="flex items-center gap-2">
          {llmEnabled && activeProvider && (
            <div className="hidden md:flex items-center gap-1.5 px-2 py-1 rounded bg-[#0E1013] border border-[#262B35] text-[11px] font-mono text-[#828997]">
              <Cpu size={12} className="text-[#2EA069]" />
              <span>{activeProvider.name}</span>
            </div>
          )}

          <Link
            to="/"
            className="flex items-center gap-1 px-2.5 py-1 rounded text-xs text-[#828997] hover:text-[#E1E4EA] bg-[#0E1013] border border-[#262B35] transition-colors"
          >
            <span>Overview</span>
          </Link>

          <button
            onClick={() => setSettingsOpen(!settingsOpen)}
            className={`p-1.5 rounded transition-colors border border-[#262B35] ${
              settingsOpen
                ? 'bg-[#262B35] text-[#D97736]'
                : 'bg-[#0E1013] text-[#828997] hover:text-[#E1E4EA]'
            }`}
            title="Settings"
          >
            <Settings size={15} />
          </button>
        </div>
      </div>

      {/* Settings Flyout */}
      <AnimatePresence>
        {settingsOpen && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15 }}
            className="absolute top-14 right-4 z-50 w-80 bg-[#16191E] rounded border border-[#262B35] shadow-2xl overflow-hidden text-xs text-[#E1E4EA]"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#262B35]">
              <span className="font-semibold text-[#E1E4EA]">AI Engine Configuration</span>
              <button
                onClick={() => setSettingsOpen(false)}
                className="p-1 rounded hover:bg-[#0E1013] text-[#828997]"
              >
                <X size={14} />
              </button>
            </div>

            <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto scrollbar-thin">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${llmEnabled ? 'bg-[#2EA069]' : 'bg-[#828997]'}`} />
                <span className="text-[#828997]">
                  Model routing: {llmEnabled ? 'Active' : 'Deterministic grammar only'}
                </span>
              </div>

              <div className="space-y-2">
                <span className="text-[11px] font-mono text-[#828997] block">Model Providers</span>
                {providers.map(p => (
                  <div
                    key={p.name}
                    className="p-3 rounded bg-[#0E1013] border border-[#262B35] space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`w-1.5 h-1.5 rounded-full ${
                          p.reachable ? 'bg-[#2EA069]' : p.configured ? 'bg-[#D97736]' : 'bg-[#828997]'
                        }`} />
                        <span className="font-medium text-[#E1E4EA] capitalize">{p.name}</span>
                      </div>
                      {p.configured && (
                        <span className="text-[10px] font-mono text-[#828997]">{p.model || 'default'}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-2 border-t border-[#262B35] font-mono text-[11px] text-[#828997]">
                Session: {sessionId.slice(0, 8)}…
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
