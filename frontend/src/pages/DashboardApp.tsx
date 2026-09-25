import { useCallback, useEffect } from 'react'
import { AICore } from '../components/AICore'
import { ConversationPanel } from '../components/ConversationPanel'
import { WorkspacePanel } from '../components/WorkspacePanel'
import { TopBar } from '../components/TopBar'
import { useWebSocket } from '../hooks/useWebSocket'
import { useStore } from '../store/useStore'
import { DocumentStudioWorkspace } from '../components/workspaces/DocumentStudioWorkspace'
import { VoiceDebugPanel } from '../components/VoiceDebugPanel'

export function DashboardApp() {
  const {
    messages,
    sendMessage,
    sendResumeFile,
    sendJobQuestion,
    sendTailorRequest,
    connectionStatus,
    sessionId,
  } = useWebSocket('/ws/career')

  const { activeWorkspace, setActiveWorkspace, setAppMode } = useStore()

  useEffect(() => {
    setAppMode('career')
  }, [setAppMode])

  const handleSendMessage = useCallback((text: string) => {
    sendMessage(text)
  }, [sendMessage])

  return (
    <div className="h-screen w-screen jarvis-bg text-jarvis-light overflow-hidden flex flex-col relative">
      {/* Top Bar */}
      <TopBar connectionStatus={connectionStatus} sessionId={sessionId} />

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left: Conversation Panel */}
        <ConversationPanel
          messages={messages}
          onSendMessage={handleSendMessage}
          onResumeUpload={sendResumeFile}
        />

        {/* Center: AI Core Visual */}
        <div className="flex-1 flex items-center justify-center jarvis-core-bg relative min-w-0">
          <AICore />
        </div>

        {/* Right: Workspace Panel */}
        <WorkspacePanel
          activeWorkspace={activeWorkspace}
          onWorkspaceChange={setActiveWorkspace}
          onTailorRequest={sendTailorRequest}
          onJobQuestion={sendJobQuestion}
          onResumeUpload={sendResumeFile}
        />

        {/* Full-Screen PDF Document Studio */}
        {activeWorkspace === 'doc-studio' && (
          <DocumentStudioWorkspace />
        )}
      </div>

      {/* Voice Debug Panel (Development / Diagnostics) */}
      <VoiceDebugPanel />
    </div>
  )
}
