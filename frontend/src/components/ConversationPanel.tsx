import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Mic, MicOff, Paperclip, Volume2, VolumeX } from 'lucide-react'
import { useStore } from '../store/useStore'
import type { Message } from '../hooks/useWebSocket'
import { speakText, stopSpeaking } from '../utils/speech'

interface ConversationPanelProps {
  messages: Message[]
  onSendMessage: (text: string) => void
  onResumeUpload: (file: File) => void
}

const QUICK_ACTIONS = [
  'Apply for ML Engineer Intern',
  'Find ML jobs in Bangalore',
  'Analyze my resume',
  'Career advice',
]

const ACCEPTED_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
]
const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md']

export function ConversationPanel({ messages, onSendMessage, onResumeUpload }: ConversationPanelProps) {
  const [inputText, setInputText] = useState('')
  const [isListening, setIsListening] = useState(false)
  const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const recognitionRef = useRef<any>(null)
  const { isProcessing, resumeFileName } = useStore()

  const handleSpeak = (msgId: string, text: string) => {
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
  }

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

  // Voice input via SpeechRecognition API
  const toggleListening = useCallback(() => {
    const SpeechRecognition = typeof window !== 'undefined' && ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)

    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser environment. Please use Chrome, Edge, or an HTTPS connection.')
      return
    }

    if (isListening) {
      recognitionRef.current?.stop()
      setIsListening(false)
      useStore.getState().setAiCoreState('idle')
      useStore.getState().setAiCoreLabel('Ready')
      return
    }

    try {
      const recognition = new SpeechRecognition()
      recognition.continuous = false
      recognition.interimResults = true
      recognition.lang = 'en-US'

      recognition.onstart = () => {
        setIsListening(true)
        useStore.getState().setAiCoreState('listening')
        useStore.getState().setAiCoreLabel('Listening...')
      }

      recognition.onresult = (event: any) => {
        let finalTranscript = ''
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalTranscript += event.results[i][0].transcript
          } else {
            setInputText(event.results[i][0].transcript)
          }
        }
        if (finalTranscript.trim()) {
          setInputText(finalTranscript.trim())
          onSendMessage(finalTranscript.trim())
          setInputText('')
        }
      }

      recognition.onerror = (event: any) => {
        console.warn('Speech recognition error:', event.error)
        setIsListening(false)
        useStore.getState().setAiCoreState('idle')
        useStore.getState().setAiCoreLabel('Ready')
      }

      recognition.onend = () => {
        setIsListening(false)
        useStore.getState().setAiCoreState('idle')
        useStore.getState().setAiCoreLabel('Ready')
      }

      recognitionRef.current = recognition
      recognition.start()
    } catch (err) {
      console.error('Speech recognition failed to start:', err)
      setIsListening(false)
      useStore.getState().setAiCoreState('idle')
    }
  }, [isListening, onSendMessage])

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
                <div key={i} className="mt-3 p-3 rounded-xl bg-gradient-to-r from-cyan-950/60 to-indigo-950/60 border border-cyan-500/40 space-y-2">
                  <div className="flex items-center gap-1.5 text-cyan-300 text-xs font-semibold">
                    <span>✨</span>
                    <span>Ready to Customize for {att.target_role || 'Target Role'}</span>
                  </div>
                  <p className="text-[11px] text-jarvis-light/80 leading-relaxed">
                    Open PDF Studio to polish sections with AI Copilot, enhance ATS keyword density, and inspect your real-time score.
                  </p>
                  <button
                    onClick={() => {
                      useStore.getState().setActiveWorkspace('doc-studio')
                    }}
                    className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white text-xs font-bold shadow-md shadow-cyan-500/20 transition-all cursor-pointer"
                  >
                    <span>🚀</span>
                    <span>{att.label || 'Open in PDF Studio'}</span>
                  </button>
                </div>
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

          {/* Voice */}
          <button
            type="button"
            onClick={toggleListening}
            className={`p-2 rounded-lg transition-all ${
              isListening
                ? 'bg-red-500/20 text-red-400 animate-pulse'
                : 'bg-jarvis-surface/50 text-jarvis-muted hover:text-jarvis-accent hover:bg-jarvis-surface'
            }`}
            title={isListening ? 'Stop listening' : 'Voice input'}
          >
            {isListening ? <MicOff size={18} /> : <Mic size={18} />}
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
            className="p-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-violet-600 text-white hover:from-blue-500 hover:to-violet-500 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-lg shadow-blue-500/20"
            title="Send message"
          >
            <Send size={16} />
          </button>
        </div>

        {/* Quick Actions */}
        <div className="mt-2.5 flex gap-1.5 overflow-x-auto scrollbar-hide pb-0.5">
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action}
              onClick={() => {
                setInputText(action)
                inputRef.current?.focus()
              }}
              className="px-3 py-1.5 text-[11px] bg-jarvis-surface/40 border border-jarvis-border/30 rounded-full text-jarvis-muted hover:text-jarvis-accent hover:border-jarvis-accent/30 transition-all whitespace-nowrap"
            >
              {action}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
