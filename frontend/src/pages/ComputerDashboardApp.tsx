/**
 * ComputerDashboardApp — dashboard layout for Computer Control mode.
 *
 * Connects to /ws/computer — a domain-exclusive WebSocket endpoint whose
 * sessions are permanently locked to domain="computer".  Career pipeline
 * tools (run_discovery, resume analysis, etc.) are rejected at the
 * orchestrator layer with a DomainViolation error.  No career events are
 * ever emitted on this channel.
 */
import { useCallback, useEffect } from 'react'
import { TopBar } from '../components/TopBar'
import { ConversationPanel } from '../components/ConversationPanel'
import { AICore } from '../components/AICore'
import { VoiceDebugPanel } from '../components/VoiceDebugPanel'
import { ComputerControlPage } from './ComputerControlPage'
import { useWebSocket } from '../hooks/useWebSocket'
import { useStore } from '../store/useStore'

export function ComputerDashboardApp() {
  const {
    messages,
    sendMessage,
    sendResumeFile,
    connectionStatus,
    sessionId,
  } = useWebSocket('/ws/computer')

  const { setAppMode } = useStore()

  useEffect(() => {
    setAppMode('computer')
  }, [setAppMode])

  const handleSendMessage = useCallback((text: string) => {
    sendMessage(text)
  }, [sendMessage])

  return (
    <div className="h-screen w-screen jarvis-bg text-jarvis-light overflow-hidden flex flex-col relative">
      {/* Top Bar with mode switcher */}
      <TopBar connectionStatus={connectionStatus} sessionId={sessionId} />

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left: Conversation Panel (shared across modes) */}
        <ConversationPanel
          messages={messages}
          onSendMessage={handleSendMessage}
          onResumeUpload={sendResumeFile}
        />

        {/* Center: AI Core Visual */}
        <div className="flex-shrink-0 flex items-center justify-center jarvis-core-bg relative"
          style={{ width: '280px' }}
        >
          <AICore />
        </div>

        {/* Right: Computer Control Page */}
        <div className="flex-1 min-w-0 overflow-hidden border-l border-jarvis-border/20">
          <ComputerControlPage sendMessage={handleSendMessage} />
        </div>
      </div>

      {/* Voice Debug Panel */}
      <VoiceDebugPanel />
    </div>
  )
}
