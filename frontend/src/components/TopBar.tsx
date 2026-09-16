import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Activity, Settings, X, Cpu, Wifi, WifiOff } from 'lucide-react'
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
  const { settingsOpen, setSettingsOpen } = useStore()
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [llmEnabled, setLlmEnabled] = useState(false)

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
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Activity className="text-white" size={16} />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-wide">JARVIS</h1>
            <p className="text-[10px] text-jarvis-muted tracking-wider uppercase">Career Intelligence</p>
          </div>
        </div>

        {/* Center status */}
        <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-4">
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
