import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Activity, Settings, X, Cpu, Wifi, WifiOff, Monitor, Briefcase } from 'lucide-react'
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
    connected: { color: 'text-emerald-400', dot: 'bg-emerald-400', label: 'Online' },
    connecting: { color: 'text-amber-400', dot: 'bg-amber-400', label: 'Connecting' },
    disconnected: { color: 'text-red-400', dot: 'bg-red-400', label: 'Offline' },
  }

  const status = statusConfig[connectionStatus]

  // Fetch provider status when settings panel opens
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
      <div className="h-14 glass-strong border-b border-jarvis-border/30 flex items-center justify-between px-5 z-30 relative">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-3 group hover:opacity-90 transition-opacity" title="Back to JARVIS Public Website">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-500/20 group-hover:scale-105 transition-transform">
            <Activity className="text-white" size={16} />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-wide flex items-center gap-1.5">
              JARVIS
              <span className={`text-[9px] font-normal px-1.5 py-0.5 rounded border ${
                appMode === 'computer'
                  ? 'bg-violet-500/10 text-violet-400 border-violet-500/20'
                  : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
              }`}>
                {appMode === 'computer' ? 'COMPUTER' : 'CAREER'}
              </span>
            </h1>
            <p className={`text-[10px] tracking-wider uppercase font-medium ${
              appMode === 'computer' ? 'text-violet-400/90' : 'text-blue-400/90'
            }`}>
              {appMode === 'computer' ? 'Computer Control' : 'Career Intelligence'}
            </p>
          </div>
        </Link>

        {/* Center: mode switcher + status */}
        <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-4">
          {/* Mode Switcher */}
          <div className="flex items-center gap-1 bg-jarvis-surface/60 border border-jarvis-border/30 rounded-lg p-0.5">
            <button
              id="mode-computer"
              onClick={() => handleModeSwitch('computer')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200 ${
                appMode === 'computer'
                  ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30 shadow-sm'
                  : 'text-jarvis-muted hover:text-white'
              }`}
            >
              <Monitor size={12} />
              Computer Control
            </button>
            <button
              id="mode-career"
              onClick={() => handleModeSwitch('career')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-200 ${
                appMode === 'career'
                  ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30 shadow-sm'
                  : 'text-jarvis-muted hover:text-white'
              }`}
            >
              <Briefcase size={12} />
              Career Intelligence
            </button>
          </div>
          {/* Connection */}
          <div className="flex items-center gap-2">
            {connectionStatus === 'connected'
              ? <Wifi size={14} className={status.color} />
              : <WifiOff size={14} className={status.color} />
            }
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${status.dot} ${connectionStatus === 'connecting' ? 'animate-pulse' : ''}`} />
              <span className={`text-xs font-medium ${status.color}`}>{status.label}</span>
            </div>
          </div>

          {/* Active provider badge */}
          {llmEnabled && activeProvider && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-jarvis-surface/60 border border-jarvis-border/30">
              <Cpu size={12} className="text-jarvis-accent" />
              <span className="text-[11px] text-jarvis-muted">
                {activeProvider.name}{activeProvider.model ? ` · ${activeProvider.model}` : ''}
              </span>
            </div>
          )}
        </div>

        {/* Right controls */}
        <div className="flex items-center gap-2">
          <Link
            to="/"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium text-jarvis-muted hover:text-white bg-jarvis-surface/40 hover:bg-jarvis-surface/80 border border-jarvis-border/30 transition-all"
            title="Visit public product overview"
          >
            <span>Overview</span>
          </Link>
          <button
            onClick={() => setSettingsOpen(!settingsOpen)}
            className={`p-2 rounded-lg transition-all ${
              settingsOpen
                ? 'bg-jarvis-accent/20 text-jarvis-accent'
                : 'hover:bg-jarvis-surface/60 text-jarvis-muted hover:text-jarvis-accent'
            }`}
            title="Settings"
          >
            <Settings size={16} />
          </button>
        </div>
      </div>

      {/* Settings Panel */}
      <AnimatePresence>
        {settingsOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="absolute top-14 right-4 z-50 w-80 glass-strong rounded-xl shadow-2xl shadow-black/40 border border-jarvis-border/30 overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-jarvis-border/30">
              <h3 className="text-sm font-semibold text-jarvis-light">AI Engine Settings</h3>
              <button
                onClick={() => setSettingsOpen(false)}
                className="p-1 rounded-md hover:bg-jarvis-surface/60 text-jarvis-muted"
              >
                <X size={14} />
              </button>
            </div>

            <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto scrollbar-thin">
              {/* LLM Status */}
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${llmEnabled ? 'bg-emerald-400' : 'bg-jarvis-muted/50'}`} />
                <span className="text-xs text-jarvis-muted">
                  LLM {llmEnabled ? 'Enabled' : 'Disabled (deterministic mode)'}
                </span>
              </div>

              {/* Providers */}
              <div className="space-y-2">
                <p className="text-xs font-medium text-jarvis-accent uppercase tracking-wider">Providers</p>
                {providers.map(p => (
                  <div
                    key={p.name}
                    className={`p-3 rounded-lg border transition-all ${
                      p.configured
                        ? 'border-jarvis-border/40 bg-jarvis-surface/30'
                        : 'border-jarvis-border/20 bg-jarvis-darker/30 opacity-60'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${
                          p.reachable ? 'bg-emerald-400' : p.configured ? 'bg-amber-400' : 'bg-jarvis-muted/30'
                        }`} />
                        <span className="text-xs font-medium text-jarvis-light capitalize">{p.name}</span>
                      </div>
                      {p.configured && (
                        <span className="text-[10px] text-jarvis-muted">{p.model || 'default'}</span>
                      )}
                    </div>
                    {p.health_status && (
                      <p className="text-[10px] text-jarvis-muted mt-1 ml-4">
                        {p.health_status}
                      </p>
                    )}
                    {p.capabilities?.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5 ml-4">
                        {p.capabilities.map(c => (
                          <span key={c} className="px-1.5 py-0.5 text-[9px] rounded bg-jarvis-darker/50 text-jarvis-muted">
                            {c}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}

                {providers.length === 0 && (
                  <p className="text-xs text-jarvis-muted/50 text-center py-4">Loading providers...</p>
                )}
              </div>

              {/* Connection info */}
              <div className="pt-2 border-t border-jarvis-border/20">
                <p className="text-[10px] text-jarvis-muted/50">
                  Session: {sessionId.slice(0, 8)}… · Server-side routing
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
