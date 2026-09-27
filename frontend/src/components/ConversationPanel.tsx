import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Mic, MicOff, Paperclip, Volume2, VolumeX, Square } from 'lucide-react'
import { useStore } from '../store/useStore'
import type { Message } from '../hooks/useWebSocket'
import { speakText, stopSpeaking } from '../utils/speech'
import { continuousVoiceController, VoiceSessionState } from '../utils/ContinuousVoiceController'

interface ConversationPanelProps {
  messages: Message[]
  onSendMessage: (text: string) => void
  onResumeUpload: (file: File) => void
}

const QUICK_ACTIONS = [
  'Open GitHub',
  'Open YouTube',
  'Open Browser',
  'Find ML jobs in Bangalore',
  'Apply for ML Engineer Intern',
  'Analyze my resume',
  'Career advice',
  'Screenshot',
  'System info',
]

const ACCEPTED_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
]
const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md']

function CredentialCard({
  service,
  field,
  onSubmit,
  onCancel,
}: {
  service: string
  field: string
  onSubmit: (val: string) => void
  onCancel: () => void
}) {
  const [val, setVal] = useState('')
  const serviceTitle = service ? service.charAt(0).toUpperCase() + service.slice(1) : 'Service'

  return (
    <div className="mt-3 p-3.5 rounded bg-[#16191E] border border-[#262B35] space-y-2.5">
      <div className="flex items-center justify-between text-xs font-semibold text-[#D97736]">
        <div className="flex items-center gap-1.5">
          <span>🔐</span>
          <span>{serviceTitle} Credential Required</span>
        </div>
        <span className="text-[10px] text-[#828997] font-mono">{field}</span>
      </div>
      <p className="text-[11px] text-[#828997] leading-relaxed">
        Enter your {serviceTitle} {field} to save it in your local Credential Vault and open your account.
      </p>
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && val.trim()) {
              e.preventDefault()
              onSubmit(val.trim())
            }
          }}
          placeholder={`e.g. ${service === 'github' ? 'bhanuteja-tech' : 'your-handle'}`}
          className="flex-1 bg-[#0E1013] border border-[#262B35] rounded px-3 py-1.5 text-xs text-[#E1E4EA] placeholder:text-[#828997]/50 focus-visible:ring-2 focus-visible:ring-[#D97736] focus-visible:outline-none"
          autoFocus
        />
        <button
          type="button"
          onClick={() => {
            if (val.trim()) onSubmit(val.trim())
          }}
          disabled={!val.trim()}
          className="px-3 py-1.5 rounded bg-[#D97736] hover:bg-[#D97736]/90 text-[#0E1013] text-xs font-semibold disabled:opacity-40 transition-colors cursor-pointer"
        >
          Save & Open
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-2.5 py-1.5 rounded bg-[#0E1013] hover:bg-[#262B35] text-[#828997] hover:text-[#E1E4EA] border border-[#262B35] text-xs transition-colors cursor-pointer"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

export function ConversationPanel({ messages, onSendMessage, onResumeUpload }: ConversationPanelProps) {
  const [inputText, setInputText] = useState('')
  const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [voiceState, setVoiceState] = useState<VoiceSessionState>('IDLE')
  const [isVoiceActive, setIsVoiceActive] = useState<boolean>(false)
  const [currentVoiceTranscript, setCurrentVoiceTranscript] = useState<string>('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { isProcessing, resumeFileName } = useStore()

  useEffect(() => {
    const unsub = continuousVoiceController.subscribe((st) => {
      setVoiceState(st)
      const dbg = continuousVoiceController.getDebugData()
      setIsVoiceActive(dbg.isActive)
      setCurrentVoiceTranscript(dbg.currentTranscript || dbg.interimTranscript)
    })
    return unsub
  }, [])

  const handleSpeak = useCallback((msgId: string, text: string) => {
    if (speakingMsgId === msgId) {
      stopSpeaking()
      setSpeakingMsgId(null)
      useStore.getState().setAiCoreState('idle')
      useStore.getState().setAiCoreLabel('Ready')
      return
    }

    const started = speakText(
      text,
      () => {
        setSpeakingMsgId(msgId)
        useStore.getState().setAiCoreState('speaking')
        useStore.getState().setAiCoreLabel('Speaking...')
      },
      () => {
        setSpeakingMsgId(null)
        useStore.getState().setAiCoreState('idle')
        useStore.getState().setAiCoreLabel('Ready')
      }
    )

    if (!started) {
      alert('Text-to-speech is not supported or failed in this browser.')
    }
  }, [speakingMsgId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(() => {
    const text = inputText.trim()
    if (text) {
      onSendMessage(text)
      setInputText('')
      inputRef.current?.focus()
    }
  }, [inputText, onSendMessage])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend])

  // File upload handling
  const handleFileSelect = useCallback((file: File) => {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!ACCEPTED_EXTENSIONS.includes(ext) && !ACCEPTED_TYPES.includes(file.type)) {
      return // silently reject unsupported files
    }
    if (file.size > 10 * 1024 * 1024) {
      return // 10MB limit
    }
    onResumeUpload(file)
  }, [onResumeUpload])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFileSelect(file)
  }, [handleFileSelect])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }, [])

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false)
  }, [])

  // Authoritative Voice Session Control via ContinuousVoiceController
  const toggleVoiceSession = useCallback(async () => {
    if (isVoiceActive) {
      continuousVoiceController.stopSession()
    } else {
      const ok = await continuousVoiceController.startSession()
      if (!ok) {
        const err = continuousVoiceController.getDebugData().errorMessage
        alert(err || 'Failed to start continuous voice session.')
      }
    }
  }, [isVoiceActive])

  const renderMessage = (message: Message) => {
    if (message.role === 'status') {
      return (
        <div className="flex justify-center">
          <div className="msg-status px-4 py-2 max-w-[90%]">
            <p className="text-xs text-jarvis-muted text-center">{message.text}</p>
          </div>
        </div>
      )
    }

    if (message.role === 'error') {
      return (
        <div className="flex justify-start">
          <div className="msg-error px-4 py-3 max-w-[85%]">
            <p className="text-sm text-red-200 leading-relaxed whitespace-pre-wrap">{message.text}</p>
          </div>
        </div>
      )
    }

    if (message.role === 'user') {
      return (
        <div className="flex justify-end">
          <div className="msg-user px-4 py-3 max-w-[85%]">
            <p className="text-sm text-white leading-relaxed whitespace-pre-wrap">{message.text}</p>
          </div>
        </div>
      )
    }

    // jarvis role
    const isSpeakingThis = speakingMsgId === message.id
    return (
      <div className="flex justify-start">
        <div className="msg-jarvis px-4 py-3 max-w-[85%] relative group">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm text-jarvis-light leading-relaxed whitespace-pre-wrap flex-1">{message.text}</p>
            <button
              type="button"
              onClick={() => handleSpeak(message.id, message.text)}
              className={`p-1.5 rounded-md transition-all flex-shrink-0 ${
                isSpeakingThis
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-jarvis-muted/40 hover:text-jarvis-accent hover:bg-jarvis-surface/60'
              }`}
              title={isSpeakingThis ? 'Stop speaking' : 'Read aloud'}
            >
              {isSpeakingThis ? <VolumeX size={14} className="animate-pulse" /> : <Volume2 size={14} />}
            </button>
          </div>
          {/* Cover letter & Studio attachments */}
          {message.attachments?.map((att, i) => {
            if (att.kind === 'cover_letter' && att.text) {
              return (
                <div key={i} className="mt-3 p-3 rounded-lg bg-jarvis-darker/50 border border-jarvis-border">
                  <p className="text-xs font-medium text-jarvis-accent mb-2">📝 Cover Letter</p>
                  <p className="text-xs text-jarvis-light/80 whitespace-pre-wrap leading-relaxed">{att.text}</p>
                </div>
              )
            }
            if (att.kind === 'open_pdf_studio') {
              return (
                <div key={i} className="mt-3 p-3 rounded bg-[#16191E] border border-[#262B35] space-y-2">
                  <div className="flex items-center gap-1.5 text-[#E1E4EA] text-xs font-semibold">
                    <span>📄</span>
                    <span>Ready to Customize for {att.target_role || 'Target Role'}</span>
                  </div>
                  <p className="text-[11px] text-[#828997] leading-relaxed">
                    Open Document Studio to inspect sections, verify evidence containment, and view ATS coverage reports.
                  </p>
                  <button
                    onClick={() => {
                      useStore.getState().setActiveWorkspace('doc-studio')
                    }}
                    className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded bg-[#D97736] hover:bg-[#D97736]/90 text-[#0E1013] text-xs font-semibold transition-colors cursor-pointer"
                  >
                    <span>{att.label || 'Open in Document Studio'}</span>
                  </button>
                </div>
              )
            }
            if (att.kind === 'credential_prompt') {
              return (
                <CredentialCard
                  key={i}
                  service={att.service || 'service'}
                  field={att.field || 'username'}
                  onSubmit={(val) => onSendMessage(val)}
                  onCancel={() => onSendMessage('cancel')}
                />
              )
            }
            return null
          })}
        </div>
      </div>
    )
  }

  return (
    <div
      className="w-[380px] min-w-[320px] glass-strong flex flex-col border-r border-jarvis-border/30"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
      {/* Drag overlay */}
      <AnimatePresence>
        {isDragOver && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-50 flex items-center justify-center drop-zone-active bg-jarvis-darker/80 backdrop-blur-sm"
          >
            <div className="text-center">
              <Paperclip className="mx-auto mb-2 text-jarvis-accent" size={32} />
              <p className="text-sm text-jarvis-accent font-medium">Drop resume here</p>
              <p className="text-xs text-jarvis-muted mt-1">PDF, DOCX, TXT, or MD</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <div className="px-4 py-3 border-b border-jarvis-border/30">
        <h2 className="text-sm font-semibold text-jarvis-light">Conversation</h2>
        {resumeFileName && (
          <p className="text-xs text-jarvis-accent mt-0.5 truncate">📄 {resumeFileName}</p>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center border border-jarvis-border/30">
              <span className="text-2xl">🤖</span>
            </div>
            <p className="text-sm text-jarvis-light font-medium">Hello! I'm JARVIS</p>
            <p className="text-xs text-jarvis-muted mt-1 max-w-[260px] mx-auto leading-relaxed">
              Your career intelligence assistant. Search jobs, analyze resumes, get matched, and tailor applications.
            </p>
          </div>
        )}

        <AnimatePresence mode="popLayout">
          {messages.map((message) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2 }}
            >
              {renderMessage(message)}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Typing indicator */}
        {isProcessing && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex justify-start"
          >
            <div className="msg-jarvis px-4 py-3 flex items-center gap-1.5">
              {[0, 1, 2].map(i => (
                <motion.div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-jarvis-accent"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }}
                />
              ))}
            </div>
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Active Voice Session Status Bar */}
      {isVoiceActive && (
        <div className="mx-3 mb-2 p-2.5 rounded-xl bg-gradient-to-r from-cyan-950/80 to-blue-950/80 border border-cyan-500/40 flex items-center justify-between shadow-lg shadow-cyan-950/30">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-500" />
            </span>
            <div className="overflow-hidden">
              <div className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                <span>● {voiceState}</span>
                <span className="text-[10px] font-normal text-cyan-400/70">Continuous Voice Loop</span>
              </div>
              {currentVoiceTranscript && (
                <div className="text-[11px] text-emerald-300 font-mono italic truncate max-w-xs">
                  "{currentVoiceTranscript}"
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {voiceState === 'SPEAKING' && (
              <button
                type="button"
                onClick={() => continuousVoiceController.bargeIn()}
                className="px-2 py-1 rounded bg-amber-600/80 hover:bg-amber-500 text-white text-[10px] font-semibold transition-all cursor-pointer shadow"
              >
                Interrupt
              </button>
            )}
            <button
              type="button"
              onClick={() => continuousVoiceController.stopSession()}
              className="px-2 py-1 rounded bg-red-600/80 hover:bg-red-500 text-white text-[10px] font-semibold transition-all cursor-pointer"
            >
              End Voice
            </button>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="p-3 border-t border-jarvis-border/30">
        <div className="flex items-center gap-2">
          {/* File Upload */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="p-2 rounded-lg transition-all bg-jarvis-surface/50 text-jarvis-muted hover:text-jarvis-accent hover:bg-jarvis-surface"
            title="Attach resume (PDF, DOCX, TXT, MD)"
          >
            <Paperclip size={18} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleFileSelect(file)
              e.target.value = '' // reset to allow re-uploading same file
            }}
          />

          {/* Continuous Voice Session Toggle */}
          <button
            type="button"
            onClick={toggleVoiceSession}
            className={`p-2 rounded-lg transition-all cursor-pointer ${
              isVoiceActive
                ? 'bg-red-500/20 text-red-400 border border-red-500/40 animate-pulse'
                : 'bg-jarvis-surface/50 text-jarvis-muted hover:text-cyan-400 hover:bg-jarvis-surface'
            }`}
            title={isVoiceActive ? 'Stop Continuous Voice Session' : 'Start Continuous Voice Session'}
          >
            {isVoiceActive ? <MicOff size={18} /> : <Mic size={18} />}
          </button>

          {/* Text Input */}
          <input
            ref={inputRef}
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask JARVIS anything..."
            className="flex-1 bg-jarvis-surface/60 border border-jarvis-border/40 rounded-xl px-4 py-2.5 text-sm text-jarvis-light placeholder:text-jarvis-muted/50 focus:outline-none focus:border-jarvis-accent/50 focus:ring-1 focus:ring-jarvis-accent/30 transition-all"
          />

          {/* Send */}
          <button
            onClick={handleSend}
            disabled={!inputText.trim()}
            className="p-2.5 rounded bg-[#D97736] hover:bg-[#D97736]/90 text-[#0E1013] font-medium disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-[#D97736]"
            title="Send message"
          >
            <Send size={16} />
          </button>
        </div>

        {/* Quick Actions */}
        <div className="mt-2.5 flex gap-1.5 overflow-x-auto scrollbar-hide pb-0.5">
          {/* Quick Voice Session Action Button */}
          <button
            type="button"
            onClick={toggleVoiceSession}
            className={`px-3 py-1.5 text-[11px] font-medium rounded border transition-colors whitespace-nowrap cursor-pointer flex items-center gap-1.5 ${
              isVoiceActive
                ? 'bg-[#E2604E]/15 text-[#E2604E] border-[#E2604E]/40 hover:bg-[#E2604E]/25'
                : 'bg-[#16191E] text-[#D97736] border-[#262B35] hover:bg-[#262B35]'
            }`}
          >
            {isVoiceActive ? (
              <>
                <Square size={12} className="text-[#E2604E]" />
                <span>Stop voice</span>
              </>
            ) : (
              <>
                <Mic size={12} className="text-[#D97736]" />
                <span>Start voice</span>
              </>
            )}
          </button>

          {QUICK_ACTIONS.map((action) => (
            <button
              key={action}
              onClick={() => {
                onSendMessage(action)
              }}
              className="px-3 py-1.5 text-[11px] bg-jarvis-surface/40 border border-jarvis-border/30 rounded-full text-jarvis-muted hover:text-jarvis-accent hover:border-jarvis-accent/30 transition-all whitespace-nowrap cursor-pointer"
            >
              {action}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
