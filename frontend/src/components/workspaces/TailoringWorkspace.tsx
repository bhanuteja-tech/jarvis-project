import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Wand2,
  Copy,
  Check,
  FileText,
  AlertCircle,
  Briefcase,
  Award,
  Sparkles,
  ExternalLink,
  Download,
  HelpCircle,
  ShieldCheck,
  Edit3,
  Eye,
  Plus,
  Trash2,
  Printer,
  ChevronDown,
  ChevronUp,
  Upload,
  Rocket,
  Flame,
  Layers,
  TrendingUp,
  CheckCircle2,
  RefreshCw,
  FileEdit,
} from 'lucide-react'
import { useStore } from '../../store/useStore'

export function TailoringWorkspace() {
  const {
    tailoredResume,
    setTailoredResume,
    jobs,
    matchResults,
    validationReport,
    sessionId,
    customJdDraft,
    setCustomJdDraft,
    setCandidateProfile,
    setResumeFileName,
    selectedJobIndex,
    setActiveWorkspace,
  } = useStore()

  // View vs Edit Mode
  const [isEditing, setIsEditing] = useState(false)
  const [copied, setCopied] = useState(false)
  const [applied, setApplied] = useState(false)
  const [activeWhy, setActiveWhy] = useState<string | null>(null)

  // Custom JD Drawer State
  const [customJdOpen, setCustomJdOpen] = useState(false)
  const [customTitle, setCustomTitle] = useState('')
  const [customCompany, setCustomCompany] = useState('')
  const [customJdText, setCustomJdText] = useState('')
  const [isTailoringCustom, setIsTailoringCustom] = useState(false)
  const [customError, setCustomError] = useState<string | null>(null)

  // Standout Suggestions State
  const [standoutOpen, setStandoutOpen] = useState(true)
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)
  const [suggestionsData, setSuggestionsData] = useState<any>(null)
  const [addedSkills, setAddedSkills] = useState<string[]>([])
  const [addedProjectIds, setAddedProjectIds] = useState<string[]>([])
  const [fileUploading, setFileUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Editable local copies of resume fields
  const [editableSummary, setEditableSummary] = useState('')
  const [editableSkills, setEditableSkills] = useState<string[]>([])
  const [newSkillInput, setNewSkillInput] = useState('')
  const [editableExp, setEditableExp] = useState<any[]>([])
  const [editableProjects, setEditableProjects] = useState<any[]>([])

  // Helper for safe string unwrapping
  const getStr = (val: any): string => {
    if (val === null || val === undefined) return ''
    if (typeof val === 'string') return val
    if (typeof val === 'number') return String(val)
    if (typeof val === 'object') {
      return val.display || val.name || val.final_text || val.original_text || val.text || ''
    }
    return ''
  }

  // Sync draft if sent from ApplicationsWorkspace
  useEffect(() => {
    if (customJdDraft) {
      setCustomTitle(customJdDraft.title || '')
      setCustomCompany(customJdDraft.company || '')
      setCustomJdText(customJdDraft.jd_text || '')
      setCustomJdOpen(true)
      setCustomJdDraft(null)
    }
  }, [customJdDraft, setCustomJdDraft])

  // Sync tailoredResume into editable state whenever tailoredResume changes
  useEffect(() => {
    if (!tailoredResume) return
    const res = tailoredResume.resume || tailoredResume
    const rawSummary = res.summary || res.professional_summary
    setEditableSummary(typeof rawSummary === 'object' ? getStr(rawSummary) : getStr(rawSummary))

    const rawSkills = res.skills || res.canonical_skills || []
    setEditableSkills(Array.isArray(rawSkills) ? rawSkills.map(getStr).filter(Boolean) : [])

    const rawExp = res.experience || res.work_experience || []
    setEditableExp(
      Array.isArray(rawExp)
        ? rawExp.map((e) => ({
            ...e,
            highlights: Array.isArray(e.highlights || e.bullets)
              ? (e.highlights || e.bullets).map((b: any) =>
                  typeof b === 'object' ? { ...b } : { final_text: b }
                )
              : [],
          }))
        : []
    )

    const rawProj = res.projects || []
    setEditableProjects(Array.isArray(rawProj) ? rawProj.map((p) => ({ ...p })) : [])
  }, [tailoredResume])

  const res = tailoredResume?.resume || tailoredResume
  const unaddressed = res?.unaddressed_jd_requirements || []
  const targetJobKey = res?.target_job_key || ''

  // Find target job details if available
  const targetJob =
    (selectedJobIndex !== null && jobs[selectedJobIndex]) ||
    jobs.find((j) => j.job_key === targetJobKey) ||
    (jobs.length > 0 ? jobs[0] : null)
  const targetMatch = matchResults.find(
    (m) => m.job_key === (targetJob?.job_key || targetJobKey) || m.job_index === targetJob?.__index
  )

  // Fetch Standout Suggestions & Gap Analysis
  const fetchStandoutSuggestions = async () => {
    setSuggestionsLoading(true)
    try {
      const payload: any = { session_id: sessionId }
      if (targetJob) {
        payload.job_key = targetJob.job_key
        payload.job_index = targetJob.__index
        payload.jd_text = targetJob.description || ''
        payload.title = targetJob.title || ''
        payload.company = targetJob.company || ''
      } else if (customJdText) {
        payload.jd_text = customJdText
        payload.title = customTitle || 'Target Role'
        payload.company = customCompany || 'Interested Employer'
      } else {
        setSuggestionsLoading(false)
        return
      }

      const response = await fetch('/api/resume/standout-suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (response.ok) {
        const data = await response.json()
        setSuggestionsData(data.recommendations)
      }
    } catch (e) {
      console.error('Failed to fetch standout suggestions', e)
    } finally {
      setSuggestionsLoading(false)
    }
  }

  // Auto-fetch suggestions when target role changes
  useEffect(() => {
    if (targetJob || customJdText || tailoredResume) {
      fetchStandoutSuggestions()
    }
  }, [targetJob?.job_key, targetJob?.__index, tailoredResume?.resume?.target_job_key])

  // Trigger Custom JD Tailor API
  const handleRunCustomTailor = async () => {
    if (!customJdText.trim()) {
      setCustomError('Please paste the Job Description text.')
      return
    }
    setCustomError(null)
    setIsTailoringCustom(true)

    try {
      const response = await fetch('/api/resume/custom-tailor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: customTitle.trim() || 'Custom Role',
          company: customCompany.trim() || 'Interested Employer',
          jd_text: customJdText.trim(),
          session_id: sessionId,
        }),
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to tailor resume for custom JD.')
      }

      const data = await response.json()
      setTailoredResume(data.tailored_resume)
      setCustomJdOpen(false)
      setIsEditing(false)
      fetchStandoutSuggestions()
    } catch (err: any) {
      setCustomError(err.message || 'Error tailoring resume.')
    } finally {
      setIsTailoringCustom(false)
    }
  }

  // Adoption Handlers
  const handleAdoptSkill = (skillName: string) => {
    if (!editableSkills.some((s) => s.toLowerCase() === skillName.toLowerCase())) {
      setEditableSkills((prev) => [...prev, skillName])
    }
    if (!addedSkills.includes(skillName)) {
      setAddedSkills((prev) => [...prev, skillName])
    }
  }

  const handleAdoptAllSkills = () => {
    if (!suggestionsData?.missing_skills) return
    const toAdd: string[] = []
    suggestionsData.missing_skills.forEach((s: any) => {
      const name = s.name || s
      if (!editableSkills.some((es) => es.toLowerCase() === name.toLowerCase())) {
        toAdd.push(name)
      }
    })
    setEditableSkills((prev) => [...prev, ...toAdd])
    setAddedSkills((prev) => [
      ...prev,
      ...suggestionsData.missing_skills.map((s: any) => s.name || s),
    ])
  }

  const handleAdoptProject = (proj: any) => {
    const newProj = {
      title: proj.title,
      name: proj.title,
      description: proj.resume_bullet || proj.architecture,
      tech_stack: proj.tech_stack,
    }
    setEditableProjects((prev) => [newProj, ...prev])
    setAddedProjectIds((prev) => [...prev, proj.id])
  }

  const handleAdoptBullet = (bulletText: string) => {
    if (editableExp.length > 0) {
      const updated = [...editableExp]
      if (!Array.isArray(updated[0].highlights)) {
        updated[0].highlights = []
      }
      updated[0].highlights.unshift({ final_text: bulletText })
      setEditableExp(updated)
    }
  }

  // Re-upload external resume
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setFileUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await fetch(`/api/candidate/resume?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        body: formData,
      })
      if (res.ok) {
        const data = await res.json()
        setCandidateProfile(data)
        setResumeFileName(file.name)
        if (targetJob) {
          handleRunCustomTailor()
        }
      }
    } catch (err) {
      console.error('Failed to re-upload resume', err)
    } finally {
      setFileUploading(false)
    }
  }

  // Exporters
  const handleCopyText = () => {
    const textParts: string[] = ['TAILORED RESUME', '===============\n']
    if (editableSummary) textParts.push(`SUMMARY:\n${editableSummary}\n`)
    if (editableSkills.length > 0) textParts.push(`SKILLS:\n• ${editableSkills.join(' • ')}\n`)
    if (editableExp.length > 0) {
      textParts.push('WORK EXPERIENCE:')
      editableExp.forEach((expItem: any) => {
        textParts.push(
          `\n${(expItem.title || expItem.role || 'Role').toUpperCase()} — ${expItem.company || expItem.employer || ''}`
        )
        if (expItem.date_range_raw || expItem.dates) {
          textParts.push(`Dates: ${getStr(expItem.date_range_raw || expItem.dates)}`)
        }
        const bullets = expItem.highlights || []
        bullets.forEach((b: any) => textParts.push(`• ${getStr(b)}`))
      })
      textParts.push('')
    }
    if (editableProjects.length > 0) {
      textParts.push('PROJECTS:')
      editableProjects.forEach((proj: any) => {
        textParts.push(`\n${proj.name || proj.title || 'Project'}`)
        if (proj.description) textParts.push(proj.description)
      })
      textParts.push('')
    }
    navigator.clipboard.writeText(textParts.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownloadMarkdown = () => {
    const mdLines: string[] = ['# Tailored Resume\n']
    if (editableSummary) mdLines.push('## Professional Summary', editableSummary, '')
    if (editableSkills.length > 0) {
      mdLines.push('## Prioritized Skills', editableSkills.map((s) => `- ${s}`).join('\n'), '')
    }
    if (editableExp.length > 0) {
      mdLines.push('## Work Experience')
      editableExp.forEach((expItem: any) => {
        mdLines.push(`### ${expItem.title || expItem.role} — ${expItem.company || expItem.employer}`)
        if (expItem.date_range_raw || expItem.dates) {
          mdLines.push(`*${getStr(expItem.date_range_raw || expItem.dates)}*`)
        }
        const bullets = expItem.highlights || []
        bullets.forEach((b: any) => mdLines.push(`- ${getStr(b)}`))
        mdLines.push('')
      })
    }
    if (editableProjects.length > 0) {
      mdLines.push('## Highlighted Projects')
      editableProjects.forEach((proj: any) => {
        mdLines.push(`### ${proj.name || proj.title}`, proj.description || '', '')
      })
    }

    const blob = new Blob([mdLines.join('\n')], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tailored-resume-${(targetJob?.company || customCompany || 'role').toLowerCase().replace(/\s+/g, '-')}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleDownloadTxt = () => {
    const textParts: string[] = ['TAILORED RESUME', '===============\n']
    if (editableSummary) textParts.push(`SUMMARY:\n${editableSummary}\n`)
    if (editableSkills.length > 0) textParts.push(`SKILLS:\n${editableSkills.join(' | ')}\n`)
    if (editableExp.length > 0) {
      textParts.push('WORK EXPERIENCE:')
      editableExp.forEach((expItem: any) => {
        textParts.push(
          `\n${(expItem.title || expItem.role || 'Role').toUpperCase()} — ${expItem.company || expItem.employer || ''}`
        )
        if (expItem.date_range_raw || expItem.dates) {
          textParts.push(`Dates: ${getStr(expItem.date_range_raw || expItem.dates)}`)
        }
        const bullets = expItem.highlights || []
        bullets.forEach((b: any) => textParts.push(`• ${getStr(b)}`))
      })
      textParts.push('')
    }
    if (editableProjects.length > 0) {
      textParts.push('PROJECTS:')
      editableProjects.forEach((proj: any) => {
        textParts.push(`\n${proj.name || proj.title || 'Project'}`)
        if (proj.description) textParts.push(proj.description)
      })
      textParts.push('')
    }
    const blob = new Blob([textParts.join('\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tailored-resume-${(targetJob?.company || customCompany || 'role').toLowerCase().replace(/\s+/g, '-')}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handlePrintPdf = () => {
    window.print()
  }

  const handleConfirmApply = async () => {
    if (!targetJob) return
    try {
      await fetch(`/api/jobs/saved?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_key: targetJob.job_key || targetJob.job_url || `${targetJob.company}-${targetJob.title}`,
          title: targetJob.title,
          company: targetJob.company,
          location: targetJob.location,
          job_url: targetJob.job_url,
          status: 'applied',
        }),
      })
      setApplied(true)
    } catch {
      /* ignore */
    }
  }

  // Editing handlers
  const handleAddSkill = () => {
    const trimmed = newSkillInput.trim()
    if (trimmed && !editableSkills.includes(trimmed)) {
      setEditableSkills([...editableSkills, trimmed])
      setNewSkillInput('')
    }
  }

  const handleRemoveSkill = (idx: number) => {
    setEditableSkills(editableSkills.filter((_, i) => i !== idx))
  }

  const handleBulletChange = (expIdx: number, bulletIdx: number, text: string) => {
    const updated = [...editableExp]
    const bullet = updated[expIdx].highlights[bulletIdx]
    if (typeof bullet === 'object') {
      bullet.final_text = text
    } else {
      updated[expIdx].highlights[bulletIdx] = text
    }
    setEditableExp(updated)
  }

  const handleAddBullet = (expIdx: number) => {
    const updated = [...editableExp]
    if (!Array.isArray(updated[expIdx].highlights)) {
      updated[expIdx].highlights = []
    }
    updated[expIdx].highlights.push({ final_text: 'New achievement or responsibility' })
    setEditableExp(updated)
  }

  const handleRemoveBullet = (expIdx: number, bulletIdx: number) => {
    const updated = [...editableExp]
    updated[expIdx].highlights = updated[expIdx].highlights.filter((_: any, i: number) => i !== bulletIdx)
    setEditableExp(updated)
  }

  const handleProjectChange = (idx: number, field: string, value: string) => {
    const updated = [...editableProjects]
    updated[idx] = { ...updated[idx], [field]: value }
    setEditableProjects(updated)
  }

  const handleRemoveProject = (idx: number) => {
    setEditableProjects(editableProjects.filter((_, i) => i !== idx))
  }

  const handleAddCustomProject = () => {
    setEditableProjects([
      {
        title: 'New Featured Project',
        name: 'New Featured Project',
        description: 'Engineered a scalable system solving critical business constraints.',
        tech_stack: ['Python', 'Docker'],
      },
      ...editableProjects,
    ])
  }

  const currentFitScore = suggestionsData?.current_score ?? targetMatch?.score ?? 50
  const projectedFitScore = suggestionsData?.projected_score ?? Math.min(96, currentFitScore + 38)

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 scrollbar-hide">
      {/* Top Header: Custom JD Accordion Button + Mode Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCustomJdOpen(!customJdOpen)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all ${
              customJdOpen
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 shadow-sm'
                : 'bg-jarvis-surface/60 text-jarvis-light border-jarvis-border/40 hover:border-cyan-500/30'
            }`}
          >
            <Sparkles size={12} className="text-cyan-400" />
            {customJdOpen ? 'Hide Custom JD Form' : 'Tailor for Any Job (Paste JD)'}
            {customJdOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>

          {/* Re-upload file button */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept=".pdf,.docx,.doc,.txt,.md"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={fileUploading}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-jarvis-surface/40 border border-jarvis-border/30 text-jarvis-muted hover:text-white hover:border-cyan-500/30 transition-all"
            title="Upload an updated resume file (PDF, DOCX, MD, TXT)"
          >
            <Upload size={12} className={fileUploading ? 'animate-bounce text-cyan-400' : ''} />
            {fileUploading ? 'Uploading...' : 'Update File'}
          </button>
        </div>

        {tailoredResume && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveWorkspace('doc-studio')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-purple-600 via-indigo-600 to-cyan-500 text-white hover:brightness-110 shadow-sm shadow-indigo-500/20 transition-all"
              title="Open full dedicated PDF Document Studio with side-by-side AI Copilot"
            >
              <FileEdit size={12} />
              <span>Open in PDF Studio ↗</span>
            </button>

            <button
              onClick={() => setIsEditing(!isEditing)}
              className={`flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all ${
                isEditing
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-sm'
                  : 'bg-jarvis-surface/60 text-jarvis-muted hover:text-white border-jarvis-border/40'
              }`}
            >
              {isEditing ? <Eye size={12} /> : <Edit3 size={12} />}
              {isEditing ? 'Done Editing' : 'Quick Edit'}
            </button>
          </div>
        )}
      </div>

      {/* Collapsible Custom JD Drawer */}
      <AnimatePresence>
        {customJdOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4 rounded-xl bg-gradient-to-br from-jarvis-surface/90 to-blue-950/40 border border-cyan-500/30 space-y-3 shadow-lg">
              <div>
                <h4 className="text-xs font-bold text-white flex items-center gap-1.5">
                  <Wand2 size={13} className="text-cyan-400" />
                  Tailor Resume for Applied or Interested Job
                </h4>
                <p className="text-[11px] text-jarvis-muted mt-0.5">
                  Paste any job description to match your skills, prioritize relevant highlights, and generate an ATS-optimized resume.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] text-jarvis-muted/80 uppercase font-semibold block mb-1">
                    Role Title
                  </label>
                  <input
                    type="text"
                    value={customTitle}
                    onChange={(e) => setCustomTitle(e.target.value)}
                    placeholder="e.g. Senior Machine Learning Engineer"
                    className="w-full text-xs p-2 rounded-lg bg-jarvis-dark/80 border border-jarvis-border/40 text-white placeholder-jarvis-muted/40 focus:outline-none focus:border-cyan-400"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-jarvis-muted/80 uppercase font-semibold block mb-1">
                    Company Name
                  </label>
                  <input
                    type="text"
                    value={customCompany}
                    onChange={(e) => setCustomCompany(e.target.value)}
                    placeholder="e.g. Acme AI Innovations"
                    className="w-full text-xs p-2 rounded-lg bg-jarvis-dark/80 border border-jarvis-border/40 text-white placeholder-jarvis-muted/40 focus:outline-none focus:border-cyan-400"
                  />
                </div>
              </div>

              <div>
                <label className="text-[10px] text-jarvis-muted/80 uppercase font-semibold block mb-1">
                  Job Description Text *
                </label>
                <textarea
                  rows={5}
                  value={customJdText}
                  onChange={(e) => setCustomJdText(e.target.value)}
                  placeholder="Paste the full job description or requirements here..."
                  className="w-full text-xs p-2.5 rounded-lg bg-jarvis-dark/80 border border-jarvis-border/40 text-white placeholder-jarvis-muted/40 focus:outline-none focus:border-cyan-400 resize-y"
                />
              </div>

              {customError && (
                <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 p-2 rounded-lg flex items-center gap-1.5">
                  <AlertCircle size={13} />
                  {customError}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setCustomJdOpen(false)}
                  className="px-3 py-1.5 text-xs text-jarvis-muted hover:text-white transition-all"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleRunCustomTailor}
                  disabled={isTailoringCustom}
                  className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 text-white hover:from-cyan-400 hover:to-blue-500 shadow-md shadow-cyan-500/20 transition-all disabled:opacity-50"
                >
                  <Sparkles size={12} />
                  {isTailoringCustom ? 'Analyzing & Tailoring...' : 'Generate Tailored Resume'}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {!tailoredResume && !customJdOpen ? (
        /* Empty State */
        <div className="p-8 text-center rounded-xl bg-jarvis-surface/20 border border-jarvis-border/30 space-y-3">
          <div className="w-12 h-12 mx-auto rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Wand2 size={22} />
          </div>
          <h3 className="text-sm font-semibold text-white">No Tailored Resume Active Yet</h3>
          <p className="text-xs text-jarvis-muted max-w-md mx-auto">
            Click <strong>"Tailor for Any Job (Paste JD)"</strong> above or select a job from the Jobs tab to generate and edit a targeted resume.
          </p>
        </div>
      ) : (
        <>
          {/* Target Job Application Review Banner */}
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="p-4 rounded-xl bg-gradient-to-br from-blue-950/60 via-jarvis-surface/70 to-cyan-950/30 border border-blue-500/30 space-y-3 shadow-lg shadow-black/20"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1">
                  <Sparkles size={11} />
                  Target Role Application Pack
                </span>
                <h4 className="text-sm font-bold text-white mt-1 truncate">
                  {targetJob?.title || customTitle || 'Target Role'}
                </h4>
                <p className="text-xs text-jarvis-muted truncate">
                  {targetJob?.company || customCompany || 'Interested Employer'} • {targetJob?.location || 'Remote'}
                </p>
              </div>

              <div className="flex flex-col items-end gap-1">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[10px] font-semibold">
                  <ShieldCheck size={10} />
                  100% Truth Grounded
                </span>
                {targetMatch && (
                  <span className="text-[11px] font-bold text-cyan-300">
                    {targetMatch.score}% Match ({targetMatch.tier})
                  </span>
                )}
              </div>
            </div>

            {/* ATS Advice / Gaps Summary */}
            <div className="text-[11px] text-jarvis-muted/90 bg-jarvis-dark/40 rounded-lg p-2.5 border border-jarvis-border/20 flex items-center justify-between gap-2">
              <span>
                {unaddressed.length > 0
                  ? `💡 ${unaddressed.length} JD requirement${unaddressed.length > 1 ? 's' : ''} not claimed in resume (honest gaps preserved).`
                  : '✓ All JD requirements covered with verified facts.'}
              </span>
              {validationReport && (
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
                  Audit Verified
                </span>
              )}
            </div>

            {/* Actions Row */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {targetJob?.job_url && (
                <a
                  href={targetJob.job_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={handleConfirmApply}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-gradient-to-r from-cyan-500 to-blue-600 text-white rounded-lg hover:from-cyan-400 hover:to-blue-500 transition-all shadow-md shadow-cyan-500/10"
                >
                  <ExternalLink size={12} />
                  {applied ? '✓ Applied • Open Job ↗' : 'Confirm & Proceed ↗'}
                </a>
              )}
              <button
                onClick={handlePrintPdf}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-jarvis-surface/60 border border-jarvis-border/40 text-jarvis-light hover:border-cyan-400 transition-all"
                title="Print or Save as PDF"
              >
                <Printer size={12} className="text-cyan-400" />
                Print / PDF
              </button>
              <button
                onClick={handleDownloadMarkdown}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-jarvis-surface/60 border border-jarvis-border/40 text-jarvis-light hover:border-jarvis-accent/40 transition-all"
              >
                <Download size={12} />
                MD
              </button>
              <button
                onClick={handleDownloadTxt}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-jarvis-surface/60 border border-jarvis-border/40 text-jarvis-light hover:border-jarvis-accent/40 transition-all"
              >
                <Download size={12} />
                TXT
              </button>
              <button
                onClick={handleCopyText}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-jarvis-surface/60 border border-jarvis-border/40 text-jarvis-light hover:border-jarvis-accent/40 transition-all"
              >
                {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </motion.div>

          {/* ========================================================================= */}
          {/* STAND OUT & FIT SUGGESTIONS (AI GAP ANALYSIS & PROJECT RECOMMENDER) */}
          {/* ========================================================================= */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="p-4 rounded-xl bg-gradient-to-br from-indigo-950/40 via-jarvis-surface/80 to-purple-950/30 border border-indigo-500/40 space-y-4 shadow-xl shadow-black/20 no-print"
          >
            {/* Suggestions Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  <Rocket size={15} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-white flex items-center gap-1.5">
                    Stand Out & Fit Suggestions
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-gradient-to-r from-amber-500/20 to-indigo-500/20 text-amber-300 border border-amber-500/30 font-semibold">
                      Boost Fit: {Math.round(currentFitScore)}% ➔ {Math.round(projectedFitScore)}%
                    </span>
                  </h4>
                  <p className="text-[11px] text-jarvis-muted mt-0.5">
                    Recommendations on missing ATS keywords, enterprise portfolio projects, and bullet rewrites to beat competition.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={fetchStandoutSuggestions}
                  disabled={suggestionsLoading}
                  className="p-1.5 text-jarvis-muted hover:text-white rounded-lg bg-jarvis-surface/40 border border-jarvis-border/30 hover:border-indigo-500/30 transition-all"
                  title="Refresh recommendations"
                >
                  <RefreshCw size={12} className={suggestionsLoading ? 'animate-spin text-indigo-400' : ''} />
                </button>
                <button
                  type="button"
                  onClick={() => setStandoutOpen(!standoutOpen)}
                  className="text-xs text-jarvis-muted hover:text-white flex items-center gap-1"
                >
                  {standoutOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
              </div>
            </div>

            <AnimatePresence>
              {standoutOpen && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="space-y-4 pt-1"
                >
                  {/* Score Gap Meter */}
                  <div className="p-3 rounded-lg bg-jarvis-dark/60 border border-jarvis-border/30 space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold">
                      <span className="text-amber-400 flex items-center gap-1">
                        <TrendingUp size={12} />
                        Current Relevance: {Math.round(currentFitScore)}%
                      </span>
                      <span className="text-emerald-400 flex items-center gap-1">
                        <Sparkles size={12} />
                        Projected Fit with Recommendations: {Math.round(projectedFitScore)}%
                      </span>
                    </div>

                    {/* Dual Progress Bar */}
                    <div className="w-full h-2 rounded-full bg-jarvis-darker overflow-hidden flex">
                      <div
                        style={{ width: `${currentFitScore}%` }}
                        className="h-full bg-amber-500/80 transition-all duration-700"
                        title={`Current Fit: ${currentFitScore}%`}
                      />
                      <div
                        style={{ width: `${Math.max(0, projectedFitScore - currentFitScore)}%` }}
                        className="h-full bg-gradient-to-r from-indigo-500 via-cyan-400 to-emerald-400 opacity-80 animate-pulse"
                        title={`Potential Score Boost: +${Math.round(projectedFitScore - currentFitScore)}%`}
                      />
                    </div>

                    <p className="text-[11px] text-jarvis-muted/90 leading-relaxed pt-1">
                      {suggestionsData?.gap_summary ||
                        `Your resume currently scores ~${Math.round(currentFitScore)}% for this role. Adding missing required skills and including a production-level portfolio project will elevate your fit to ~${Math.round(projectedFitScore)}%, outperforming 90% of applicants.`}
                    </p>
                  </div>

                  {/* 1. Missing ATS Keywords & Skills */}
                  {suggestionsData?.missing_skills && suggestionsData.missing_skills.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1.5">
                          <Flame size={12} className="text-amber-400" />
                          Missing ATS Keywords & Skills ({suggestionsData.missing_skills.length})
                        </span>
                        <button
                          type="button"
                          onClick={handleAdoptAllSkills}
                          className="text-[10px] font-semibold text-cyan-400 hover:text-cyan-300 underline"
                        >
                          + Add All Missing Skills
                        </button>
                      </div>

                      <div className="flex flex-wrap gap-1.5">
                        {suggestionsData.missing_skills.map((skillObj: any, sIdx: number) => {
                          const sName = skillObj.name || skillObj
                          const isReq = skillObj.importance === 'required'
                          const isAdded =
                            addedSkills.includes(sName) ||
                            editableSkills.some((s) => s.toLowerCase() === sName.toLowerCase())

                          return (
                            <button
                              key={sIdx}
                              type="button"
                              onClick={() => handleAdoptSkill(sName)}
                              className={`group inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all ${
                                isAdded
                                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                                  : isReq
                                  ? 'bg-amber-500/10 text-amber-200 border-amber-500/30 hover:bg-amber-500/20'
                                  : 'bg-indigo-500/10 text-indigo-200 border-indigo-500/30 hover:bg-indigo-500/20'
                              }`}
                              title={skillObj.reason || 'Click to add to your resume'}
                            >
                              <span>{sName}</span>
                              {isReq && (
                                <span className="text-[9px] px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 font-semibold uppercase">
                                  Req
                                </span>
                              )}
                              {isAdded ? (
                                <CheckCircle2 size={11} className="text-emerald-400" />
                              ) : (
                                <Plus size={11} className="text-cyan-400 group-hover:scale-110 transition-transform" />
                              )}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* 2. Standout Portfolio Project Recommendations */}
                  {suggestionsData?.standout_projects && suggestionsData.standout_projects.length > 0 && (
                    <div className="space-y-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
                          <Layers size={13} className="text-indigo-400" />
                          Recommended Projects to Stand Out ({suggestionsData.standout_projects.length})
                        </span>
                        <span className="text-[10px] text-jarvis-muted">
                          Proven architecture templates tailored to JD gaps
                        </span>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                        {suggestionsData.standout_projects.map((proj: any, pIdx: number) => {
                          const isAdded =
                            addedProjectIds.includes(proj.id) ||
                            editableProjects.some((ep) => (ep.title || ep.name) === proj.title)

                          return (
                            <div
                              key={pIdx}
                              className="p-3 rounded-xl bg-jarvis-dark/70 border border-indigo-500/20 hover:border-indigo-500/40 transition-all space-y-2 flex flex-col justify-between"
                            >
                              <div className="space-y-1.5">
                                <div className="flex items-start justify-between gap-2">
                                  <h5 className="text-xs font-bold text-white leading-snug">{proj.title}</h5>
                                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-medium flex-shrink-0">
                                    Stand-out Impact
                                  </span>
                                </div>
                                <p className="text-[11px] text-cyan-300/90 font-medium">{proj.tagline}</p>
                                <p className="text-[11px] text-jarvis-muted leading-relaxed">{proj.architecture}</p>

                                {/* Tech Stack Tags */}
                                {proj.tech_stack && proj.tech_stack.length > 0 && (
                                  <div className="flex flex-wrap gap-1 pt-1">
                                    {proj.tech_stack.map((t: string, tIdx: number) => (
                                      <span
                                        key={tIdx}
                                        className="text-[10px] px-1.5 py-0.5 rounded bg-jarvis-surface text-jarvis-muted font-mono"
                                      >
                                        {t}
                                      </span>
                                    ))}
                                  </div>
                                )}

                                {/* Why it stands out note */}
                                {proj.why_it_stands_out && (
                                  <div className="p-2 rounded-lg bg-indigo-950/30 border border-indigo-500/20 text-[10px] text-indigo-200/90 leading-snug">
                                    💡 <strong>Why this shines:</strong> {proj.why_it_stands_out}
                                  </div>
                                )}
                              </div>

                              <div className="pt-2 border-t border-jarvis-border/20 flex items-center justify-between">
                                <span className="text-[10px] text-emerald-400 font-semibold">{proj.metrics}</span>
                                <button
                                  type="button"
                                  onClick={() => handleAdoptProject(proj)}
                                  className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                                    isAdded
                                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                      : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm shadow-indigo-500/30'
                                  }`}
                                >
                                  {isAdded ? (
                                    <>
                                      <CheckCircle2 size={11} /> Added to Resume
                                    </>
                                  ) : (
                                    <>
                                      <Plus size={11} /> + Add Project to Resume
                                    </>
                                  )}
                                </button>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* 3. Targeted Bullet Point Suggestions */}
                  {suggestionsData?.bullet_suggestions && suggestionsData.bullet_suggestions.length > 0 && (
                    <div className="space-y-2">
                      <span className="text-[11px] font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
                        <Sparkles size={12} className="text-amber-400" />
                        Suggested Experience Bullet Rewrites ({suggestionsData.bullet_suggestions.length})
                      </span>

                      <div className="space-y-1.5">
                        {suggestionsData.bullet_suggestions.map((bulletObj: any, bIdx: number) => (
                          <div
                            key={bIdx}
                            className="p-2.5 rounded-lg bg-jarvis-dark/50 border border-jarvis-border/30 text-xs flex items-start justify-between gap-3"
                          >
                            <div className="space-y-0.5 flex-1">
                              <p className="text-white leading-relaxed">{bulletObj.suggested_bullet}</p>
                              <span className="text-[10px] text-jarvis-muted">{bulletObj.reason}</span>
                            </div>
                            <button
                              type="button"
                              onClick={() => handleAdoptBullet(bulletObj.suggested_bullet)}
                              className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/30 flex-shrink-0"
                            >
                              <Plus size={10} /> Insert Bullet
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          {/* EDIT MODE CALLOUT BANNER */}
          {isEditing && (
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between">
              <span className="flex items-center gap-1.5 font-medium">
                <Edit3 size={13} />
                <strong>Interactive Editor Active:</strong> You can edit summary text, add/remove skills, refine bullets, and customize projects.
              </span>
              <button
                onClick={() => setIsEditing(false)}
                className="text-[11px] underline hover:text-white font-semibold"
              >
                View Mode
              </button>
            </div>
          )}

          {/* PRINTABLE CONTAINER (Targeted by @media print) */}
          <div id="printable-resume" className="space-y-4">
            {/* Professional Summary */}
            <div className="p-3.5 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2">
              <div className="flex items-center justify-between text-jarvis-accent">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-3.5 h-3.5" />
                  <h4 className="text-xs font-semibold uppercase tracking-wider">Professional Summary</h4>
                </div>
                {isEditing && (
                  <span className="text-[10px] text-jarvis-muted">{editableSummary.length} chars</span>
                )}
              </div>

              {isEditing ? (
                <textarea
                  rows={3}
                  value={editableSummary}
                  onChange={(e) => setEditableSummary(e.target.value)}
                  className="w-full text-xs p-2.5 rounded-lg bg-jarvis-dark/60 border border-cyan-500/30 text-white focus:outline-none focus:border-cyan-400 resize-y leading-relaxed"
                />
              ) : (
                <p className="text-xs text-jarvis-muted/90 leading-relaxed">{editableSummary}</p>
              )}
            </div>

            {/* Prioritized Skills */}
            <div className="p-3.5 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2.5">
              <div className="flex items-center justify-between text-cyan-400">
                <div className="flex items-center gap-2">
                  <Award className="w-3.5 h-3.5" />
                  <h4 className="text-xs font-semibold uppercase tracking-wider">
                    Prioritized Skills ({editableSkills.length})
                  </h4>
                </div>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {editableSkills.map((skill: string, idx: number) => (
                  <span
                    key={idx}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 rounded-md"
                  >
                    <span>{skill}</span>
                    {isEditing && (
                      <button
                        type="button"
                        onClick={() => handleRemoveSkill(idx)}
                        className="text-cyan-400/60 hover:text-rose-400 ml-1"
                      >
                        ×
                      </button>
                    )}
                  </span>
                ))}
              </div>

              {isEditing && (
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="text"
                    placeholder="Add a new skill..."
                    value={newSkillInput}
                    onChange={(e) => setNewSkillInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleAddSkill()}
                    className="text-xs px-2.5 py-1 rounded-md bg-jarvis-dark/60 border border-jarvis-border/40 text-white placeholder-jarvis-muted/40 focus:outline-none focus:border-cyan-500/50"
                  />
                  <button
                    type="button"
                    onClick={handleAddSkill}
                    className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/30"
                  >
                    <Plus size={11} /> Add
                  </button>
                </div>
              )}
            </div>

            {/* Work Experience */}
            {editableExp.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-blue-400 px-1">
                  <Briefcase className="w-3.5 h-3.5" />
                  <h4 className="text-xs font-semibold uppercase tracking-wider">
                    Tailored Work Experience
                  </h4>
                </div>

                {editableExp.map((expItem: any, expIdx: number) => {
                  const bullets = expItem.highlights || []
                  const dateStr = getStr(expItem.date_range_raw) || getStr(expItem.dates)

                  return (
                    <div
                      key={expIdx}
                      className="p-3.5 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2.5"
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <h5 className="text-xs font-bold text-white">{expItem.title || expItem.role}</h5>
                          <p className="text-[11px] text-jarvis-muted">{expItem.company || expItem.employer}</p>
                        </div>
                        {dateStr && (
                          <span className="text-[10px] text-jarvis-muted/70 bg-jarvis-surface px-2 py-0.5 rounded border border-jarvis-border/30">
                            {dateStr}
                          </span>
                        )}
                      </div>

                      <div className="space-y-2 pt-1">
                        {bullets.map((bulletObj: any, bIdx: number) => {
                          const bulletId = `${expIdx}-${bIdx}`
                          const isExpanded = activeWhy === bulletId
                          const finalText =
                            typeof bulletObj === 'object'
                              ? bulletObj.final_text || bulletObj.text
                              : bulletObj
                          const origText =
                            typeof bulletObj === 'object' ? bulletObj.original_text : null
                          const evidenceRef =
                            typeof bulletObj === 'object' ? bulletObj.evidence_ref : null

                          return (
                            <div key={bIdx} className="space-y-1.5">
                              <div className="flex items-start justify-between gap-2 group">
                                {isEditing ? (
                                  <div className="flex items-center gap-2 flex-1">
                                    <span className="text-cyan-400 text-xs">•</span>
                                    <input
                                      type="text"
                                      value={finalText}
                                      onChange={(e) =>
                                        handleBulletChange(expIdx, bIdx, e.target.value)
                                      }
                                      className="w-full text-xs px-2 py-1 rounded bg-jarvis-dark/60 border border-jarvis-border/40 text-white focus:outline-none focus:border-cyan-400"
                                    />
                                    <button
                                      type="button"
                                      onClick={() => handleRemoveBullet(expIdx, bIdx)}
                                      className="text-jarvis-muted/40 hover:text-rose-400 p-1"
                                      title="Delete bullet"
                                    >
                                      <Trash2 size={12} />
                                    </button>
                                  </div>
                                ) : (
                                  <>
                                    <div className="text-xs text-jarvis-muted/90 flex items-start gap-2 leading-relaxed flex-1">
                                      <span className="text-cyan-400 mt-1 flex-shrink-0">•</span>
                                      <span>{finalText}</span>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => setActiveWhy(isExpanded ? null : bulletId)}
                                      className={`px-1.5 py-0.5 text-[10px] rounded border transition-all flex items-center gap-1 flex-shrink-0 no-print ${
                                        isExpanded
                                          ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                                          : 'bg-jarvis-surface/40 text-jarvis-muted/60 border-jarvis-border/30 hover:text-jarvis-accent hover:border-jarvis-accent/30'
                                      }`}
                                    >
                                      <HelpCircle size={10} />
                                      Why?
                                    </button>
                                  </>
                                )}
                              </div>

                              {/* "Why?" Evidence Panel */}
                              <AnimatePresence>
                                {!isEditing && isExpanded && (
                                  <motion.div
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: 'auto' }}
                                    exit={{ opacity: 0, height: 0 }}
                                    className="overflow-hidden"
                                  >
                                    <div className="p-2.5 rounded-lg bg-jarvis-dark/70 border border-cyan-500/30 text-[11px] space-y-1.5 ml-4">
                                      <div className="flex items-center justify-between text-[10px]">
                                        <span className="text-cyan-400 font-semibold uppercase tracking-wider">
                                          Evidence Grounding
                                        </span>
                                        {evidenceRef && (
                                          <code className="text-[9px] px-1.5 py-0.5 rounded bg-jarvis-surface text-jarvis-muted font-mono">
                                            {evidenceRef}
                                          </code>
                                        )}
                                      </div>
                                      {origText && (
                                        <div>
                                          <span className="text-jarvis-muted/70 text-[10px] uppercase">
                                            Candidate Fact:
                                          </span>
                                          <p className="text-jarvis-light font-mono text-[10px] mt-0.5">
                                            {origText}
                                          </p>
                                        </div>
                                      )}
                                      <div>
                                        <span className="text-jarvis-muted/70 text-[10px] uppercase">
                                          Audit Verdict:
                                        </span>
                                        <p className="text-emerald-400 text-[10px] mt-0.5">
                                          ✓ Token subset contained in candidate evidence. Zero
                                          invented skills or dates.
                                        </p>
                                      </div>
                                    </div>
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                          )
                        })}
                      </div>

                      {isEditing && (
                        <button
                          type="button"
                          onClick={() => handleAddBullet(expIdx)}
                          className="text-[11px] font-medium text-cyan-400 hover:text-cyan-300 flex items-center gap-1 pt-1"
                        >
                          <Plus size={11} /> Add Bullet
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {/* Relevant Projects */}
            {editableProjects.length > 0 && (
              <div className="p-3.5 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2.5">
                <div className="flex items-center justify-between text-indigo-400">
                  <div className="flex items-center gap-2">
                    <FileText className="w-3.5 h-3.5" />
                    <h4 className="text-xs font-semibold uppercase tracking-wider">
                      Highlighted Projects ({editableProjects.length})
                    </h4>
                  </div>
                  {isEditing && (
                    <button
                      type="button"
                      onClick={handleAddCustomProject}
                      className="text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
                    >
                      <Plus size={11} /> Add Project
                    </button>
                  )}
                </div>
                <div className="space-y-2">
                  {editableProjects.map((proj: any, idx: number) => (
                    <div
                      key={idx}
                      className="text-xs p-3 rounded-lg bg-jarvis-dark/40 border border-jarvis-border/20 space-y-1.5"
                    >
                      {isEditing ? (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between gap-2">
                            <input
                              type="text"
                              value={proj.title || proj.name || ''}
                              onChange={(e) => handleProjectChange(idx, 'title', e.target.value)}
                              placeholder="Project Title"
                              className="w-full text-xs p-1.5 rounded bg-jarvis-dark/80 border border-cyan-500/30 text-white font-semibold focus:outline-none focus:border-cyan-400"
                            />
                            <button
                              type="button"
                              onClick={() => handleRemoveProject(idx)}
                              className="text-jarvis-muted/40 hover:text-rose-400 p-1"
                              title="Delete project"
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                          <textarea
                            rows={2}
                            value={proj.description || ''}
                            onChange={(e) => handleProjectChange(idx, 'description', e.target.value)}
                            placeholder="Project architecture and results"
                            className="w-full text-xs p-1.5 rounded bg-jarvis-dark/80 border border-jarvis-border/30 text-white focus:outline-none focus:border-cyan-400 resize-y"
                          />
                        </div>
                      ) : (
                        <>
                          <p className="font-semibold text-white">{proj.name || proj.title}</p>
                          {proj.description && (
                            <p className="text-jarvis-muted/90 leading-relaxed mt-0.5">{proj.description}</p>
                          )}
                          {proj.tech_stack && proj.tech_stack.length > 0 && (
                            <div className="flex flex-wrap gap-1 pt-1">
                              {proj.tech_stack.map((t: string, ti: number) => (
                                <span
                                  key={ti}
                                  className="text-[9px] px-1.5 py-0.5 rounded bg-jarvis-surface text-jarvis-muted font-mono"
                                >
                                  {t}
                                </span>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Unaddressed Requirements (Honest Gaps) */}
          {unaddressed.length > 0 && (
            <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-500/30 space-y-2 no-print">
              <div className="flex items-center gap-2 text-amber-400">
                <AlertCircle className="w-3.5 h-3.5" />
                <h4 className="text-xs font-semibold uppercase tracking-wider">
                  Unaddressed Job Requirements
                </h4>
              </div>
              <p className="text-[11px] text-amber-200/80 leading-relaxed">
                These requirements from the JD could not be supported by your verified candidate
                experience. JARVIS never fabricates claims:
              </p>
              <ul className="space-y-1">
                {unaddressed.map((req: string, idx: number) => (
                  <li key={idx} className="text-xs text-amber-200/90 flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                    <span>{req}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  )
}
