import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle,
  Clock,
  AlertCircle,
  Zap,
  Loader2,
  MinusCircle,
  Search,
  Filter,
  BarChart3,
  Cpu,
  Target,
  Wand2,
  ShieldCheck,
  Activity,
  Layers,
} from 'lucide-react'
import { useStore } from '../../store/useStore'
import type { ActivityItem } from '../../store/useStore'

interface PipelineNode {
  id: string
  label: string
  icon: any
  desc: string
}

const PIPELINE_NODES: PipelineNode[] = [
  { id: 'fetch_sources', label: 'Discovery', icon: Search, desc: 'Fetch postings across job sources' },
  { id: 'deduplicate_jobs', label: 'Dedup', icon: Filter, desc: 'Cross-source URL & title clustering' },
  { id: 'rank_jobs', label: 'Ranking', icon: BarChart3, desc: 'Deterministic score & feature ordering' },
  { id: 'analyze_jd', label: 'JD Analysis', icon: Cpu, desc: 'Evidence-anchored requirement extraction' },
  { id: 'match_candidate_to_jobs', label: 'Matching', icon: Target, desc: 'Candidate fit & gap scoring' },
  { id: 'tailor_resume', label: 'Tailoring', icon: Wand2, desc: 'Fact-grounded evidence selection' },
  { id: 'validate_resume', label: 'Validation', icon: ShieldCheck, desc: 'T1–T10 truth & A1–A8 ATS compliance' },
]

export function ActivityWorkspace() {
  const { activities, isProcessing, processingStage, jobs, matchResults, tailoredResume, validationReport } = useStore()

  const getStatusIcon = (status: ActivityItem['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle size={13} className="text-emerald-400" />
      case 'skipped':
        return <MinusCircle size={13} className="text-jarvis-muted/70" />
      case 'active':
        return <Loader2 size={13} className="text-blue-400 animate-spin" />
      case 'error':
        return <AlertCircle size={13} className="text-red-400" />
      case 'pending':
        return <Clock size={13} className="text-jarvis-muted/50" />
    }
  }

  const getNodeState = (nodeId: string) => {
    // Check in activities
    const matchingActivity = activities.find(
      (a) => a.node === nodeId || a.id.toLowerCase().includes(nodeId) || a.label.toLowerCase().includes(nodeId)
    )
    if (matchingActivity) return matchingActivity.status

    // Check artifacts
    if (nodeId === 'fetch_sources' && jobs.length > 0) return 'completed'
    if (nodeId === 'deduplicate_jobs' && jobs.length > 0) return 'completed'
    if (nodeId === 'rank_jobs' && jobs.length > 0) return 'completed'
    if (nodeId === 'match_candidate_to_jobs' && matchResults.length > 0) return 'completed'
    if (nodeId === 'tailor_resume' && tailoredResume) return 'completed'
    if (nodeId === 'validate_resume' && validationReport) return 'completed'

    if (isProcessing && processingStage?.toLowerCase().includes(nodeId.replace('_', ' '))) {
      return 'active'
    }
    return 'pending'
  }

  const completedCount = activities.filter((a) => a.status === 'completed').length
  const totalCount = activities.length

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 scrollbar-thin">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={15} className="text-jarvis-accent" />
          <h3 className="text-xs font-semibold text-white uppercase tracking-wider">Observable Execution Graph</h3>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-jarvis-surface/60 border border-jarvis-border/40 text-jarvis-muted">
          LangGraph • 7 Nodes
        </span>
      </div>

      {/* Observability Telemetry Strip */}
      <div className="grid grid-cols-3 gap-2 p-2.5 rounded-xl bg-jarvis-surface/30 border border-jarvis-border/30 text-center">
        <div className="p-1.5 rounded-lg bg-jarvis-dark/40">
          <p className="text-[10px] text-jarvis-muted uppercase tracking-wider">Discovered</p>
          <p className="text-sm font-bold text-white mt-0.5">{jobs.length}</p>
        </div>
        <div className="p-1.5 rounded-lg bg-jarvis-dark/40">
          <p className="text-[10px] text-jarvis-muted uppercase tracking-wider">Scored</p>
          <p className="text-sm font-bold text-cyan-400 mt-0.5">{matchResults.length}</p>
        </div>
        <div className="p-1.5 rounded-lg bg-jarvis-dark/40">
          <p className="text-[10px] text-jarvis-muted uppercase tracking-wider">Audit</p>
          <p className="text-sm font-bold text-emerald-400 mt-0.5">
            {validationReport ? 'PASSED' : 'READY'}
          </p>
        </div>
      </div>

      {/* Active Pipeline Stage Banner */}
      {isProcessing && processingStage && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex items-center gap-2.5 p-3 rounded-xl border border-cyan-500/30 bg-gradient-to-r from-blue-950/40 via-cyan-950/30 to-transparent"
        >
          <Zap size={15} className="text-cyan-400 animate-pulse" />
          <div className="min-w-0 flex-1">
            <p className="text-[10px] text-cyan-300/70 font-semibold uppercase tracking-wider">Executing Node</p>
            <p className="text-xs text-white font-medium truncate">{processingStage}</p>
          </div>
          <Loader2 size={13} className="text-cyan-400 animate-spin" />
        </motion.div>
      )}

      {/* Visual Pipeline Graph */}
      <div className="p-3.5 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold text-jarvis-muted uppercase tracking-wider flex items-center gap-1.5">
            <Layers size={12} />
            Pipeline Stages
          </span>
          <span className="text-[10px] text-jarvis-muted/70">Deterministic & Fact-Grounded</span>
        </div>

        <div className="space-y-1.5">
          {PIPELINE_NODES.map((node, i) => {
            const state = getNodeState(node.id)
            const Icon = node.icon
            const isNodeActive = state === 'active'
            const isNodeDone = state === 'completed'

            return (
              <div
                key={node.id}
                className={`flex items-center gap-2.5 p-2 rounded-lg border text-xs transition-all ${
                  isNodeActive
                    ? 'bg-blue-500/15 border-blue-500/40 shadow-sm shadow-blue-500/10'
                    : isNodeDone
                      ? 'bg-emerald-500/5 border-emerald-500/20'
                      : 'bg-jarvis-dark/30 border-jarvis-border/20 text-jarvis-muted/70'
                }`}
              >
                <div
                  className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 ${
                    isNodeActive
                      ? 'bg-blue-500 text-white animate-pulse'
                      : isNodeDone
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : 'bg-jarvis-surface/40 text-jarvis-muted/50'
                  }`}
                >
                  <Icon size={12} />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={`font-semibold ${isNodeDone || isNodeActive ? 'text-white' : 'text-jarvis-muted'}`}>
                      {i + 1}. {node.label}
                    </span>
                    {isNodeActive && (
                      <span className="px-1.5 py-0.2 text-[9px] rounded bg-blue-500/20 text-blue-300 font-bold">
                        RUNNING
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-jarvis-muted/70 truncate">{node.desc}</p>
                </div>

                {isNodeDone ? (
                  <CheckCircle size={13} className="text-emerald-400 flex-shrink-0" />
                ) : isNodeActive ? (
                  <Loader2 size={13} className="text-blue-400 animate-spin flex-shrink-0" />
                ) : (
                  <span className="text-[10px] text-jarvis-muted/40 font-mono flex-shrink-0">PENDING</span>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Step Execution Log */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold text-jarvis-muted uppercase tracking-wider">
            Telemetry Events ({activities.length})
          </span>
          {totalCount > 0 && (
            <span className="text-[10px] text-jarvis-muted/60">
              {completedCount} completed
            </span>
          )}
        </div>

        <div className="space-y-1 max-h-56 overflow-y-auto pr-1 scrollbar-thin">
          <AnimatePresence mode="popLayout">
            {activities.map((activity, index) => (
              <motion.div
                key={activity.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                transition={{ delay: index * 0.02 }}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-jarvis-surface/30 border border-jarvis-border/20 text-[11px]"
              >
                {getStatusIcon(activity.status)}
                <span className="flex-1 text-jarvis-light truncate">{activity.label}</span>
                <span className="text-[9px] text-jarvis-muted/50 tabular-nums font-mono">
                  {new Date(activity.timestamp).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </span>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
