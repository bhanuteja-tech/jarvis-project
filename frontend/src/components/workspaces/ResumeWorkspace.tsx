import { useRef } from 'react'
import { motion } from 'framer-motion'
import { Upload, FileText, User, Briefcase, GraduationCap, Award, CheckCircle2, ShieldCheck, Clock } from 'lucide-react'
import { useStore } from '../../store/useStore'

function safeStr(val: any, fallback = ''): string {
  if (val === null || val === undefined) return fallback
  if (typeof val === 'string') return val
  if (typeof val === 'number' || typeof val === 'boolean') return String(val)
  if (typeof val === 'object') {
    if (typeof val.full_name === 'string') return val.full_name
    if (typeof val.name === 'string') return val.name
    if (typeof val.title === 'string') return val.title
    if (typeof val.text === 'string') return val.text
    if (typeof val.degree === 'string') return val.degree
    if (typeof val.school === 'string') return val.school
    if (typeof val.value === 'string') return val.value
  }
  return fallback
}

interface ResumeWorkspaceProps {
  onResumeUpload?: (file: File) => void
}

export function ResumeWorkspace({ onResumeUpload }: ResumeWorkspaceProps) {
  const { candidateProfile, resumeFileName, setResumeFileName } = useStore()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setResumeFileName(file.name)
    if (onResumeUpload) {
      onResumeUpload(file)
    }
  }

  const profileData = candidateProfile?.profile || candidateProfile || null
  const parsedStatus = safeStr(candidateProfile?.status) || (profileData ? 'PARSED' : '')

  // Extract candidate name safely from identity or contact
  const candidateName =
    (typeof profileData?.identity === 'object' && safeStr(profileData?.identity?.full_name)) ||
    (typeof profileData?.contact === 'object' && safeStr(profileData?.contact?.name)) ||
    'Candidate Profile'

  // Extract summary safely
  const summaryText = safeStr((profileData as any)?.summary?.text || (profileData as any)?.summary)

  // Extract skills safely
  const rawSkills = profileData?.skills
  let skillItems: string[] = []
  if (Array.isArray(rawSkills)) {
    skillItems = rawSkills.map((s: any) => safeStr(s?.name || s)).filter(Boolean)
  } else if (rawSkills && Array.isArray((rawSkills as any).items)) {
    skillItems = (rawSkills as any).items.map((s: any) => safeStr(s?.name || s)).filter(Boolean)
  }

  // Extract experience safely
  const rawExp = profileData?.experience
  let expItems: any[] = []
  let totalYears: number | null = null
  if (Array.isArray(rawExp)) {
    expItems = rawExp
  } else if (rawExp && Array.isArray((rawExp as any).items)) {
    expItems = (rawExp as any).items
    totalYears = (rawExp as any).total_years ?? null
  }

  // Extract education safely
  const rawEdu = profileData?.education
  let eduItems: any[] = []
  if (Array.isArray(rawEdu)) {
    eduItems = rawEdu
  } else if (rawEdu && Array.isArray((rawEdu as any).items)) {
    eduItems = (rawEdu as any).items
  }

  // Extract certifications safely
  const rawCerts = profileData?.certifications
  let certItems: any[] = []
  if (Array.isArray(rawCerts)) {
    certItems = rawCerts
  } else if (rawCerts && Array.isArray((rawCerts as any).items)) {
    certItems = (rawCerts as any).items
  }

  // Extract projects safely
  const rawProjects = profileData?.projects
  let projectItems: any[] = []
  if (Array.isArray(rawProjects)) {
    projectItems = rawProjects
  } else if (rawProjects && Array.isArray((rawProjects as any).items)) {
    projectItems = (rawProjects as any).items
  }

  // Extract preferences safely
  const prefs = profileData?.preferences || {}
  const prefLocations = Array.isArray(prefs.locations) ? prefs.locations.map((l: any) => safeStr(l)).filter(Boolean) : []
  const prefRemote = prefs.remote ?? null

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 scrollbar-hide">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileUpload}
        accept=".pdf,.docx,.txt,.md"
        className="hidden"
      />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-jarvis-accent" />
          <h3 className="text-sm font-semibold text-white">Parsed Profile</h3>
        </div>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-jarvis-accent text-jarvis-dark rounded-lg hover:bg-jarvis-accent/90 transition-all shadow-lg shadow-jarvis-accent/10"
        >
          <Upload size={12} />
          {candidateProfile ? 'Re-upload' : 'Upload Resume'}
        </button>
      </div>

      {!candidateProfile ? (
        <div className="flex flex-col items-center justify-center py-12 px-4 text-center border-2 border-dashed border-jarvis-border/40 rounded-2xl bg-jarvis-surface/20">
          <div className="w-12 h-12 rounded-full bg-jarvis-accent/10 flex items-center justify-center mb-3">
            <Upload className="w-6 h-6 text-jarvis-accent" />
          </div>
          <h4 className="text-sm font-semibold text-white mb-1">No Resume Processed</h4>
          <p className="text-xs text-jarvis-muted/70 max-w-xs mb-4">
            Upload your resume (PDF, DOCX, TXT) to build a deterministic candidate profile with strict PII quarantining.
          </p>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-4 py-2 text-xs font-semibold bg-jarvis-accent text-jarvis-dark rounded-lg hover:bg-jarvis-accent/90 transition-all"
          >
            Select File
          </button>
        </div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          {/* Header Card */}
          <div className="p-4 rounded-xl bg-gradient-to-r from-blue-950/40 via-jarvis-surface/60 to-transparent border border-jarvis-border/50">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center font-bold text-white shadow-md">
                <User size={20} />
              </div>
              <div>
                <h4 className="text-sm font-bold text-white">{candidateName}</h4>
                <div className="flex items-center gap-2 text-[11px] text-jarvis-muted mt-0.5">
                  <span className="flex items-center gap-1 text-green-400 font-medium">
                    <ShieldCheck size={12} /> PII Quarantined
                  </span>
                  {parsedStatus && (
                    <span className="px-1.5 py-0.5 text-[10px] bg-blue-500/20 text-blue-300 rounded font-semibold uppercase">
                      {parsedStatus}
                    </span>
                  )}
                  {resumeFileName && <span>• {resumeFileName}</span>}
                </div>
              </div>
            </div>
            {totalYears !== null && (
              <div className="mt-3 pt-2 border-t border-jarvis-border/30 flex items-center gap-2 text-xs text-jarvis-accent">
                <Clock size={14} />
                <span>Total Verified Experience: <strong>{totalYears} years</strong></span>
              </div>
            )}
          </div>

          {/* Professional Summary */}
          {summaryText && (
            <div className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-jarvis-accent">Professional Summary</h4>
              <p className="text-xs text-jarvis-muted/90 leading-relaxed">{summaryText}</p>
            </div>
          )}

          {/* Skills Taxonomy */}
          {skillItems.length > 0 && (
            <div className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2.5">
              <div className="flex items-center gap-2 text-cyan-400">
                <CheckCircle2 size={16} />
                <h4 className="text-xs font-semibold uppercase tracking-wider">Extracted Taxonomy Skills ({skillItems.length})</h4>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {skillItems.map((skill, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 text-xs bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 rounded-md font-medium"
                  >
                    {safeStr(skill)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Work Experience */}
          {expItems.length > 0 && (
            <div className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-3">
              <div className="flex items-center gap-2 text-blue-400">
                <Briefcase size={16} />
                <h4 className="text-xs font-semibold uppercase tracking-wider">Work Experience</h4>
              </div>
              <div className="space-y-3">
                {expItems.filter(Boolean).map((exp: any, idx: number) => {
                  const isObj = typeof exp === 'object' && exp !== null
                  const title = isObj ? (safeStr(exp.title) || safeStr(exp.role) || safeStr(exp.position) || 'Position') : safeStr(exp, 'Position')
                  const company = isObj ? (safeStr(exp.company) || safeStr(exp.employer)) : ''
                  const dates = isObj ? (safeStr(exp.dates) || safeStr(exp.start_raw ? `${exp.start_raw} - ${exp.end_raw || 'Present'}` : '')) : ''
                  const desc = isObj ? (safeStr(exp.description) || safeStr(exp.summary)) : ''
                  const highlights: string[] = isObj && Array.isArray(exp.highlights)
                    ? exp.highlights.map((h: any) => safeStr(h?.final_text || h?.original_text || h)).filter(Boolean)
                    : []

                  return (
                    <div key={idx} className="p-3 rounded-lg bg-jarvis-dark/40 border border-jarvis-border/30 space-y-1.5">
                      <div className="flex items-start justify-between">
                        <h5 className="text-xs font-bold text-white">{title}</h5>
                        {dates && (
                          <span className="text-[10px] text-jarvis-muted bg-jarvis-surface px-2 py-0.5 rounded border border-jarvis-border/30">
                            {dates}
                          </span>
                        )}
                      </div>
                      {company && <p className="text-xs text-jarvis-accent/80 font-medium">{company}</p>}
                      {desc && <p className="text-xs text-jarvis-muted/80 leading-relaxed pt-1">{desc}</p>}
                      {highlights.length > 0 && (
                        <ul className="space-y-1 pt-1">
                          {highlights.map((hText: string, hIdx: number) => (
                            <li key={hIdx} className="text-xs text-jarvis-muted/90 flex items-start gap-1.5 leading-relaxed">
                              <span className="text-jarvis-accent flex-shrink-0">•</span>
                              <span>{hText}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Preferences */}
          {(prefLocations.length > 0 || prefRemote !== null) && (
            <div className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Candidate Preferences</h4>
              <div className="flex flex-wrap gap-2 text-xs text-jarvis-muted">
                {prefLocations.length > 0 && (
                  <span className="px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 rounded-md">
                    Locations: {prefLocations.join(', ')}
                  </span>
                )}
                {prefRemote !== null && (
                  <span className="px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 rounded-md">
                    Remote: {prefRemote ? 'Yes' : 'No Preference'}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Education */}
          {eduItems.length > 0 && (
            <div className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2.5">
              <div className="flex items-center gap-2 text-indigo-400">
                <GraduationCap size={16} />
                <h4 className="text-xs font-semibold uppercase tracking-wider">Education</h4>
              </div>
              <div className="space-y-2">
                {eduItems.filter(Boolean).map((edu: any, idx: number) => {
                  const isObj = typeof edu === 'object' && edu !== null
                  const degree = isObj ? (safeStr(edu.degree) || safeStr(edu.title) || 'Degree') : safeStr(edu, 'Degree')
                  const school = isObj ? (safeStr(edu.school) || safeStr(edu.institution)) : ''
                  return (
                    <div key={idx} className="text-xs">
                      <p className="font-bold text-white">{degree}</p>
                      {school && <p className="text-jarvis-muted">{school}</p>}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Certifications */}
          {certItems.length > 0 && (
            <div className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2.5">
              <div className="flex items-center gap-2 text-emerald-400">
                <Award size={16} />
                <h4 className="text-xs font-semibold uppercase tracking-wider">Certifications ({certItems.length})</h4>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {certItems.filter(Boolean).map((cert: any, idx: number) => {
                  const certName = safeStr(cert?.name || cert?.title || cert, 'Certification')
                  return (
                    <span
                      key={idx}
                      className="px-2.5 py-1 text-xs bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-md font-medium"
                    >
                      {certName}
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          {/* Projects */}
          {projectItems.length > 0 && (
            <div className="p-4 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40 space-y-2.5">
              <div className="flex items-center gap-2 text-purple-400">
                <FileText size={16} />
                <h4 className="text-xs font-semibold uppercase tracking-wider">Projects ({projectItems.length})</h4>
              </div>
              <div className="space-y-2.5">
                {projectItems.filter(Boolean).map((proj: any, idx: number) => {
                  const isObj = typeof proj === 'object' && proj !== null
                  const name = isObj ? (safeStr(proj.name) || safeStr(proj.title) || 'Project') : safeStr(proj, 'Project')
                  const desc = isObj ? safeStr(proj.description) : ''
                  const techs = isObj && Array.isArray(proj.technologies) ? proj.technologies.map((t: any) => safeStr(t)).filter(Boolean) : []
                  return (
                    <div key={idx} className="p-3 rounded-lg bg-jarvis-dark/40 border border-jarvis-border/30 space-y-1">
                      <h5 className="text-xs font-bold text-white">{name}</h5>
                      {desc && <p className="text-xs text-jarvis-muted/80 leading-relaxed">{desc}</p>}
                      {techs.length > 0 && (
                        <div className="flex flex-wrap gap-1 pt-1">
                          {techs.map((tech: string, tIdx: number) => (
                            <span key={tIdx} className="text-[10px] px-1.5 py-0.5 bg-purple-500/10 border border-purple-500/20 text-purple-300 rounded">
                              {tech}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </div>
  )
}
