import { create } from 'zustand'

export type AiCoreState =
  | 'idle'
  | 'listening'
  | 'transcribing'
  | 'routing'
  | 'executing'
  | 'observing'
  | 'thinking'
  | 'searching'
  | 'analyzing'
  | 'speaking'
  | 'interrupted'
  | 'ending'
  | 'ended'
  | 'error'

export interface ActivityItem {
  id: string
  label: string
  status: 'pending' | 'active' | 'completed' | 'skipped' | 'error'
  node?: string
  timestamp: number
}

export interface JobItem {
  __index: number
  job_key: string
  title: string
  company: string
  location: string
  employment_type: string
  job_url: string
  description?: string
  salary?: any
}

export interface MatchResult {
  job_index: number
  job_key?: string
  score: number
  tier: string
  breakdown?: Record<string, any>
  matched_skills?: string[]
  missing_requirements?: string[]
  reasons?: string[]
}

export interface CandidateProfile {
  status: string
  raw_text?: string
  profile?: {
    identity?: { full_name?: string }
    skills?: { items: Array<{ name: string; category?: string }> }
    experience?: { items: Array<any>; total_years?: number }
    education?: { items: Array<any> }
    certifications?: { items: Array<any> }
    projects?: { items: Array<any> }
    preferences?: any
    contact?: { name?: string; emails?: string[]; phones?: string[]; links?: string[] }
  }
  identity?: { full_name?: string }
  skills?: { items: Array<{ name: string; category?: string }> }
  experience?: { items: Array<any>; total_years?: number }
  education?: { items: Array<any> }
  certifications?: { items: Array<any> }
  projects?: { items: Array<any> }
  preferences?: any
  contact?: { name?: string; emails?: string[]; phones?: string[]; links?: string[] }
}

export interface SavedJob {
  job_key: string
  title: string
  company: string
  location: string
  status: string
  saved_at: number
  score?: number
  tier?: string
}

export type AppMode = 'career' | 'computer'

export interface ComputerStateInfo {
  isRunning: boolean
  planDescription: string
  steps: string[]
  currentStepIdx: number
  currentStepDescription: string
  lastVerified: boolean | null
  lastResponse: string
  needsConfirm: boolean
  stepResults: Array<{
    step_id: string
    description: string
    verified: boolean | null
    reason?: string
    confidence?: number
    tool?: string
  }>
  // Advanced debug telemetry
  intent?: string | null
  entities?: any | null
  target?: string | null
  browser?: string | null
  observation?: string | null
  verification?: any | null
  taskId?: string | null
  generation?: number
  activeApplication?: string | null
  currentDirectory?: string | null
  activeWindow?: string | null
  currentUrl?: string | null
  isExplorerActive?: boolean
}

export interface ComputerContextInfo {
  site: string | null
  domain: string | null
  page: string | null
  channel: string | null
  playlist: string | null
  course: string | null
  video: string | null
  videoUrl: string | null
  activeBrowser: string | null
  activeApp: string | null
  activeWindow: string | null
  currentUrl: string | null
  windowTitle: string | null
  webSite: string | null
  webChannel: string | null
  webVideo: string | null
  currentList: Array<{ ordinal?: number; type?: string; title?: string; name?: string; url?: string }>
  ordinalBasis: string | null
  currentDirectory: string | null
}

interface JarvisState {
  // Workspace
  activeWorkspace: string
  setActiveWorkspace: (workspace: string) => void

  // AI Core
  aiCoreState: AiCoreState
  setAiCoreState: (state: AiCoreState) => void
  aiCoreLabel: string
  setAiCoreLabel: (label: string) => void

  // Activities
  activities: ActivityItem[]
  addActivity: (activity: ActivityItem) => void
  updateActivity: (id: string, updates: Partial<ActivityItem>) => void
  clearActivities: () => void

  // Candidate
  candidateProfile: CandidateProfile | null
  setCandidateProfile: (profile: CandidateProfile | null) => void
  resumeFileName: string
  setResumeFileName: (name: string) => void

  // Jobs
  jobs: JobItem[]
  setJobs: (jobs: JobItem[]) => void

  // Matching
  matchResults: MatchResult[]
  setMatchResults: (results: MatchResult[]) => void

  // Tailoring
  tailoredResume: any
  setTailoredResume: (resume: any) => void

  // Validation
  validationReport: any
  setValidationReport: (report: any) => void

  // Processing
  isProcessing: boolean
  setIsProcessing: (processing: boolean) => void
  processingStage: string
  setProcessingStage: (stage: string) => void

  // Saved jobs
  savedJobs: SavedJob[]
  setSavedJobs: (jobs: SavedJob[]) => void

  // Selected job for detail view
  selectedJobIndex: number | null
  setSelectedJobIndex: (index: number | null) => void

  // Custom JD draft for tailoring/editor
  customJdDraft: { title: string; company: string; jd_text: string } | null
  setCustomJdDraft: (draft: { title: string; company: string; jd_text: string } | null) => void

  // Settings panel
  settingsOpen: boolean
  setSettingsOpen: (open: boolean) => void

  // Session
  sessionId: string
  setSessionId: (id: string) => void

  // Voice Session
  voiceSessionActive: boolean
  setVoiceSessionActive: (active: boolean) => void

  // App Mode (career vs computer control)
  appMode: AppMode
  setAppMode: (mode: AppMode) => void

  // Computer Agent state
  computerState: ComputerStateInfo
  setComputerState: (state: Partial<ComputerStateInfo>) => void
  resetComputerState: () => void

  // Computer context
  computerContext: ComputerContextInfo
  setComputerContext: (ctx: Partial<ComputerContextInfo>) => void
}

export const useStore = create<JarvisState>((set) => ({
  activeWorkspace: 'jobs',
  setActiveWorkspace: (activeWorkspace) => set({ activeWorkspace }),

  aiCoreState: 'idle',
  setAiCoreState: (aiCoreState) => set({ aiCoreState }),
  aiCoreLabel: 'Ready',
  setAiCoreLabel: (aiCoreLabel) => set({ aiCoreLabel }),

  activities: [],
  addActivity: (activity) => set((s) => ({
    activities: [...s.activities.slice(-49), activity],
  })),
  updateActivity: (id, updates) => set((s) => ({
    activities: s.activities.map((a) =>
      a.id === id ? { ...a, ...updates } : a
    ),
  })),
  clearActivities: () => set({ activities: [] }),

  candidateProfile: null,
  setCandidateProfile: (candidateProfile) => set({ candidateProfile }),
  resumeFileName: '',
  setResumeFileName: (resumeFileName) => set({ resumeFileName }),

  jobs: [],
  setJobs: (jobs) => set({ jobs }),

  matchResults: [],
  setMatchResults: (matchResults) => set({ matchResults }),

  tailoredResume: null,
  setTailoredResume: (tailoredResume) => set({ tailoredResume }),

  validationReport: null,
  setValidationReport: (validationReport) => set({ validationReport }),

  isProcessing: false,
  setIsProcessing: (isProcessing) => set({ isProcessing }),
  processingStage: '',
  setProcessingStage: (processingStage) => set({ processingStage }),

  savedJobs: [],
  setSavedJobs: (savedJobs) => set({ savedJobs }),

  selectedJobIndex: null,
  setSelectedJobIndex: (selectedJobIndex) => set({ selectedJobIndex }),

  customJdDraft: null,
  setCustomJdDraft: (customJdDraft) => set({ customJdDraft }),

  settingsOpen: false,
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),

  sessionId: typeof window !== 'undefined' ? (crypto.randomUUID?.() || `s-${Date.now()}`) : 'session-default',
  setSessionId: (sessionId) => set({ sessionId }),

  voiceSessionActive: false,
  setVoiceSessionActive: (voiceSessionActive) => set({ voiceSessionActive }),

  appMode: 'career',
  setAppMode: (appMode) => set({ appMode }),

  computerState: {
    isRunning: false,
    planDescription: '',
    steps: [],
    currentStepIdx: -1,
    currentStepDescription: '',
    lastVerified: null,
    lastResponse: '',
    needsConfirm: false,
    stepResults: [],
  },
  setComputerState: (updates) => set((s) => ({
    computerState: { ...s.computerState, ...updates },
  })),
  resetComputerState: () => set({
    computerState: {
      isRunning: false,
      planDescription: '',
      steps: [],
      currentStepIdx: -1,
      currentStepDescription: '',
      lastVerified: null,
      lastResponse: '',
      needsConfirm: false,
      stepResults: [],
    }
  }),

  computerContext: {
    site: null,
    domain: null,
    page: null,
    channel: null,
    playlist: null,
    course: null,
    video: null,
    videoUrl: null,
    activeBrowser: null,
    activeApp: null,
    activeWindow: null,
    currentUrl: null,
    windowTitle: null,
    webSite: null,
    webChannel: null,
    webVideo: null,
    currentList: [],
    ordinalBasis: null,
    currentDirectory: null,
  },
  setComputerContext: (updates) => set((s) => ({
    computerContext: { ...s.computerContext, ...updates },
  })),
}))
