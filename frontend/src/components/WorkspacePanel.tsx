import { motion, AnimatePresence } from 'framer-motion'
import { useStore } from '../store/useStore'
import { ActivityWorkspace } from './workspaces/ActivityWorkspace'
import { JobsWorkspace } from './workspaces/JobsWorkspace'
import { ResumeWorkspace } from './workspaces/ResumeWorkspace'
import { TailoringWorkspace } from './workspaces/TailoringWorkspace'
import { ValidationWorkspace } from './workspaces/ValidationWorkspace'
import { Activity, Briefcase, FileText, Wand2, ShieldCheck, FileEdit } from 'lucide-react'

const WORKSPACE_TABS = [
  { id: 'activity', title: 'Activity', icon: Activity },
  { id: 'jobs', title: 'Jobs', icon: Briefcase },
  { id: 'resume', title: 'Resume', icon: FileText },
  { id: 'tailoring', title: 'Tailor', icon: Wand2 },
  { id: 'doc-studio', title: 'PDF Studio', icon: FileEdit },
  { id: 'validation', title: 'Validate', icon: ShieldCheck },
]

interface WorkspacePanelProps {
  activeWorkspace: string
  onWorkspaceChange: (workspace: string) => void
  onTailorRequest: (jobIndex: number) => void
  onJobQuestion: (jobIndex: number, question: string) => void
  onResumeUpload: (file: File) => void
}

export function WorkspacePanel({
  activeWorkspace,
  onWorkspaceChange,
  onTailorRequest,
  onJobQuestion,
  onResumeUpload,
}: WorkspacePanelProps) {
  const { jobs, tailoredResume, validationReport } = useStore()

  // Badge counts
  const jobCount = jobs.length
  const hasTailored = !!tailoredResume
  const hasValidation = !!validationReport

  const getBadge = (id: string): string | null => {
    if (id === 'jobs' && jobCount > 0) return String(jobCount)
    if (id === 'tailoring' && hasTailored) return '✓'
    if (id === 'validation' && hasValidation) return '✓'
    return null
  }

  const renderWorkspace = () => {
    switch (activeWorkspace) {
      case 'activity':
        return <ActivityWorkspace />
      case 'jobs':
        return <JobsWorkspace onTailorRequest={onTailorRequest} onJobQuestion={onJobQuestion} />
      case 'resume':
        return <ResumeWorkspace onResumeUpload={onResumeUpload} />
      case 'tailoring':
        return <TailoringWorkspace />
      case 'validation':
        return <ValidationWorkspace />
      default:
        return <ActivityWorkspace />
    }
  }

  return (
    <div className="w-[400px] min-w-[340px] glass-strong border-l border-jarvis-border/30 flex flex-col">
      {/* Workspace Tabs */}
      <div className="flex border-b border-jarvis-border/30">
        {WORKSPACE_TABS.map((tab) => {
          const Icon = tab.icon
          const badge = getBadge(tab.id)
          const isActive = activeWorkspace === tab.id

          return (
            <button
              key={tab.id}
              onClick={() => onWorkspaceChange(tab.id)}
              className={`flex-1 flex flex-col items-center gap-1 px-2 py-2.5 text-[10px] font-medium transition-all relative ${
                isActive
                  ? 'text-jarvis-accent'
                  : 'text-jarvis-muted/60 hover:text-jarvis-muted'
              }`}
            >
              <div className="relative">
                <Icon size={14} />
                {badge && (
                  <span className="absolute -top-1.5 -right-2.5 min-w-[14px] h-[14px] flex items-center justify-center px-1 text-[8px] font-bold rounded-full bg-jarvis-accent text-jarvis-dark">
                    {badge}
                  </span>
                )}
              </div>
              <span className="tracking-wide uppercase">{tab.title}</span>
              {isActive && (
                <motion.div
                  layoutId="workspace-indicator"
                  className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-gradient-to-r from-blue-500 to-cyan-500"
                />
              )}
            </button>
          )
        })}
      </div>

      {/* Workspace Content */}
      <div className="flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeWorkspace}
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.15 }}
            className="h-full"
          >
            {renderWorkspace()}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}
