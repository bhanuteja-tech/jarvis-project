import { useState, useEffect, useRef, useCallback } from 'react'
import { useStore } from '../store/useStore'
import { continuousVoiceController } from '../utils/ContinuousVoiceController'

export interface Message {
  id: string
  role: 'user' | 'jarvis' | 'status' | 'error'
  text: string
  timestamp: number
  attachments?: any[]
  resultSnapshot?: any
}

interface EventEnvelope {
  type: string
  data?: Record<string, any>
  run_id?: string
  seq: number
  ts?: string
}

const NODE_LABELS: Record<string, string> = {
  fetch_sources: 'Searching job sources',
  build_candidate_profile: 'Building candidate profile',
  deduplicate_jobs: 'Deduplicating results',
  rank_jobs: 'Ranking jobs',
  analyze_jd: 'Analyzing job descriptions',
  match_candidate_to_jobs: 'Matching your profile',
  tailor_resume: 'Tailoring resume',
  validate_resume: 'Validating resume',
}

let msgIdCounter = 0
function nextId(): string {
  return `msg-${++msgIdCounter}-${Date.now()}`
}

export function useWebSocket(wsPath?: string) {
  const [messages, setMessages] = useState<Message[]>([])
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const wsRef = useRef<WebSocket | null>(null)
  const sessionIdRef = useRef(crypto.randomUUID?.() || `session-${Date.now()}-${Math.random()}`)
  const streamingRef = useRef<string | null>(null)
  // Capture the wsPath in a ref so reconnects use the same endpoint.
  const wsPathRef = useRef(wsPath || '/ws/jarvis')



  const connect = useCallback(() => {
    const sessionId = sessionIdRef.current
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    // Use the domain-specific endpoint if provided; fall back to the legacy
    // shared endpoint.  The mode query param is included for the legacy path.
    const endpoint = wsPathRef.current
    const isLegacy = endpoint === '/ws/jarvis'
    const mode = useStore.getState().appMode
    const modeParam = isLegacy ? `&mode=${mode}` : ''
    const ws = new WebSocket(`${protocol}//${host}${endpoint}?session_id=${sessionId}${modeParam}`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionStatus('connected')
      useStore.getState().setAiCoreState('idle')
      useStore.getState().setAiCoreLabel('Online')
    }

    ws.onclose = () => {
      setConnectionStatus('disconnected')
      useStore.getState().setAiCoreState('idle')
      useStore.getState().setAiCoreLabel('Offline')
      setTimeout(connect, 3000)
    }

    ws.onerror = () => {
      setConnectionStatus('disconnected')
      useStore.getState().setAiCoreState('error')
      useStore.getState().setAiCoreLabel('Connection Error')
    }

    ws.onmessage = (event) => {
      try {
        const envelope: EventEnvelope = JSON.parse(event.data)
        handleEvent(envelope)
      } catch (error) {
        console.error('Error parsing WebSocket message:', error)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleEvent = useCallback((envelope: EventEnvelope) => {
    const { type, data = {} } = envelope
    const store = useStore.getState()

    switch (type) {
      case 'assistant_message': {
        const rawText = data.text || ''
        let displayText = rawText
        if (typeof rawText === 'string' && rawText.trim().startsWith('{') && rawText.trim().endsWith('}')) {
          try {
            const parsed = JSON.parse(rawText.trim())
            if (typeof parsed.text === 'string' && parsed.text.trim()) displayText = parsed.text
            else if (typeof parsed.answer === 'string') displayText = parsed.answer
            else if (typeof parsed.reply === 'string') displayText = parsed.reply
            else if (typeof parsed.message === 'string') displayText = parsed.message
          } catch { /* use original */ }
        }

        // Clear streaming ref — this is the authoritative message
        const streamId = streamingRef.current
        streamingRef.current = null

        // If we were streaming, replace the streaming message; otherwise deduplicate against last message
        setMessages(prev => {
          const filtered = streamId ? prev.filter(m => m.id !== streamId) : prev
          const lastMsg = filtered[filtered.length - 1]
          if (lastMsg && lastMsg.role === 'jarvis' && lastMsg.text === displayText) {
            return filtered
          }
          return [...filtered, {
            id: nextId(),
            role: 'jarvis' as const,
            text: displayText,
            timestamp: Date.now(),
            attachments: data.attachments?.filter((a: any) => a.kind !== 'llm_meta'),
            resultSnapshot: data.result_snapshot,
          }]
        })

        // Handle result snapshot
        if (data.result_snapshot) {
          const snapshot = data.result_snapshot
          if (snapshot.candidate_profile) {
            store.setCandidateProfile(snapshot.candidate_profile)
            store.setActiveWorkspace('resume')
          }
          if (snapshot.jobs?.length) {
            store.setJobs(snapshot.jobs)
            store.setActiveWorkspace('jobs')
          }
          if (snapshot.match_results?.length) store.setMatchResults(snapshot.match_results)
          if (snapshot.tailored_resume) {
            store.setTailoredResume(snapshot.tailored_resume)
            store.setActiveWorkspace('tailoring')
          }
          if (snapshot.validation_report) {
            store.setValidationReport(snapshot.validation_report)
          }
        }

        // Voice response handling
        const isVoice = !!data.is_voice || continuousVoiceController.getDebugData().isActive
        if (isVoice) {
          continuousVoiceController.handleAssistantResponse({
            text: displayText,
            generation: data.generation,
            isAcknowledgment: data.is_acknowledgment,
            isTermination: data.is_termination,
          })
        }

        if (!continuousVoiceController.getDebugData().isActive) {
          store.setAiCoreState('idle')
          store.setAiCoreLabel('Ready')
        }
        break
      }

      case 'token': {
        // Streaming token from LLM
        if (!streamingRef.current) {
          const id = nextId()
          streamingRef.current = id
          setMessages(prev => [...prev, {
            id,
            role: 'jarvis' as const,
            text: data.text || '',
            timestamp: Date.now(),
          }])
        } else {
          const streamId = streamingRef.current
          setMessages(prev => {
            return prev.map(m =>
              m.id === streamId
                ? { ...m, text: m.text + (data.text || '') }
                : m
            )
          })
        }
        store.setAiCoreState('thinking')
        store.setAiCoreLabel('Responding...')
        break
      }

      case 'domain_violation': {
        // The session's domain does not support this action.
        // Show a helpful redirect message rather than a generic error.
        const sessionDomain: string = data.session_domain || 'current'
        const otherDomain = sessionDomain === 'computer' ? 'career' : 'computer'
        const targetUrl = `/app/${otherDomain}`
        const domainLabel = otherDomain === 'career' ? 'Career Intelligence' : 'Computer Control'
        setMessages(prev => [...prev, {
          id: nextId(),
          role: 'error' as const,
          text: `That action belongs to ${domainLabel}. Navigate to ${targetUrl} to use it.`,
          timestamp: Date.now(),
        }])
        store.setIsProcessing(false)
        // Don't set AI Core to error — this is an informational boundary message.
        break
      }

      case 'error':
      case 'agent_error': {
        setMessages(prev => [...prev, {
          id: nextId(),
          role: 'error' as const,
          text: data.message || 'An error occurred',
          timestamp: Date.now(),
        }])
        store.setIsProcessing(false)
        store.setAiCoreState('error')
        store.setAiCoreLabel('Error')
        // Return to idle after 3s
        setTimeout(() => {
          store.setAiCoreState('idle')
          store.setAiCoreLabel('Ready')
        }, 3000)
        break
      }

      case 'agent_started': {
        store.setIsProcessing(true)
        store.setProcessingStage('started')
        store.clearActivities()
        streamingRef.current = null
        store.setAiCoreState('thinking')
        store.setAiCoreLabel('Processing')
        const action = data.action || 'processing'
        store.addActivity({
          id: `act-${envelope.seq}`,
          label: `Understanding request (${action})`,
          status: 'active',
          timestamp: Date.now(),
        })
        // Switch to activity workspace when a workflow starts
        if (action === 'run_discovery') {
          store.setActiveWorkspace('activity')
        }
        break
      }

      case 'agent_thinking': {
        store.setAiCoreState('thinking')
        store.setAiCoreLabel(data.detail || 'Thinking')
        break
      }

      case 'agent_speaking': {
        store.setAiCoreState('thinking')
        store.setAiCoreLabel('Generating response')
        break
      }

      case 'workflow_node_started': {
        const node = data.node || ''
        const label = data.label || NODE_LABELS[node] || node
        store.setProcessingStage(label)
        store.addActivity({
          id: `node-${node}-${envelope.seq}`,
          label,
          status: 'active',
          node,
          timestamp: Date.now(),
        })
        // Set appropriate AI core state based on node
        if (node === 'fetch_sources') {
          store.setAiCoreState('searching')
          store.setAiCoreLabel('Searching')
        } else if (node === 'analyze_jd' || node === 'match_candidate_to_jobs') {
          store.setAiCoreState('analyzing')
          store.setAiCoreLabel('Analyzing')
        } else {
          store.setAiCoreState('thinking')
          store.setAiCoreLabel(label)
        }
        break
      }

      case 'workflow_node_completed': {
        const node = data.node || ''
        const activities = useStore.getState().activities
        const activity = activities.find(a => a.node === node && a.status === 'active')
        if (activity) {
          const keys: string[] = data.keys || []
          let isSkipped = false
          let suffix = ''
          if (node === 'tailor_resume' && !keys.includes('tailored_resume')) {
            suffix = ' — Skipped (no target job selected)'
            isSkipped = true
          } else if (node === 'validate_resume' && !keys.includes('validation_report')) {
            suffix = ' — Skipped (no tailored resume)'
            isSkipped = true
          } else if (node === 'build_candidate_profile' && !keys.includes('candidate_profile')) {
            suffix = ' — Skipped (no resume uploaded)'
            isSkipped = true
          } else if (node === 'match_candidate_to_jobs' && !keys.includes('match_results')) {
            suffix = ' — Skipped (no candidate profile)'
            isSkipped = true
          }

          store.updateActivity(activity.id, {
            status: isSkipped ? 'skipped' : 'completed',
            label: suffix ? `${activity.label}${suffix}` : activity.label,
          })
        }
        break
      }

      case 'tool_started': {
        const tool = data.tool || ''
        const label = data.label || tool
        store.addActivity({
          id: `tool-${tool}-${envelope.seq}`,
          label,
          status: 'active',
          timestamp: Date.now(),
        })
        store.setAiCoreState('analyzing')
        store.setAiCoreLabel(label)
        break
      }

      case 'tool_completed': {
        const tool = data.tool || ''
        // Update tool activity
        const activities = useStore.getState().activities
        const activity = activities.find(a => a.id.startsWith(`tool-${tool}`) && a.status === 'active')
        if (activity) {
          store.updateActivity(activity.id, { status: 'completed' })
        }
        // If it's set_resume tool, store candidate profile info
        if (tool === 'set_resume') {
          if (data.candidate_profile) {
            store.setCandidateProfile(data.candidate_profile)
          }
          store.setActiveWorkspace('resume')
        }
        break
      }

      case 'completed':
      case 'agent_completed': {
        store.setIsProcessing(false)
        store.setProcessingStage('')
        if (!continuousVoiceController.getDebugData().isActive) {
          store.setAiCoreState('idle')
          store.setAiCoreLabel('Ready')
        }
        continuousVoiceController.handleAgentCompleted()
        // Mark any remaining active activities as completed
        const acts = useStore.getState().activities
        acts.forEach(a => {
          if (a.status === 'active') {
            store.updateActivity(a.id, { status: 'completed' })
          }
        })
        break
      }

      case 'cancelled':
      case 'run_cancelled': {
        store.setIsProcessing(false)
        store.setProcessingStage('')
        if (!continuousVoiceController.getDebugData().isActive) {
          store.setAiCoreState('idle')
          store.setAiCoreLabel('Ready')
        }
        continuousVoiceController.handleAgentCompleted()
        if (data.message) {
          setMessages(prev => [...prev, {
            id: nextId(),
            role: 'status' as const,
            text: data.message,
            timestamp: Date.now(),
          }])
        }
        break
      }

      case 'llm_provider_selected': {
        store.addActivity({
          id: `llm-select-${envelope.seq}`,
          label: `Using ${data.provider || 'LLM'}${data.model ? ` (${data.model})` : ''}`,
          status: 'completed',
          timestamp: Date.now(),
        })
        break
      }

      case 'llm_fallback': {
        store.addActivity({
          id: `llm-fallback-${envelope.seq}`,
          label: `Fallback: ${data.from} → ${data.to}`,
          status: 'completed',
          timestamp: Date.now(),
        })
        break
      }

      case 'desktop_action_result': {
        const emoji = data.success ? '✅' : '❌'
        const actionLabel = (data.action || 'desktop_action').replace(/_/g, ' ')
        store.addActivity({
          id: `desktop-${envelope.seq}`,
          label: `${emoji} Desktop: ${actionLabel}`,
          status: data.success ? 'completed' : 'skipped',
          timestamp: Date.now(),
        })
        const details = data.details || {}
        const compState = details.computer_state || {}
        continuousVoiceController.updateDiagnosticData({
          execution: `${data.action || 'action'}`,
          verification: details.verification || (data.success ? 'SUCCESS' : 'FAILED'),
          activeApplication: compState.active_application || details.application,
          currentDirectory: compState.current_directory || details.directory,
          taskId: data.task_id,
        })
        break
      }

      // -----------------------------------------------------------------------
      // Phase 8+ Computer Agent events
      // -----------------------------------------------------------------------

      case 'computer_plan_start': {
        store.resetComputerState()
        store.setComputerState({ isRunning: true })
        store.setAiCoreState('thinking')
        store.setAiCoreLabel('Planning task...')
        break
      }

      case 'computer_plan_ready': {
        store.setComputerState({
          planDescription: data.description || '',
          steps: data.steps || [],
          currentStepIdx: 0,
        })
        store.setAiCoreState('executing')
        store.setAiCoreLabel(`Executing ${data.step_count || 1} step plan`)
        store.addActivity({
          id: `plan-${envelope.seq}`,
          label: `📋 Plan: ${data.description || 'computer control'}`,
          status: 'active',
          timestamp: Date.now(),
        })
        break
      }

      case 'computer_step_start':
      case 'computer_step_started': {
        const stepIdx = data.step_idx ?? 0
        const totalSteps = data.total_steps ?? 1
        store.setComputerState({
          currentStepIdx: stepIdx,
          currentStepDescription: data.description || '',
        })
        store.setAiCoreLabel(`Step ${stepIdx + 1}/${totalSteps}: ${data.description || ''}`)
        store.addActivity({
          id: `step-${data.step_id || envelope.seq}`,
          label: `⚙️ ${data.description || data.tool || 'executing'}`,
          status: 'active',
          timestamp: Date.now(),
        })
        continuousVoiceController.updateDiagnosticData({
          currentStep: `Step ${stepIdx + 1}/${totalSteps}`,
          execution: `${data.tool || 'executing'}`,
          currentTask: `${data.description || data.tool || 'executing'}`,
          routerType: 'AUTONOMOUS_AGENT',
          intent: data.tool || 'computer_control',
        })
        break
      }

      case 'computer_step_done':
      case 'computer_step_verified': {
        const prevResults = useStore.getState().computerState.stepResults
        store.setComputerState({
          stepResults: [...prevResults, {
            step_id: data.step_id || '',
            description: data.description || '',
            verified: data.verified ?? true,
            reason: data.reason,
            confidence: data.confidence,
          }],
        })
        const activities = useStore.getState().activities
        const act = activities.find(a => a.id === `step-${data.step_id || ''}` && a.status === 'active')
        if (act) store.updateActivity(act.id, { status: 'completed', label: `✅ ${act.label.replace('⚙️ ', '')}` })
        continuousVoiceController.updateDiagnosticData({
          verification: (data.verified ?? true) ? 'SUCCESS' : 'FAILED',
          confidence: data.confidence,
        })
        break
      }

      case 'computer_step_failed': {
        const prevResults = useStore.getState().computerState.stepResults
        store.setComputerState({
          stepResults: [...prevResults, {
            step_id: data.step_id || '',
            description: data.description || '',
            verified: false,
            reason: data.reason,
          }],
        })
        const activities = useStore.getState().activities
        const act = activities.find(a => a.id === `step-${data.step_id || ''}` && a.status === 'active')
        if (act) store.updateActivity(act.id, { status: 'error', label: `❌ ${act.label.replace('⚙️ ', '')}` })
        continuousVoiceController.updateDiagnosticData({
          verification: 'FAILED',
          confidence: data.confidence || 0.0,
        })
        break
      }

      case 'computer_state_update': {
        const app = data.active_application || ''
        const isExplorer = app && (
          app.toLowerCase().includes('explorer') ||
          app.toLowerCase().includes('desktop')
        )
        store.setComputerState({
          activeApplication: data.active_application,
          currentDirectory: data.current_directory,
          activeWindow: data.active_window_title,
          currentUrl: data.current_url,
          isExplorerActive: isExplorer,
          intent: data.current_intent || data.last_intent || null,
          target: data.last_target || null,
          browser: isExplorer ? 'None' : (data.browser_name || data.browser || null),
          observation: data.last_observation || null,
          verification: data.last_verification || null,
          taskId: data.current_task_id || null,
        })
        continuousVoiceController.updateDiagnosticData({
          activeApplication: data.active_application,
          currentDirectory: data.current_directory,
        })
        store.setComputerContext({
          activeApp: data.active_application || null,
          activeWindow: data.active_window_title || null,
          activeBrowser: isExplorer ? 'None' : (data.browser_name || data.browser || null),
          currentUrl: isExplorer ? null : (data.active_page_url || data.current_url || null),
          currentDirectory: data.current_directory || null,
          ...(isExplorer ? {
            site: null,
            domain: null,
            page: null,
            channel: null,
            playlist: null,
            course: null,
            video: null,
            videoUrl: null,
            webSite: null,
            webChannel: null,
            webVideo: null,
          } : {})
        })
        break
      }

      case 'computer_context_update': {
        store.setComputerContext({
          site: data.site || null,
          domain: data.domain || null,
          page: data.page || null,
          channel: data.channel || null,
          playlist: data.playlist || null,
          course: data.course || null,
          video: data.video || null,
          videoUrl: data.video_url || null,
          webSite: data.site ? data.site.toUpperCase() : null,
          webChannel: data.channel || null,
          webVideo: data.video || null,
          currentList: data.current_list || [],
          ordinalBasis: data.ordinal_basis || null,
        })
        break
      }

      case 'latency_metrics': {
        store.setComputerState({
          latencyMetrics: data.metrics || data,
        })
        break
      }

      case 'action_request':
      case 'computer_needs_confirm':
      case 'confirmation_required': {
        const requiresConfirm = data.requires_confirmation ?? true
        store.setComputerState({
          needsConfirm: requiresConfirm,
          confirmationTimeoutSeconds: data.confirmation_timeout_seconds ?? (requiresConfirm ? 120 : null),
          timeoutSeconds: data.timeout_seconds ?? 30,
          target: data.target || data.tool || data.params?.path || data.params?.url,
          blastRadius: data.blast_radius || data.confirmation_prompt || data.description,
          dangerLevel: data.danger_level || (data.tool?.includes('delete') ? 'critical' : 'high'),
          taskId: data.action_id || data.task_id,
        })
        store.addActivity({
          id: `confirm-${envelope.seq}`,
          label: `⚠️ Needs confirmation: ${data.confirmation_prompt || data.description || data.tool || ''}`,
          status: 'active',
          timestamp: Date.now(),
        })
        break
      }

      case 'computer_response': {
        store.setComputerState({
          isRunning: false,
          lastVerified: data.verified ?? null,
          lastResponse: data.text || '',
          needsConfirm: data.needs_confirm ?? false,
          confirmationTimeoutSeconds: data.needs_confirm ? (data.confirmation_timeout_seconds ?? 120) : null,
        })
        if (!data.needs_confirm) {
          store.setAiCoreState('idle')
          store.setAiCoreLabel('Ready')
        }
        break
      }

      case 'computer_error': {
        store.setComputerState({ isRunning: false, lastVerified: false })
        store.setAiCoreState('error')
        store.setAiCoreLabel('Error')
        setTimeout(() => {
          store.setAiCoreState('idle')
          store.setAiCoreLabel('Ready')
        }, 3000)
        break
      }

      default:
        // Unknown event types are ignored per protocol
        break
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connect])

  const sendMessage = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setMessages(prev => [...prev, {
        id: nextId(),
        role: 'user' as const,
        text,
        timestamp: Date.now(),
      }])
      // Backend expects {type, text, mode} at the top level (not nested in data)
      const mode = useStore.getState().appMode
      wsRef.current.send(JSON.stringify({
        type: 'chat',
        text,
        mode,
      }))
    }
  }, [])

  const sendVoiceTurn = useCallback((text: string, generation: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setMessages(prev => [...prev, {
        id: nextId(),
        role: 'user' as const,
        text,
        timestamp: Date.now(),
      }])
      const mode = useStore.getState().appMode
      wsRef.current.send(JSON.stringify({
        type: 'voice_turn',
        text,
        generation,
        mode,
      }))
    }
  }, [])

  const sendVoiceBargeIn = useCallback((generation: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'voice_barge_in',
        generation,
      }))
    }
  }, [])

  useEffect(() => {
    continuousVoiceController.setSendFunctions(sendVoiceTurn, sendVoiceBargeIn)
  }, [sendVoiceTurn, sendVoiceBargeIn])

  const sendResumeFile = useCallback((file: File) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      alert('WebSocket connection is not active. Please wait or refresh.')
      return
    }

    const store = useStore.getState()
    store.setResumeFileName(file.name)

    const reader = new FileReader()
    reader.onerror = () => {
      console.error('Failed to read file:', reader.error)
      store.setAiCoreState('error')
      store.setAiCoreLabel('File Error')
      setMessages(prev => [...prev, {
        id: nextId(),
        role: 'error' as const,
        text: `Failed to read file: ${file.name}`,
        timestamp: Date.now(),
      }])
    }
    reader.onload = () => {
      try {
        const dataUrl = reader.result as string
        const base64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl

        wsRef.current?.send(JSON.stringify({
          type: 'resume_upload',
          name: file.name,
          data_base64: base64,
        }))

        setMessages(prev => [...prev, {
          id: nextId(),
          role: 'user' as const,
          text: `📄 Uploaded resume: ${file.name}`,
          timestamp: Date.now(),
        }])

        store.setAiCoreState('analyzing')
        store.setAiCoreLabel('Processing resume')
        store.setActiveWorkspace('resume')
      } catch (err) {
        console.error('Error preparing resume upload payload:', err)
        store.setAiCoreState('error')
        store.setAiCoreLabel('Upload Error')
      }
    }
    reader.readAsDataURL(file)
  }, [])

  const sendJobQuestion = useCallback((jobIndex: number, question: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'job_question',
        job_index: jobIndex,
        question,
      }))
      setMessages(prev => [...prev, {
        id: nextId(),
        role: 'user' as const,
        text: question,
        timestamp: Date.now(),
      }])
    }
  }, [])

  const sendTailorRequest = useCallback((jobIndex: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'chat',
        text: `tailor job ${jobIndex + 1}`,
      }))
      setMessages(prev => [...prev, {
        id: nextId(),
        role: 'user' as const,
        text: `Tailor resume for job #${jobIndex + 1}`,
        timestamp: Date.now(),
      }])
    }
  }, [])

  return {
    messages,
    sendMessage,
    sendVoiceTurn,
    sendVoiceBargeIn,
    sendResumeFile,
    sendJobQuestion,
    sendTailorRequest,
    connectionStatus,
    sessionId: sessionIdRef.current,
  }
}
