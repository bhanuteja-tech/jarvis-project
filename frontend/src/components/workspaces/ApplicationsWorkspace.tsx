import { motion } from 'framer-motion'
import { Bookmark, Trash2, FolderOpen, Clock, Wand2 } from 'lucide-react'
import { useStore } from '../../store/useStore'

export function ApplicationsWorkspace() {
  const { savedJobs, setSavedJobs, setActiveWorkspace, setCustomJdDraft } = useStore()

  const handleRemove = (jobKey: string) => {
    setSavedJobs(savedJobs.filter((j) => j.job_key !== jobKey))
    fetch(`/api/jobs/saved/${encodeURIComponent(jobKey)}`, { method: 'DELETE' }).catch(() => {})
  }

  const handleTailorSavedJob = (job: any) => {
    setCustomJdDraft({
      title: job.title || '',
      company: job.company || '',
      jd_text: job.description || `${job.title} at ${job.company}. Location: ${job.location || 'Remote'}.`,
    })
    setActiveWorkspace('tailoring')
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'applied':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
      case 'interviewing':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
      case 'archived':
        return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
      default:
        return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 scrollbar-hide">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bookmark className="w-4 h-4 text-jarvis-accent" />
          <h3 className="text-sm font-semibold text-white">Saved Applications</h3>
        </div>
        <span className="text-xs text-jarvis-muted font-medium">{savedJobs.length} saved</span>
      </div>

      {savedJobs.length === 0 ? (
        <div className="h-64 flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-jarvis-border/40 rounded-2xl bg-jarvis-surface/20">
          <FolderOpen className="w-10 h-10 text-jarvis-accent/40 mb-3" />
          <h4 className="text-sm font-semibold text-white mb-1">No Saved Jobs</h4>
          <p className="text-xs text-jarvis-muted/70 max-w-xs">
            Save interesting jobs from the Jobs tab to track your application pipeline and status.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {savedJobs.map((job, index) => (
            <motion.div
              key={job.job_key || index}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
              className="p-3.5 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 hover:border-jarvis-accent/40 transition-all space-y-2.5"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h4 className="text-xs font-bold text-white leading-tight">{job.title}</h4>
                  <p className="text-[11px] text-jarvis-muted mt-0.5">{job.company} • {job.location}</p>
                </div>
                <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase ${getStatusColor(job.status)}`}>
                  {job.status}
                </span>
              </div>

              <div className="flex items-center justify-between text-[10px] text-jarvis-muted/80 pt-1 border-t border-jarvis-border/30">
                <span className="flex items-center gap-1">
                  <Clock size={10} /> Saved {job.saved_at ? new Date(job.saved_at).toLocaleDateString() : 'Recently'}
                </span>
                {job.score !== undefined && (
                  <span className="text-cyan-400 font-semibold">{job.score}% Match</span>
                )}
              </div>

              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={() => handleTailorSavedJob(job)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-blue-600 via-indigo-600 to-cyan-500 text-white hover:brightness-110 shadow-sm shadow-blue-500/20 transition-all flex-1 justify-center"
                >
                  <Wand2 size={12} />
                  Tailor / Edit Resume
                </button>
                <button
                  onClick={() => handleRemove(job.job_key)}
                  className="p-1.5 bg-rose-500/10 border border-rose-500/30 rounded-lg hover:bg-rose-500/20 text-rose-400 transition-all"
                  title="Remove saved job"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
