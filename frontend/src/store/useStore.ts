import { create } from 'zustand'

export type AiCoreState = 'idle' | 'listening' | 'thinking' | 'searching' | 'analyzing' | 'speaking' | 'error'

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
}))
