import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Briefcase, MapPin, Building2, ExternalLink, Wand2,
  ChevronDown, ChevronUp, MessageSquare, TrendingUp, AlertTriangle, Sparkles, FileEdit
} from 'lucide-react'
import { useStore } from '../../store/useStore'
import type { MatchResult } from '../../store/useStore'

interface JobsWorkspaceProps {
  onTailorRequest: (jobIndex: number) => void
  onJobQuestion: (jobIndex: number, question: string) => void
}

export function JobsWorkspace({ onTailorRequest, onJobQuestion }: JobsWorkspaceProps) {
  const { jobs, matchResults, candidateProfile, setActiveWorkspace, setSelectedJobIndex } = useStore()
  const [expandedJob, setExpandedJob] = useState<number | null>(null)

  const handleApplyAndTailor = (jobIndex: number) => {
    setSelectedJobIndex(jobIndex)
    setActiveWorkspace('tailoring')
    onTailorRequest(jobIndex)
  }

  const handleOpenDocStudio = (jobIndex: number) => {
    setSelectedJobIndex(jobIndex)
    setActiveWorkspace('doc-studio')
    onTailorRequest(jobIndex)
  }

  const getMatch = (jobIndex: number): MatchResult | undefined => {
    return matchResults.find(m => m.job_index === jobIndex)
  }

  const getScoreColor = (score?: number) => {
    if (!score) return 'text-jarvis-muted/50'
    if (score >= 75) return 'text-emerald-400'
    if (score >= 50) return 'text-amber-400'
    return 'text-red-400'
  }

  const getScoreRingColor = (score?: number) => {
    if (!score) return '#64748b'
    if (score >= 75) return '#34d399'
    if (score >= 50) return '#fbbf24'
    return '#f87171'
  }

  const getTierBadge = (tier?: string) => {
    switch (tier) {
      case 'strong':
        return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20'
      case 'moderate':
        return 'bg-amber-500/15 text-amber-400 border-amber-500/20'
      default:
        return 'bg-jarvis-surface/50 text-jarvis-muted border-jarvis-border/30'
    }
  }

  const hasResume = !!candidateProfile

  return (
    <div className="h-full overflow-y-auto p-4 space-y-3 scrollbar-thin">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold text-jarvis-accent uppercase tracking-wider">Job Matches</h3>
        <span className="text-[10px] text-jarvis-muted">
          {jobs.length} {jobs.length === 1 ? 'result' : 'results'}
          {matchResults.length > 0 && ` · ${matchResults.filter(m => m.tier === 'strong').length} strong`}
        </span>
      </div>

      {/* Job Cards */}
      <div className="space-y-2.5">
        <AnimatePresence mode="popLayout">
          {jobs.map((job, index) => {
            const match = getMatch(job.__index)
            const isExpanded = expandedJob === index
            const score = match?.score

            return (
              <motion.div
                key={job.job_key || index}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.2, delay: index * 0.04 }}
                className={`card-hover p-3.5 rounded-xl border transition-all ${
                  isExpanded
                    ? 'border-jarvis-accent/40 bg-jarvis-surface/50 shadow-md shadow-black/20'
                    : 'border-jarvis-border/30 bg-jarvis-surface/30'
                }`}
              >
                {/* Main card */}
                <div>
                  <div className="flex items-start gap-3">
                    {/* Score ring */}
                    {score !== undefined && (
                      <div className="relative w-11 h-11 flex-shrink-0 flex items-center justify-center">
                        <svg className="w-11 h-11 -rotate-90" viewBox="0 0 36 36">
                          <circle
                            cx="18" cy="18" r="14"
                            fill="none"
                            stroke="rgba(100, 116, 139, 0.2)"
                            strokeWidth="3"
                          />
                          <circle
                            cx="18" cy="18" r="14"
                            fill="none"
                            stroke={getScoreRingColor(score)}
                            strokeWidth="3"
                            strokeDasharray={`${(score / 100) * 88} 88`}
                            strokeLinecap="round"
                            className="transition-all duration-700 ease-out"
                          />
                        </svg>
                        <span className={`absolute text-xs font-bold ${getScoreColor(score)}`}>
                          {Math.round(score)}
                        </span>
                      </div>
                    )}

                    {/* Job info */}
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-semibold text-white truncate">{job.title || 'Untitled Role'}</h4>
                      <div className="flex items-center gap-1.5 mt-1">
                        <Building2 size={12} className="text-jarvis-muted/60 flex-shrink-0" />
                        <span className="text-xs text-jarvis-muted truncate">{job.company || 'Unknown'}</span>
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        {job.location && (
                          <div className="flex items-center gap-1">
                            <MapPin size={11} className="text-jarvis-muted/50" />
                            <span className="text-[11px] text-jarvis-muted/60 truncate">{job.location}</span>
                          </div>
                        )}
                        {job.employment_type && (
                          <span className="text-[10px] text-jarvis-muted/50 px-1.5 py-0.5 rounded bg-jarvis-darker/40">
                            {job.employment_type}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Tier badge */}
                  {match?.tier && (
                    <div className="mt-2.5 flex items-center gap-2">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium ${getTierBadge(match.tier)}`}>
                        <TrendingUp size={10} />
                        {match.tier} match
                      </span>
                      {match.matched_skills && match.matched_skills.length > 0 && (
                        <span className="text-[10px] text-jarvis-muted/50 truncate">
                          {match.matched_skills.slice(0, 3).join(', ')}
                          {match.matched_skills.length > 3 && ` +${match.matched_skills.length - 3}`}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex flex-wrap items-center gap-1.5 mt-3">
                    {/* Primary Stand Out & Tailor Button */}
                    <button
                      onClick={() => handleApplyAndTailor(job.__index)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold rounded-lg bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-500 text-white hover:brightness-110 shadow-sm shadow-blue-500/20 transition-all"
                      title="Analyze match gaps, get missing ATS keywords & standout projects, and tailor your resume"
                    >
                      <Sparkles size={11} />
                      Stand Out & Tailor
                    </button>

                    <button
                      onClick={() => handleOpenDocStudio(job.__index)}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 hover:bg-indigo-500/25 transition-all"
                      title="Edit directly inside A4 PDF canvas with live AI Copilot"
                    >
                      <FileEdit size={11} />
                      PDF Studio ↗
                    </button>

                    {job.job_url && (
                      <a
                        href={job.job_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-lg bg-jarvis-surface/50 border border-jarvis-border/30 text-jarvis-muted hover:text-jarvis-accent hover:border-jarvis-accent/30 transition-all"
                      >
                        <ExternalLink size={11} />
                        View Job
                      </a>
                    )}
                    {hasResume && (
                      <button
                        onClick={() => onTailorRequest(job.__index)}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-lg bg-jarvis-surface/50 border border-jarvis-border/30 text-jarvis-muted hover:text-jarvis-accent hover:border-jarvis-accent/30 transition-all"
                      >
                        <Wand2 size={11} />
                        Tailor
                      </button>
                    )}
                    <button
                      onClick={() => onJobQuestion(job.__index, 'Tell me about this job and why I might be a good fit.')}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] rounded-lg bg-jarvis-surface/50 border border-jarvis-border/30 text-jarvis-muted hover:text-jarvis-accent hover:border-jarvis-accent/30 transition-all"
                    >
                      <MessageSquare size={11} />
                      Ask
                    </button>
                    {match && (
                      <button
                        onClick={() => setExpandedJob(isExpanded ? null : index)}
                        className="ml-auto p-1.5 rounded-lg bg-jarvis-surface/30 text-jarvis-muted hover:text-jarvis-accent transition-all"
                      >
                        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      </button>
                    )}
                  </div>
                </div>

                {/* Expanded match details */}
                <AnimatePresence>
                  {isExpanded && match && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-3.5 pb-3.5 pt-0 border-t border-jarvis-border/20">
                        <div className="pt-3 space-y-3">
                          {/* Score Breakdown */}
                          {match.breakdown && (
                            <div>
                              <p className="text-[10px] font-medium text-jarvis-accent uppercase tracking-wider mb-2">Score Breakdown</p>
                              <div className="grid grid-cols-2 gap-1.5">
                                {Object.entries(match.breakdown).map(([key, value]) => (
                                  <div key={key} className="flex items-center justify-between px-2 py-1 rounded bg-jarvis-darker/30">
                                    <span className="text-[10px] text-jarvis-muted capitalize">{key.replace(/_/g, ' ')}</span>
                                    <span className="text-[10px] text-jarvis-light font-medium">{typeof value === 'number' ? value : String(value)}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Matched Skills */}
                          {match.matched_skills && match.matched_skills.length > 0 && (
                            <div>
                              <p className="text-[10px] font-medium text-emerald-400 mb-1.5">✓ Matched Skills</p>
                              <div className="flex flex-wrap gap-1">
                                {match.matched_skills.map(skill => (
                                  <span key={skill} className="px-1.5 py-0.5 text-[10px] rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                    {skill}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Missing Requirements */}
                          {match.missing_requirements && match.missing_requirements.length > 0 && (
                            <div>
                              <p className="text-[10px] font-medium text-amber-400 flex items-center gap-1 mb-1.5">
                                <AlertTriangle size={10} />
                                Potential Gaps
                              </p>
                              <div className="flex flex-wrap gap-1">
                                {match.missing_requirements.map(req => (
                                  <span key={req} className="px-1.5 py-0.5 text-[10px] rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                    {req}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Match Reasons */}
                          {match.reasons && match.reasons.length > 0 && (
                            <div>
                              <p className="text-[10px] font-medium text-jarvis-accent mb-1.5">Why You Match</p>
                              <ul className="space-y-1">
                                {match.reasons.map((reason, i) => (
                                  <li key={i} className="text-[10px] text-jarvis-muted flex items-start gap-1.5">
                                    <span className="text-jarvis-accent mt-0.5">•</span>
                                    {reason}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>

      {/* Empty State */}
      {jobs.length === 0 && (
        <div className="text-center py-16">
          <div className="w-12 h-12 mx-auto mb-3 rounded-xl bg-jarvis-surface/30 border border-jarvis-border/20 flex items-center justify-center">
            <Briefcase size={20} className="text-jarvis-muted/30" />
          </div>
          <p className="text-xs text-jarvis-muted/50">No jobs found yet</p>
          <p className="text-[10px] text-jarvis-muted/30 mt-1">
            Try "Find Python developer jobs in Bangalore"
          </p>
        </div>
      )}
    </div>
  )
}
