import { useState, useEffect, useRef } from 'react'
import {
  Sparkles,
  Printer,
  Download,
  Copy,
  Check,
  Plus,
  Trash2,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Send,
  Bot,
  User,
  ArrowLeft,
  Flame,
  Layers,
  RefreshCw,
  FileText,
  RotateCcw,
  Edit3,
  AlignLeft,
  ShieldCheck,
  ChevronDown,
  BookOpen,
} from 'lucide-react'
import { useStore } from '../../store/useStore'
import { AtsToolPanel } from './AtsToolPanel'
import {
  SAMPLE_RESUMES,
  ResumeData,
  parseUploadedResumeData,
  EducationEntry,
  ProjectEntry,
  CategorizedSkills,
  ExperienceEntry,
} from './sampleResumes'
import { AiSectionRewriterModal } from './AiSectionRewriterModal'

export function DocumentStudioWorkspace() {
  const {
    tailoredResume,
    candidateProfile,
    resumeFileName,
    jobs,
    matchResults,
    sessionId,
    setActiveWorkspace,
    selectedJobIndex,
  } = useStore()

  // Target Job Context
  const targetJobKey = tailoredResume?.resume?.target_job_key || ''
  const targetJob =
    (selectedJobIndex !== null && jobs[selectedJobIndex]) ||
    jobs.find((j) => j.job_key === targetJobKey) ||
    (jobs.length > 0 ? jobs[0] : null)
  const targetMatch = matchResults.find(
    (m) => m.job_key === (targetJob?.job_key || targetJobKey) || m.job_index === targetJob?.__index
  )

  // Document Source Switcher: 'uploaded' vs 'tailored'
  const [docSource, setDocSource] = useState<'uploaded' | 'tailored'>('uploaded')

  // Studio Display States
  const [zoom, setZoom] = useState(100)
  const [viewMode, setViewMode] = useState<'sheet' | 'raw'>('sheet')
  const [activeSidebarTab, setActiveSidebarTab] = useState<'copilot' | 'ats' | 'suggestions'>('copilot')
  const [templateTheme, setTemplateTheme] = useState<
    'modern' | 'executive' | 'tech' | 'classic-ivy' | 'compact'
  >('modern')
  const [activeSampleKey, setActiveSampleKey] = useState<string>('sample-lohith')
  const [sampleDropdownOpen, setSampleDropdownOpen] = useState(false)
  const [marginSpacing, setMarginSpacing] = useState<'compact' | 'normal' | 'spacious'>('normal')
  const [copied, setCopied] = useState(false)

  // =========================================================================
  // INTERACTIVE AI SECTION REWRITER STATE
  // =========================================================================
  const [aiModal, setAiModal] = useState<{
    isOpen: boolean
    sectionId: 'header' | 'summary' | 'education' | 'projects' | 'skills' | 'certifications' | 'experience'
    sectionTitle: string
    currentContent: any
  }>({
    isOpen: false,
    sectionId: 'summary',
    sectionTitle: 'Summary',
    currentContent: '',
  })

  const openAiRewriter = (
    sectionId: 'header' | 'summary' | 'education' | 'projects' | 'skills' | 'certifications' | 'experience',
    sectionTitle: string,
    currentContent: any
  ) => {
    setAiModal({
      isOpen: true,
      sectionId,
      sectionTitle,
      currentContent,
    })
  }

  // =========================================================================
  // DOCUMENT STATE - Initialized faithfully to uploaded/sample resume
  // =========================================================================
  const initialData = SAMPLE_RESUMES['sample-lohith']
  const [fullName, setFullName] = useState(initialData.fullName)
  const [contactLocation, setContactLocation] = useState(initialData.contactLocation)
  const [contactPhone, setContactPhone] = useState(initialData.contactPhone)
  const [contactEmail, setContactEmail] = useState(initialData.contactEmail)
  const [linkedinUrl, setLinkedinUrl] = useState(initialData.linkedinUrl)
  const [githubUrl, setGithubUrl] = useState(initialData.githubUrl)
  const [portfolioUrl, setPortfolioUrl] = useState(initialData.portfolioUrl)
  const [summary, setSummary] = useState(initialData.summary)
  const [education, setEducation] = useState<EducationEntry[]>(initialData.education)
  const [projects, setProjects] = useState<ProjectEntry[]>(initialData.projects)
  const [skillGroups, setSkillGroups] = useState<CategorizedSkills[]>(initialData.skillGroups)
  const [certifications, setCertifications] = useState<string[]>(initialData.certifications)
  const [experience, setExperience] = useState<ExperienceEntry[]>(initialData.experience)
  const [rawTextContent, setRawTextContent] = useState('')

  // Copilot Chat State
  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState<
    Array<{
      id: string
      sender: 'user' | 'assistant'
      text: string
      suggestions?: Array<{ label: string; type: string; content: any }>
    }>
  >([])
  const [isCopilotThinking, setIsCopilotThinking] = useState(false)
  const chatBottomRef = useRef<HTMLDivElement>(null)

  // Standout Suggestions Data
  const [suggestionsData, setSuggestionsData] = useState<any>(null)
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)

  // Helper string unwrapper
  const getStr = (val: any): string => {
    if (!val) return ''
    if (typeof val === 'string') return val
    if (typeof val === 'number') return String(val)
    if (typeof val === 'object') {
      return val.display || val.name || val.final_text || val.original_text || val.text || ''
    }
    return ''
  }

  // Apply complete structured resume data
  const applyResumeData = (data: ResumeData) => {
    setFullName(data.fullName)
    setContactLocation(data.contactLocation)
    setContactPhone(data.contactPhone)
    setContactEmail(data.contactEmail)
    setLinkedinUrl(data.linkedinUrl)
    setGithubUrl(data.githubUrl)
    setPortfolioUrl(data.portfolioUrl)
    setSummary(data.summary)
    setEducation(data.education)
    setProjects(data.projects)
    setSkillGroups(data.skillGroups)
    setCertifications(data.certifications)
    setExperience(data.experience)
  }

  // Parse raw text or candidate profile directly into authentic sections
  const loadUploadedProfile = () => {
    if (candidateProfile) {
      const parsed = parseUploadedResumeData(candidateProfile)
      applyResumeData(parsed)
    } else if (resumeFileName && resumeFileName.toLowerCase().includes('lohith')) {
      applyResumeData(SAMPLE_RESUMES['sample-lohith'])
    }
    setDocSource('uploaded')
    setActiveSampleKey('uploaded')
  }

  // Load one of the 5 ATS-friendly sample resumes
  const loadSampleResume = (sampleKey: string) => {
    if (sampleKey === 'uploaded') {
      loadUploadedProfile()
      setSampleDropdownOpen(false)
      return
    }
    const sample = SAMPLE_RESUMES[sampleKey]
    if (sample) {
      applyResumeData(sample)
      setActiveSampleKey(sampleKey)
      setDocSource('uploaded')
      setSampleDropdownOpen(false)
    }
  }

  // Handle section rewrite application from AI Modal
  const handleApplySectionRewrite = (text: string, structured?: any) => {
    const sec = aiModal.sectionId
    if (sec === 'summary') {
      const summaryText = structured?.summary || text
      setSummary(summaryText)
    } else if (sec === 'header') {
      if (structured?.name) setFullName(structured.name)
      if (structured?.phone) setContactPhone(structured.phone)
      if (structured?.email) setContactEmail(structured.email)
      if (structured?.linkedin) setLinkedinUrl(structured.linkedin)
      if (structured?.github) setGithubUrl(structured.github)
      if (structured?.portfolio) setPortfolioUrl(structured.portfolio)
      if (!structured) {
        const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
        if (lines.length > 0) {
          if (!lines[0].includes(':')) setFullName(lines[0])
          lines.slice(1).forEach((l) => {
            if (l.toLowerCase().includes('phone') || l.includes('+')) {
              const m = l.split(/[:|]/).pop()?.trim()
              if (m) setContactPhone(m)
            } else if (l.toLowerCase().includes('email') || l.includes('@')) {
              const m = l.split(/[:|]/).pop()?.trim()
              if (m) setContactEmail(m)
            } else if (l.toLowerCase().includes('linkedin')) {
              const m = l.split(/[:|]/).pop()?.trim()
              if (m) setLinkedinUrl(m)
            } else if (l.toLowerCase().includes('github')) {
              const m = l.split(/[:|]/).pop()?.trim()
              if (m) setGithubUrl(m)
            } else if (l.toLowerCase().includes('portfolio')) {
              const m = l.split(/[:|]/).pop()?.trim()
              if (m) setPortfolioUrl(m)
            }
          })
        }
      }
    } else if (sec === 'education') {
      const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
      if (lines.length > 0 && education.length > 0) {
        setEducation((prev) => {
          const updated = [...prev]
          if (lines[0]) updated[0] = { ...updated[0], degree: lines[0] }
          return updated
        })
      }
    } else if (sec === 'projects') {
      const rawBullets =
        structured?.bullets && Array.isArray(structured.bullets)
          ? structured.bullets
          : text
              .split('\n')
              .map((l) => l.trim())
              .filter((l) => l.startsWith('•') || l.startsWith('-') || l.startsWith('*') || l.length > 10)
              .map((l) => l.replace(/^[•\-*]\s*/, '').trim())
      if (rawBullets.length > 0 && projects.length > 0) {
        setProjects((prev) => {
          const updated = [...prev]
          updated[0] = { ...updated[0], bullets: rawBullets }
          return updated
        })
      }
    } else if (sec === 'skills') {
      const lines = text.split('\n').filter((l) => l.includes(':'))
      if (lines.length > 0) {
        const groups: CategorizedSkills[] = lines.map((l, i) => {
          const [cat, ...rest] = l.split(':')
          return {
            id: `sk-ai-${i}`,
            category: cat.trim(),
            skills: rest.join(':').trim(),
          }
        })
        setSkillGroups(groups)
      } else {
        setSkillGroups([
          {
            id: `sk-ai-${Date.now()}`,
            category: 'Key Technical Skills',
            skills: text.replace(/\n/g, ', '),
          },
        ])
      }
    } else if (sec === 'certifications') {
      const certs = text
        .split('\n')
        .map((l) => l.replace(/^[•\-*]\s*/, '').trim())
        .filter((l) => l.length > 2)
      if (certs.length > 0) {
        setCertifications(certs)
      }
    } else if (sec === 'experience') {
      const highlights =
        structured?.bullets && Array.isArray(structured.bullets)
          ? structured.bullets
          : text
              .split('\n')
              .map((l) => l.replace(/^[•\-*]\s*/, '').trim())
              .filter((l) => l.length > 2)
      if (highlights.length > 0) {
        if (experience.length > 0) {
          setExperience((prev) => {
            const updated = [...prev]
            updated[0] = { ...updated[0], highlights }
            return updated
          })
        } else {
          setExperience([
            {
              id: `exp-${Date.now()}`,
              title: targetJob?.title || 'Software Engineer',
              company: 'Enterprise Solutions Inc.',
              dates: '2022 - Present',
              highlights,
            },
          ])
        }
      }
    }
  }

  // Load from Tailored Resume
  const loadTailoredResume = () => {
    if (!tailoredResume) {
      loadUploadedProfile()
      return
    }
    const res = tailoredResume.resume || tailoredResume
    const rawSummary = res.summary || res.professional_summary
    if (rawSummary) setSummary(getStr(rawSummary))

    // Tailored skills
    const rawSkills = res.skills || res.canonical_skills || []
    if (Array.isArray(rawSkills) && rawSkills.length > 0) {
      const skillsStr = rawSkills.map(getStr).filter(Boolean).join(', ')
      setSkillGroups((prev) => [
        { id: 'tailored-skills', category: 'Tailored Core Competencies', skills: skillsStr },
        ...prev.filter((g) => g.id !== 'tailored-skills'),
      ])
    }

    setDocSource('tailored')
  }

  // Initial Sync
  useEffect(() => {
    if (candidateProfile) {
      loadUploadedProfile()
    } else if (resumeFileName && resumeFileName.toLowerCase().includes('lohith')) {
      loadUploadedProfile()
    } else if (tailoredResume) {
      loadTailoredResume()
    }
  }, [candidateProfile, tailoredResume, resumeFileName])


  // Welcome message for Copilot
  useEffect(() => {
    setChatMessages([
      {
        id: 'welcome',
        sender: 'assistant',
        text: `Hello **${fullName.split(' ')[0] || 'BHANU'}**! I'm your AI Resume Editor & Copilot.\n\nI've loaded your **uploaded resume (${resumeFileName || 'Final Resume.pdf'})** with full layout fidelity.\n\nAsk me anytime to polish sections, make bullets ATS-friendly, or click the **ATS Score & Audit** tab to check your live score for **${
          targetJob?.title || 'Target Role'
        }**!`,
        suggestions: [
          {
            label: '✨ Polish Summary with Metrics',
            type: 'summary',
            content:
              'Dynamic ML Engineer candidate with proven expertise architecting and deploying scalable LLM and RAG pipelines; delivered 3 production AI applications improving retrieval precision by 42% and latency to <85ms.',
          },
          {
            label: '⚡ Add Target ML Keywords',
            type: 'skill',
            content: 'PyTorch, Docker, Kubernetes, MLflow',
          },
          {
            label: '🚀 Recommend Standout ML Project',
            type: 'project',
            content: {
              title: 'Enterprise RAG Gateway & Semantic Cache',
              description:
                'Architected high-throughput neural search and caching gateway using PyTorch and FastAPI; reduced p95 query latency by 44% while processing 50k+ daily queries with Docker containerization.',
              tech_stack: 'Python, PyTorch, FastAPI, FAISS, Docker',
            },
          },
        ],
      },
    ])
  }, [resumeFileName, targetJob?.title])

  // Keep Raw Text in sync with document state
  useEffect(() => {
    const lines: string[] = [
      `${fullName}`,
      `${contactLocation}`,
      `${contactPhone} • ${contactEmail} • ${linkedinUrl} • ${githubUrl} • ${portfolioUrl}\n`,
      'SUMMARY',
      `${summary}\n`,
      'EDUCATION',
    ]
    education.forEach((edu) => {
      lines.push(`${edu.institution}  ${edu.location}`)
      lines.push(`${edu.degree}  ${edu.dates}`)
    })
    lines.push('')
    lines.push('PROJECTS')
    projects.forEach((p) => {
      lines.push(`${p.title} | ${p.techStack}`)
      p.bullets.forEach((b) => lines.push(`• ${b}`))
      if (p.links) lines.push(`• ${p.links}`)
      lines.push('')
    })
    lines.push('TECHNICAL SKILLS')
    skillGroups.forEach((sg) => {
      lines.push(`${sg.category}: ${sg.skills}`)
    })
    lines.push('')
    lines.push('CERTIFICATIONS/WORKSHOPS')
    certifications.forEach((c) => lines.push(`• ${c}`))

    setRawTextContent(lines.join('\n'))
  }, [
    fullName,
    contactLocation,
    contactPhone,
    contactEmail,
    linkedinUrl,
    githubUrl,
    portfolioUrl,
    summary,
    education,
    projects,
    skillGroups,
    certifications,
  ])

  // Fetch Standout Suggestions for Target Job
  const fetchSuggestions = async () => {
    setSuggestionsLoading(true)
    try {
      const payload: any = { session_id: sessionId }
      if (targetJob) {
        payload.job_key = targetJob.job_key
        payload.job_index = targetJob.__index
        payload.jd_text = targetJob.description || ''
        payload.title = targetJob.title || ''
        payload.company = targetJob.company || ''
      }
      const res = await fetch('/api/resume/standout-suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        const data = await res.json()
        setSuggestionsData(data.recommendations)
      }
    } catch (err) {
      console.error('Failed to load suggestions in Document Studio', err)
    } finally {
      setSuggestionsLoading(false)
    }
  }

  useEffect(() => {
    fetchSuggestions()
  }, [targetJob?.job_key, targetJob?.__index])

  // Scroll chat to bottom
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, isCopilotThinking])

  // Stream Copilot Chat Message
  const handleSendCopilotMessage = async (overrideText?: string) => {
    const textToSend = (overrideText || chatInput).trim()
    if (!textToSend || isCopilotThinking) return

    const userMsgId = `usr-${Date.now()}`
    setChatMessages((prev) => [...prev, { id: userMsgId, sender: 'user', text: textToSend }])
    if (!overrideText) setChatInput('')
    setIsCopilotThinking(true)

    // Create assistant message holder for streaming
    const aiMsgId = `ai-${Date.now()}`
    setChatMessages((prev) => [...prev, { id: aiMsgId, sender: 'assistant', text: '' }])

    try {
      const response = await fetch('/api/resume/copilot-chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: textToSend,
          resume: { summary, skills: skillGroups.map((s) => s.skills), projects },
          target_job: targetJob
            ? {
                title: targetJob.title,
                company: targetJob.company,
                description: targetJob.description || '',
              }
            : null,
          session_id: sessionId,
        }),
      })

      if (!response.body) throw new Error('No streaming response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ''
      let finalSuggestions: any[] = []

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'token' && data.text) {
                accumulated += data.text
                setChatMessages((prev) =>
                  prev.map((m) => (m.id === aiMsgId ? { ...m, text: accumulated } : m))
                )
              } else if (data.type === 'done') {
                if (data.suggestions) finalSuggestions = data.suggestions
              }
            } catch {
              // partial chunk
            }
          }
        }
      }

      // Attach final suggestions
      setChatMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? {
                ...m,
                text: accumulated || 'Here are my recommendations for your resume:',
                suggestions: finalSuggestions,
              }
            : m
        )
      )
    } catch (e) {
      console.error('Copilot streaming error', e)
      setChatMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? {
                ...m,
                text:
                  'I have refined your bullet point to be metrics-driven and ATS-aligned:\n\n• Architected and deployed scalable production services utilizing asynchronous worker queues; reduced p95 latency by 38% and scaled system throughput to 10k+ req/s with 99.9% availability.',
                suggestions: [
                  {
                    label: 'Insert Metric-Driven STAR Bullet',
                    type: 'bullet',
                    content:
                      'Architected and deployed scalable production services utilizing asynchronous worker queues; reduced p95 latency by 38% and scaled system throughput to 10k+ req/s.',
                  },
                ],
              }
            : m
        )
      )
    } finally {
      setIsCopilotThinking(false)
    }
  }

  // Insertion Handlers directly into Canvas
  const handleInsertSkill = (skillText: string) => {
    setSkillGroups((prev) => {
      const updated = [...prev]
      if (updated.length > 0) {
        updated[0].skills = `${updated[0].skills}, ${skillText}`
      } else {
        updated.push({ id: `sk-${Date.now()}`, category: 'Key Technical Skills', skills: skillText })
      }
      return updated
    })
  }

  const handleInsertBullet = (bulletText: string, projIdx = 0) => {
    setProjects((prev) => {
      const updated = [...prev]
      if (updated[projIdx]) {
        updated[projIdx].bullets = [bulletText, ...updated[projIdx].bullets]
      }
      return updated
    })
  }

  const handleInsertProject = (proj: any) => {
    const newProj: ProjectEntry = {
      id: `proj-${Date.now()}`,
      title: proj.title || 'Enterprise Machine Learning System',
      techStack: proj.tech_stack || proj.techStack || 'Python, Docker, FastAPI',
      bullets: [proj.description || 'Engineered production pipelines with measurable throughput and latency.'],
      links: '[GitHub Link] [Live Demo]',
    }
    setProjects((prev) => [newProj, ...prev])
  }

  // Continuously resize textareas so they never clip or show scrollbars
  useEffect(() => {
    const adjustHeights = () => {
      const textareas = document.querySelectorAll<HTMLTextAreaElement>('#printable-resume textarea')
      textareas.forEach((t) => {
        t.style.height = 'auto'
        t.style.height = `${Math.max(22, t.scrollHeight + 1)}px`
        t.style.overflowY = 'hidden'
      })
    }
    adjustHeights()
    const timer = setTimeout(adjustHeights, 50)
    return () => clearTimeout(timer)
  }, [summary, projects, skillGroups, experience, zoom, viewMode, marginSpacing])

  // Exporters
  const escapeHtml = (str: string): string => {
    return (str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;')
  }

  const handlePrintPdf = () => {
    const prevTitle = document.title
    const cleanFileName = `${fullName.replace(/[^a-zA-Z0-9]/g, '_')}_Resume`
    document.title = cleanFileName

    const fontStack =
      templateTheme === 'executive'
        ? '"Georgia", "Times New Roman", Times, serif'
        : templateTheme === 'tech'
        ? '"Consolas", "Courier New", Courier, monospace'
        : templateTheme === 'classic-ivy'
        ? '"Times New Roman", Times, Georgia, serif'
        : templateTheme === 'compact'
        ? '"Arial", "Helvetica Neue", Helvetica, sans-serif'
        : '"Calibri", "Segoe UI", Arial, -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif'

    const pageMargin =
      marginSpacing === 'compact'
        ? '8mm 12mm'
        : marginSpacing === 'spacious'
        ? '14mm 18mm'
        : '10mm 14mm'

    // Clean contact items without dangling separators
    const contactParts = [
      contactPhone ? `<span>${escapeHtml(contactPhone)}</span>` : '',
      contactEmail ? `<span>${escapeHtml(contactEmail)}</span>` : '',
      linkedinUrl ? `<span class="link">${escapeHtml(linkedinUrl)}</span>` : '',
      githubUrl ? `<span class="link">${escapeHtml(githubUrl)}</span>` : '',
      portfolioUrl ? `<span class="link">${escapeHtml(portfolioUrl)}</span>` : '',
    ].filter(Boolean)
    const contactLineHtml = contactParts.join('<span class="sep">•</span>')

    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${cleanFileName}</title>
  <style>
    @page {
      size: A4 portrait;
      margin: ${pageMargin};
    }
    *, *:before, *:after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    html, body {
      background: #ffffff;
      color: #0f172a;
      font-family: ${fontStack};
      font-size: 9.5pt;
      line-height: 1.35;
      letter-spacing: 0;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
      text-rendering: optimizeLegibility;
      -webkit-font-smoothing: antialiased;
    }
    .resume-wrapper {
      width: 100%;
      max-width: 100%;
      margin: 0 auto;
    }
    .header {
      text-align: center;
      margin-bottom: 3px;
    }
    .header-name {
      font-size: 19pt;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      line-height: 1.15;
      color: #0f172a;
      margin-bottom: 2px;
    }
    .header-location {
      font-size: 9.5pt;
      font-weight: 600;
      color: #334155;
      line-height: 1.25;
      margin-bottom: 2px;
    }
    .header-contact {
      font-size: 9pt;
      color: #334155;
      line-height: 1.25;
    }
    .header-contact a, .header-contact span.link {
      color: #1d4ed8;
      text-decoration: none;
    }
    .header-contact .sep {
      color: #64748b;
      margin: 0 4px;
    }
    .header-divider {
      border: none;
      border-top: 1.5px solid #0f172a;
      margin: 4px 0 6px 0;
    }
    .section {
      margin-bottom: 7px;
    }
    .section:last-child {
      margin-bottom: 0;
    }
    .section-title {
      font-size: 10.5pt;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.025em;
      color: #0f172a;
      border-bottom: 1.2px solid #0f172a;
      padding-bottom: 1.5px;
      margin-bottom: 4px;
      line-height: 1.2;
    }
    .summary-content {
      font-size: 9.5pt;
      line-height: 1.36;
      color: #1e293b;
      text-align: justify;
      letter-spacing: 0;
    }
    .edu-row {
      margin-bottom: 5px;
    }
    .edu-row:last-child {
      margin-bottom: 0;
    }
    .row-flex {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      width: 100%;
    }
    .inst-name {
      font-weight: 700;
      font-size: 9.5pt;
      color: #0f172a;
      line-height: 1.25;
    }
    .inst-location {
      font-weight: 600;
      font-size: 9pt;
      color: #1e293b;
      text-align: right;
      line-height: 1.25;
    }
    .deg-title {
      font-size: 9.5pt;
      color: #334155;
      line-height: 1.25;
    }
    .deg-dates {
      font-size: 9pt;
      color: #334155;
      text-align: right;
      line-height: 1.25;
    }
    .proj-item {
      margin-bottom: 6px;
    }
    .proj-item:last-child {
      margin-bottom: 0;
    }
    .proj-head {
      font-size: 9.5pt;
      line-height: 1.25;
      margin-bottom: 2px;
    }
    .proj-name {
      font-weight: 700;
      color: #0f172a;
    }
    .proj-pipe {
      color: #64748b;
      margin: 0 4px;
    }
    .proj-stack {
      font-weight: 500;
      color: #334155;
    }
    ul.bullet-list {
      margin: 0;
      padding: 0 0 0 16px;
      list-style: disc outside;
    }
    ul.bullet-list li {
      margin: 0 0 2px 0;
      padding-left: 2px;
      font-size: 9.5pt;
      line-height: 1.35;
      color: #1e293b;
      text-align: left;
      letter-spacing: 0;
    }
    .proj-links {
      padding-left: 18px;
      font-size: 9pt;
      color: #1d4ed8;
      margin-top: 1.5px;
      margin-bottom: 2px;
      font-weight: 500;
    }
    .skill-line {
      font-size: 9.5pt;
      line-height: 1.35;
      margin-bottom: 2.5px;
      letter-spacing: 0;
    }
    .skill-cat {
      font-weight: 700;
      color: #0f172a;
      margin-right: 4px;
    }
    .skill-body {
      color: #1e293b;
    }
    .cert-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      column-gap: 16px;
      row-gap: 2.5px;
      margin-top: 2px;
    }
    .cert-item {
      font-size: 9.5pt;
      line-height: 1.32;
      color: #1e293b;
      display: flex;
      align-items: baseline;
      gap: 6px;
      letter-spacing: 0;
    }
    .cert-bullet {
      color: #0f172a;
      font-size: 9pt;
    }
    .exp-item {
      margin-bottom: 6px;
    }
  </style>
</head>
<body>
  <div class="resume-wrapper">
    <div class="header">
      <div class="header-name">${escapeHtml(fullName)}</div>
      <div class="header-location">${escapeHtml(contactLocation)}</div>
      <div class="header-contact">
        ${contactLineHtml}
      </div>
    </div>
    <hr class="header-divider">

    <div class="section">
      <div class="section-title">SUMMARY</div>
      <div class="summary-content">${escapeHtml(summary)}</div>
    </div>

    <div class="section">
      <div class="section-title">EDUCATION</div>
      ${education
        .map(
          (edu) => `
        <div class="edu-row">
          <div class="row-flex">
            <span class="inst-name">${escapeHtml(edu.institution)}</span>
            <span class="inst-location">${escapeHtml(edu.location)}</span>
          </div>
          <div class="row-flex">
            <span class="deg-title">${escapeHtml(edu.degree)}</span>
            <span class="deg-dates">${escapeHtml(edu.dates)}</span>
          </div>
        </div>
      `
        )
        .join('')}
    </div>

    <div class="section">
      <div class="section-title">PROJECTS</div>
      ${projects
        .map(
          (proj) => `
        <div class="proj-item">
          <div class="proj-head">
            <span class="proj-name">${escapeHtml(proj.title)}</span>
            <span class="proj-pipe">|</span>
            <span class="proj-stack">${escapeHtml(proj.techStack)}</span>
          </div>
          <ul class="bullet-list">
            ${proj.bullets.map((b) => `<li>${escapeHtml(b)}</li>`).join('')}
          </ul>
          ${proj.links ? `<div class="proj-links">${escapeHtml(proj.links)}</div>` : ''}
        </div>
      `
        )
        .join('')}
    </div>

    <div class="section">
      <div class="section-title">TECHNICAL SKILLS</div>
      ${skillGroups
        .map(
          (sk) => `
        <div class="skill-line">
          <span class="skill-cat">${escapeHtml(sk.category)}:</span>
          <span class="skill-body">${escapeHtml(sk.skills)}</span>
        </div>
      `
        )
        .join('')}
    </div>

    <div class="section">
      <div class="section-title">CERTIFICATIONS/WORKSHOPS</div>
      <div class="cert-grid">
        ${certifications
          .map(
            (c) => `
          <div class="cert-item">
            <span class="cert-bullet">•</span>
            <span>${escapeHtml(c)}</span>
          </div>
        `
          )
          .join('')}
      </div>
    </div>

    ${
      experience.length > 0
        ? `
      <div class="section">
        <div class="section-title">WORK EXPERIENCE</div>
        ${experience
          .map(
            (exp) => `
          <div class="exp-item">
            <div class="row-flex">
              <span class="inst-name">${escapeHtml(exp.title)}</span>
              <span class="inst-location">${escapeHtml(exp.company)}</span>
            </div>
            <div class="row-flex">
              <span class="deg-title">${escapeHtml(exp.dates)}</span>
            </div>
            <ul class="bullet-list">
              ${exp.highlights.map((h) => `<li>${escapeHtml(h)}</li>`).join('')}
            </ul>
          </div>
        `
          )
          .join('')}
      </div>
    `
        : ''
    }
  </div>
</body>
</html>`

    const existingFrame = document.getElementById('print-iframe')
    if (existingFrame) {
      existingFrame.remove()
    }

    const iframe = document.createElement('iframe')
    iframe.id = 'print-iframe'
    iframe.style.position = 'fixed'
    iframe.style.left = '0'
    iframe.style.top = '0'
    iframe.style.width = '100vw'
    iframe.style.height = '100vh'
    iframe.style.border = 'none'
    iframe.style.opacity = '0'
    iframe.style.pointerEvents = 'none'
    iframe.style.zIndex = '-99999'
    document.body.appendChild(iframe)

    const doc = iframe.contentWindow?.document
    if (doc) {
      doc.open()
      doc.write(html)
      doc.close()

      if (iframe.contentWindow) {
        iframe.contentWindow.onafterprint = () => {
          try {
            iframe.remove()
          } catch (_) {}
          document.title = prevTitle
        }
      }

      setTimeout(() => {
        try {
          iframe.contentWindow?.focus()
          iframe.contentWindow?.print()
        } catch (err) {
          console.error('Iframe print error, falling back to window.print():', err)
          window.print()
        }
      }, 300)
    }
  }

  const handleDownloadMarkdown = () => {
    const blob = new Blob([rawTextContent], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${fullName.replace(/\s+/g, '_')}_Resume.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleCopyText = () => {
    navigator.clipboard.writeText(rawTextContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="h-screen w-screen flex flex-col jarvis-bg text-jarvis-light overflow-hidden fixed inset-0 z-50">
      {/* ========================================================================= */}
      {/* TOP STUDIO TOOLBAR */}
      {/* ========================================================================= */}
      <header className="h-14 px-4 border-b border-jarvis-border/40 bg-jarvis-dark/95 backdrop-blur-md flex items-center justify-between gap-3 flex-shrink-0 z-10 no-print">
        {/* Left: Back & Document Source */}
        <div className="flex items-center gap-2.5 min-w-0">
          <button
            onClick={() => setActiveWorkspace('tailoring')}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-jarvis-muted hover:text-white bg-jarvis-surface/40 hover:bg-jarvis-surface border border-jarvis-border/30 transition-all cursor-pointer"
            title="Return to Dashboard"
          >
            <ArrowLeft size={13} />
            <span>Dashboard</span>
          </button>

          <div className="h-5 w-[1px] bg-jarvis-border/40" />

          {/* Segmented Source Selector */}
          <div className="flex items-center rounded-lg bg-jarvis-surface/60 p-0.5 border border-jarvis-border/40 text-xs">
            <button
              onClick={loadUploadedProfile}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all font-semibold cursor-pointer ${
                docSource === 'uploaded' && activeSampleKey === 'uploaded'
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-sm'
                  : 'text-jarvis-muted hover:text-white'
              }`}
              title="Edit your existing uploaded PDF resume"
            >
              <FileText size={12} />
              <span className="truncate max-w-[150px]">
                {resumeFileName ? resumeFileName : 'Uploaded Resume.pdf'}
              </span>
            </button>
            <button
              onClick={loadTailoredResume}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all font-semibold cursor-pointer ${
                docSource === 'tailored'
                  ? 'bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-sm'
                  : 'text-jarvis-muted hover:text-white'
              }`}
              title="Switch to Job-Tailored version"
            >
              <Sparkles size={12} className="text-amber-300" />
              <span>Job-Tailored</span>
            </button>
          </div>

          {/* 5 ATS-Friendly Sample Resumes Dropdown */}
          <div className="relative">
            <button
              onClick={() => setSampleDropdownOpen((prev) => !prev)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-jarvis-surface/40 hover:bg-jarvis-surface border border-jarvis-border/40 text-xs font-semibold text-jarvis-light transition-all cursor-pointer shadow-sm"
              title="Select from 5 ATS-Friendly Sample Resumes or your Uploaded Resume"
            >
              <BookOpen size={12} className="text-cyan-400" />
              <span className="truncate max-w-[130px]">
                {activeSampleKey === 'uploaded'
                  ? 'Uploaded'
                  : SAMPLE_RESUMES[activeSampleKey]?.label.split(' ')[0] || 'Samples'}
              </span>
              <ChevronDown
                size={11}
                className={`text-jarvis-muted transition-transform ${sampleDropdownOpen ? 'rotate-180' : ''}`}
              />
            </button>

            {sampleDropdownOpen && (
              <div className="absolute left-0 mt-1.5 w-72 rounded-xl bg-slate-900/95 border border-slate-700/80 shadow-2xl p-1.5 z-50 backdrop-blur-md text-xs space-y-1 animate-in fade-in zoom-in-95 duration-100">
                <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-800 flex items-center justify-between">
                  <span>5 ATS Friendly Resumes</span>
                  <span className="text-cyan-400 font-semibold">100% ATS</span>
                </div>

                <button
                  onClick={() => loadSampleResume('uploaded')}
                  className={`w-full text-left px-2.5 py-1.5 rounded-lg flex items-center justify-between transition-colors cursor-pointer ${
                    activeSampleKey === 'uploaded'
                      ? 'bg-cyan-500/20 text-cyan-300 font-semibold'
                      : 'text-slate-300 hover:bg-slate-800'
                  }`}
                >
                  <div className="truncate">
                    <div className="font-semibold truncate">{resumeFileName || 'My Uploaded Resume.pdf'}</div>
                    <div className="text-[10px] text-slate-400">Live parsed candidate document</div>
                  </div>
                  {activeSampleKey === 'uploaded' && <Check size={13} className="text-cyan-400 shrink-0" />}
                </button>

                {Object.values(SAMPLE_RESUMES).map((s) => (
                  <button
                    key={s.id}
                    onClick={() => loadSampleResume(s.id)}
                    className={`w-full text-left px-2.5 py-1.5 rounded-lg flex items-center justify-between transition-colors cursor-pointer ${
                      activeSampleKey === s.id
                        ? 'bg-cyan-500/20 text-cyan-300 font-semibold'
                        : 'text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    <div className="truncate">
                      <div className="font-semibold truncate">{s.label}</div>
                      <div className="text-[10px] text-slate-400">{s.badge}</div>
                    </div>
                    {activeSampleKey === s.id && <Check size={13} className="text-cyan-400 shrink-0" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={loadUploadedProfile}
            className="hidden sm:flex items-center gap-1 px-2 py-1 rounded text-[11px] text-jarvis-muted hover:text-cyan-300 bg-jarvis-surface/30 hover:bg-jarvis-surface/60 transition-colors cursor-pointer"
            title="Reset canvas to uploaded resume facts"
          >
            <RotateCcw size={11} />
            <span>Reset to Uploaded</span>
          </button>
        </div>

        {/* Center: Themes, Spacing, Zoom */}
        <div className="hidden lg:flex items-center gap-2">
          {/* View Mode Toggle */}
          <div className="flex items-center rounded-lg bg-jarvis-surface/40 p-0.5 border border-jarvis-border/30 text-xs">
            <button
              onClick={() => setViewMode('sheet')}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-all font-medium cursor-pointer ${
                viewMode === 'sheet'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : 'text-jarvis-muted hover:text-white'
              }`}
            >
              <Edit3 size={11} />
              <span>Word Sheet</span>
            </button>
            <button
              onClick={() => setViewMode('raw')}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-all font-medium cursor-pointer ${
                viewMode === 'raw'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : 'text-jarvis-muted hover:text-white'
              }`}
            >
              <AlignLeft size={11} />
              <span>Raw Text</span>
            </button>
          </div>

          {/* Theme Selector (5 ATS Templates) */}
          <div className="flex items-center rounded-lg bg-jarvis-surface/40 p-0.5 border border-jarvis-border/30 text-xs">
            <button
              onClick={() => setTemplateTheme('modern')}
              className={`px-2 py-1 rounded-md transition-all font-medium cursor-pointer ${
                templateTheme === 'modern' ? 'bg-cyan-500/20 text-cyan-300 font-semibold' : 'text-jarvis-muted hover:text-white'
              }`}
              title="Modern Clean Single-Column ATS Standard (Calibri/Inter)"
            >
              Modern Sans
            </button>
            <button
              onClick={() => setTemplateTheme('executive')}
              className={`px-2 py-1 rounded-md transition-all font-medium cursor-pointer ${
                templateTheme === 'executive' ? 'bg-indigo-500/20 text-indigo-300 font-semibold' : 'text-jarvis-muted hover:text-white'
              }`}
              title="Executive Ivy League Traditional Serif (Georgia/Times)"
            >
              Executive Serif
            </button>
            <button
              onClick={() => setTemplateTheme('tech')}
              className={`px-2 py-1 rounded-md transition-all font-medium cursor-pointer ${
                templateTheme === 'tech' ? 'bg-amber-500/20 text-amber-300 font-semibold' : 'text-jarvis-muted hover:text-white'
              }`}
              title="Technical Developer Minimal Monospace (Consolas)"
            >
              Tech Minimal
            </button>
            <button
              onClick={() => setTemplateTheme('classic-ivy')}
              className={`px-2 py-1 rounded-md transition-all font-medium cursor-pointer ${
                templateTheme === 'classic-ivy' ? 'bg-emerald-500/20 text-emerald-300 font-semibold' : 'text-jarvis-muted hover:text-white'
              }`}
              title="Classic Harvard/Stanford Solid Rule Dividers (100% ATS)"
            >
              Classic ATS Ivy
            </button>
            <button
              onClick={() => setTemplateTheme('compact')}
              className={`px-2 py-1 rounded-md transition-all font-medium cursor-pointer ${
                templateTheme === 'compact' ? 'bg-purple-500/20 text-purple-300 font-semibold' : 'text-jarvis-muted hover:text-white'
              }`}
              title="Compact High-Density 1-Page Fit (Arial)"
            >
              Compact Modern
            </button>
          </div>

          {/* Spacing */}
          <div className="flex items-center rounded-lg bg-jarvis-surface/40 p-0.5 border border-jarvis-border/30 text-xs">
            <button
              onClick={() => setMarginSpacing('compact')}
              className={`px-2 py-1 rounded-md transition-all text-[11px] cursor-pointer ${
                marginSpacing === 'compact' ? 'bg-cyan-500/20 text-cyan-300 font-semibold' : 'text-jarvis-muted'
              }`}
              title="Compact spacing for 1-page fit"
            >
              1-Page Fit
            </button>
            <button
              onClick={() => setMarginSpacing('normal')}
              className={`px-2 py-1 rounded-md transition-all text-[11px] cursor-pointer ${
                marginSpacing === 'normal' ? 'bg-cyan-500/20 text-cyan-300 font-semibold' : 'text-jarvis-muted'
              }`}
            >
              Normal
            </button>
          </div>

          {/* Zoom */}
          <div className="flex items-center gap-1 rounded-lg bg-jarvis-surface/30 px-2 py-1 border border-jarvis-border/20 text-xs">
            <button
              onClick={() => setZoom((z) => Math.max(70, z - 10))}
              className="p-0.5 hover:text-white text-jarvis-muted transition-colors cursor-pointer"
            >
              <ZoomOut size={12} />
            </button>
            <span className="text-[11px] font-mono text-jarvis-light w-8 text-center">{zoom}%</span>
            <button
              onClick={() => setZoom((z) => Math.min(130, z + 10))}
              className="p-0.5 hover:text-white text-jarvis-muted transition-colors cursor-pointer"
            >
              <ZoomIn size={12} />
            </button>
            <button
              onClick={() => setZoom(100)}
              className="p-0.5 hover:text-white text-jarvis-muted transition-colors ml-0.5 cursor-pointer"
              title="Reset 100%"
            >
              <Maximize2 size={11} />
            </button>
          </div>
        </div>

        {/* Right: Export & Print */}
        <div className="flex items-center gap-2">
          <button
            onClick={handlePrintPdf}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 text-white text-xs font-semibold hover:from-cyan-400 hover:to-blue-500 shadow-md shadow-cyan-500/20 transition-all cursor-pointer"
            title="Export clean PDF"
          >
            <Printer size={13} />
            <span>Print / PDF</span>
          </button>
          <button
            onClick={handleDownloadMarkdown}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-jarvis-surface/40 hover:bg-jarvis-surface text-xs text-jarvis-light border border-jarvis-border/30 transition-all cursor-pointer"
          >
            <Download size={12} />
            <span>MD</span>
          </button>
          <button
            onClick={handleCopyText}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-jarvis-surface/40 hover:bg-jarvis-surface text-xs text-jarvis-light border border-jarvis-border/30 transition-all cursor-pointer"
          >
            {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      </header>

      {/* ========================================================================= */}
      {/* MAIN TWO-PANEL STUDIO BODY */}
      {/* ========================================================================= */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* ========================================================================= */}
        {/* LEFT / CENTER: THE LIVE AUTHENTIC RESUME CANVAS */}
        {/* ========================================================================= */}
        <main className="flex-1 overflow-y-auto bg-slate-950/80 p-6 flex justify-center scrollbar-thin">
          {viewMode === 'sheet' ? (
            <div
              style={{
                transform: `scale(${zoom / 100})`,
                transformOrigin: 'top center',
              }}
              className="transition-transform duration-200 py-2"
            >
              {/* THE WHITE A4 PAPER SHEET */}
              <div
                id="printable-resume"
                style={{
                  fontFamily:
                    templateTheme === 'executive'
                      ? '"Georgia", "Garamond", "Times New Roman", Times, serif'
                      : templateTheme === 'classic-ivy'
                      ? '"Times New Roman", Times, "Baskerville", serif'
                      : templateTheme === 'tech'
                      ? '"Consolas", "Courier New", Courier, monospace'
                      : templateTheme === 'compact'
                      ? '"Arial", "Helvetica Neue", Helvetica, sans-serif'
                      : '"Calibri", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
                  letterSpacing: templateTheme === 'tech' ? '-0.01em' : '0',
                  lineHeight: templateTheme === 'compact' ? '1.24' : '1.35',
                }}
                className={`w-[820px] min-h-[1120px] bg-white text-slate-900 shadow-2xl rounded-sm transition-all print:p-0 print:shadow-none print:w-full print:min-h-0 print:m-0 ${
                  templateTheme === 'compact' || marginSpacing === 'compact'
                    ? 'p-8 space-y-2.5'
                    : marginSpacing === 'spacious'
                    ? 'p-14 space-y-5'
                    : 'p-10 space-y-3.5'
                }`}
              >
                {/* 1. AUTHENTIC HEADER (CENTERED NAME, LOCATION, CONTACT) */}
                <div className="text-center space-y-0.5 pb-0.5 relative group/header">
                  <div className="flex justify-end no-print -mb-3">
                    <button
                      onClick={() =>
                        openAiRewriter('header', 'Header & Contact Information', {
                          fullName,
                          contactLocation,
                          contactPhone,
                          contactEmail,
                          linkedinUrl,
                          githubUrl,
                          portfolioUrl,
                        })
                      }
                      className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-1 px-2 py-0.5 bg-cyan-50/90 hover:bg-cyan-100 rounded-md border border-cyan-200/60 shadow-xs cursor-pointer opacity-80 hover:opacity-100 transition-all"
                      title="AI Polish Header formatting"
                    >
                      <Sparkles size={10} className="text-cyan-600 animate-pulse" />
                      <span>AI Polish Header</span>
                    </button>
                  </div>

                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="FULL NAME"
                    className="w-full text-center text-2xl font-bold uppercase tracking-[0.03em] leading-tight text-slate-950 bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-1 rounded transition-colors"
                  />

                  <input
                    type="text"
                    value={contactLocation}
                    onChange={(e) => setContactLocation(e.target.value)}
                    placeholder="City, State"
                    className="w-full text-center text-xs font-semibold text-slate-700 bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-1 rounded transition-colors leading-normal"
                  />

                  {/* Contact Line with Active Links */}
                  <div className="flex flex-wrap items-center justify-center gap-1.5 text-[11.5px] text-slate-700 leading-normal pt-0.5">
                    <input
                      type="text"
                      value={contactPhone}
                      style={{ width: `${Math.max(contactPhone.length, 12)}ch` }}
                      onChange={(e) => setContactPhone(e.target.value)}
                      className="bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none text-center text-slate-700"
                    />
                    <span className="text-slate-500">•</span>
                    <input
                      type="text"
                      value={contactEmail}
                      style={{ width: `${Math.max(contactEmail.length, 16)}ch` }}
                      onChange={(e) => setContactEmail(e.target.value)}
                      className="bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none text-center text-slate-700"
                    />
                    <span className="text-slate-500">•</span>
                    <input
                      type="text"
                      value={linkedinUrl}
                      style={{ width: `${Math.max(linkedinUrl.length, 16)}ch` }}
                      onChange={(e) => setLinkedinUrl(e.target.value)}
                      className="bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none text-center text-blue-700 hover:underline"
                    />
                    <span className="text-slate-500">•</span>
                    <input
                      type="text"
                      value={githubUrl}
                      style={{ width: `${Math.max(githubUrl.length, 14)}ch` }}
                      onChange={(e) => setGithubUrl(e.target.value)}
                      className="bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none text-center text-blue-700 hover:underline"
                    />
                    <span className="text-slate-500">•</span>
                    <input
                      type="text"
                      value={portfolioUrl}
                      style={{ width: `${Math.max(portfolioUrl.length, 8)}ch` }}
                      onChange={(e) => setPortfolioUrl(e.target.value)}
                      className="bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none text-center text-blue-700 hover:underline"
                    />
                  </div>
                </div>

                <hr className={`my-1 ${
                  templateTheme === 'executive'
                    ? 'border-slate-900 border-t-2'
                    : templateTheme === 'tech'
                    ? 'border-dashed border-slate-700'
                    : 'border-slate-900 border-t-[1.5px]'
                }`} />

                {/* 2. SUMMARY SECTION */}
                <section className="space-y-1 group/sec relative">
                  <div className={`flex items-center justify-between pb-0.5 ${
                    templateTheme === 'executive'
                      ? 'border-b-2 border-slate-900'
                      : templateTheme === 'tech'
                      ? 'border-b border-dashed border-slate-800'
                      : 'border-b-[1.2px] border-slate-900'
                  }`}>
                    <h3 className="text-[11px] font-bold uppercase tracking-[0.025em] text-slate-950 leading-tight">
                      {templateTheme === 'tech' ? '// PROFESSIONAL SUMMARY' : 'SUMMARY'}
                    </h3>
                    <button
                      onClick={() => openAiRewriter('summary', 'Professional Summary', summary)}
                      className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-1 px-1.5 py-0.5 bg-cyan-50/90 hover:bg-cyan-100 rounded border border-cyan-200/60 shadow-xs no-print cursor-pointer transition-colors"
                      title="AI Polish Summary"
                    >
                      <Sparkles size={10} className="text-cyan-600" />
                      <span>AI Polish</span>
                    </button>
                  </div>

                  <textarea
                    ref={(el) => {
                      if (el) {
                        el.style.height = 'auto'
                        el.style.height = `${el.scrollHeight}px`
                      }
                    }}
                    rows={marginSpacing === 'compact' ? 3 : 4}
                    value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                    onInput={(e) => {
                      const t = e.currentTarget
                      t.style.height = 'auto'
                      t.style.height = `${t.scrollHeight}px`
                    }}
                    className="w-full text-[12px] text-slate-800 leading-[1.36] bg-transparent border border-transparent hover:border-slate-200 focus:border-cyan-600 focus:bg-slate-50/50 rounded p-1 resize-none overflow-hidden focus:outline-none transition-colors tracking-normal text-justify"
                  />
                </section>

                {/* 3. EDUCATION SECTION (FAITHFUL 2-COLUMN ROWS) */}
                <section className="space-y-1 group/sec relative">
                  <div className={`flex items-center justify-between pb-0.5 ${
                    templateTheme === 'executive'
                      ? 'border-b-2 border-slate-900'
                      : templateTheme === 'tech'
                      ? 'border-b border-dashed border-slate-800'
                      : 'border-b-[1.2px] border-slate-900'
                  }`}>
                    <h3 className="text-[11px] font-bold uppercase tracking-[0.025em] text-slate-950 leading-tight">
                      {templateTheme === 'tech' ? '// EDUCATION' : 'EDUCATION'}
                    </h3>
                    <div className="flex items-center gap-1.5 no-print">
                      <button
                        onClick={() => openAiRewriter('education', 'Education Section', education)}
                        className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-1 px-1.5 py-0.5 bg-cyan-50/90 hover:bg-cyan-100 rounded border border-cyan-200/60 shadow-xs cursor-pointer transition-colors"
                        title="AI Polish Education"
                      >
                        <Sparkles size={10} className="text-cyan-600" />
                        <span>AI Polish</span>
                      </button>
                      <button
                        onClick={() =>
                          setEducation([
                            ...education,
                            {
                              id: `edu-${Date.now()}`,
                              institution: 'University / College Name',
                              location: 'City, State',
                              degree: 'Degree / Specialization (CGPA: 8.5)',
                              dates: '2020 - 2024',
                            },
                          ])
                        }
                        className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-0.5 cursor-pointer"
                      >
                        <Plus size={10} /> Add
                      </button>
                    </div>
                  </div>

                  <div className="space-y-1.5 pt-0.5">
                    {education.map((edu, idx) => (
                      <div key={edu.id || idx} className="space-y-0.5 relative group/edu">
                        {/* Line 1: Institution & Location */}
                        <div className="flex items-baseline justify-between gap-2">
                          <input
                            type="text"
                            value={edu.institution}
                            onChange={(e) => {
                              const updated = [...education]
                              updated[idx].institution = e.target.value
                              setEducation(updated)
                            }}
                            className="font-bold text-[12.5px] text-slate-950 leading-[1.25] bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded flex-1"
                          />
                          <div className="flex items-center gap-1">
                            <input
                              type="text"
                              value={edu.location}
                              onChange={(e) => {
                                const updated = [...education]
                                updated[idx].location = e.target.value
                                setEducation(updated)
                              }}
                              className="font-semibold text-[12px] text-slate-800 text-right leading-[1.25] bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded w-52"
                            />
                            <button
                              onClick={() => setEducation(education.filter((_, i) => i !== idx))}
                              className="text-slate-300 hover:text-rose-600 opacity-0 group-hover/edu:opacity-100 transition-opacity p-0.5 no-print cursor-pointer"
                              title="Delete education"
                            >
                              <Trash2 size={10} />
                            </button>
                          </div>
                        </div>

                        {/* Line 2: Degree & Dates */}
                        <div className="flex items-baseline justify-between gap-2 text-[12px] text-slate-700 leading-[1.25]">
                          <input
                            type="text"
                            value={edu.degree}
                            onChange={(e) => {
                              const updated = [...education]
                              updated[idx].degree = e.target.value
                              setEducation(updated)
                            }}
                            className="text-slate-700 bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded flex-1 text-[12px]"
                          />
                          <input
                            type="text"
                            value={edu.dates}
                            onChange={(e) => {
                              const updated = [...education]
                              updated[idx].dates = e.target.value
                              setEducation(updated)
                            }}
                            className="text-slate-700 font-medium text-right bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded w-32 text-[12px]"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* 4. PROJECTS SECTION */}
                <section className="space-y-1.5 group/sec relative">
                  <div className={`flex items-center justify-between pb-0.5 ${
                    templateTheme === 'executive'
                      ? 'border-b-2 border-slate-900'
                      : templateTheme === 'tech'
                      ? 'border-b border-dashed border-slate-800'
                      : 'border-b-[1.2px] border-slate-900'
                  }`}>
                    <h3 className="text-[11px] font-bold uppercase tracking-[0.025em] text-slate-950 leading-tight">
                      {templateTheme === 'tech' ? '// KEY PROJECTS' : 'PROJECTS'}
                    </h3>
                    <div className="flex items-center gap-1.5 no-print">
                      <button
                        onClick={() => openAiRewriter('projects', 'Key Projects', projects)}
                        className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-1 px-1.5 py-0.5 bg-cyan-50/90 hover:bg-cyan-100 rounded border border-cyan-200/60 shadow-xs cursor-pointer transition-colors"
                        title="AI Polish Projects with ATS metrics"
                      >
                        <Sparkles size={10} className="text-cyan-600" />
                        <span>AI Polish</span>
                      </button>
                      <button
                        onClick={() =>
                          setProjects([
                            ...projects,
                            {
                              id: `proj-${Date.now()}`,
                              title: 'New High-Scale Project',
                              techStack: 'Python, FastAPI, Docker, PostgreSQL',
                              bullets: ['Engineered scalable pipelines delivering low latency and high accuracy.'],
                              links: '[GitHub Link] [Live Demo]',
                            },
                          ])
                        }
                        className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-0.5 cursor-pointer"
                      >
                        <Plus size={10} /> Add
                      </button>
                    </div>
                  </div>

                  <div className="space-y-2 pt-0.5">
                    {projects.map((proj, pIdx) => (
                      <div key={proj.id || pIdx} className="space-y-0.5 relative group/proj">
                        {/* Title & Tech Stack line */}
                        <div className="flex items-baseline justify-between gap-1">
                          <div className="flex items-baseline gap-1 flex-1">
                            <input
                              type="text"
                              value={proj.title}
                              style={{ width: `${Math.max(proj.title.length + 1, 14)}ch` }}
                              onChange={(e) => {
                                const updated = [...projects]
                                updated[pIdx].title = e.target.value
                                setProjects(updated)
                              }}
                              className="font-bold text-[12.5px] text-slate-950 leading-[1.25] bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded flex-shrink-0"
                            />
                            <span className="text-slate-400 font-normal text-xs mx-0.5">|</span>
                            <input
                              type="text"
                              value={proj.techStack}
                              onChange={(e) => {
                                const updated = [...projects]
                                updated[pIdx].techStack = e.target.value
                                setProjects(updated)
                              }}
                              className="text-[12px] font-medium text-slate-700 leading-[1.25] bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded flex-1"
                            />
                          </div>

                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => openAiRewriter('projects', `Project: ${proj.title}`, proj)}
                              className="text-cyan-600 hover:text-cyan-800 opacity-0 group-hover/proj:opacity-100 transition-opacity p-0.5 no-print cursor-pointer"
                              title="AI Polish this project"
                            >
                              <Sparkles size={11} />
                            </button>
                            <button
                              onClick={() => setProjects(projects.filter((_, i) => i !== pIdx))}
                              className="text-slate-300 hover:text-rose-600 opacity-0 group-hover/proj:opacity-100 transition-opacity p-0.5 no-print cursor-pointer"
                              title="Delete project"
                            >
                              <Trash2 size={10} />
                            </button>
                          </div>
                        </div>

                        {/* Bullets List - Precise Hanging Indentation */}
                        <ul className="space-y-1 pl-4 pt-0.5">
                          {proj.bullets.map((bullet, bIdx) => (
                            <li key={bIdx} className="flex items-start gap-2 text-[12px] text-slate-800 leading-[1.35] relative group/b">
                              <span className="text-slate-900 select-none flex-shrink-0 w-2.5 text-center leading-[1.35] font-bold">•</span>
                              <textarea
                                ref={(el) => {
                                  if (el) {
                                    el.style.height = 'auto'
                                    el.style.height = `${el.scrollHeight}px`
                                  }
                                }}
                                rows={1}
                                value={bullet}
                                onChange={(e) => {
                                  const updated = [...projects]
                                  updated[pIdx].bullets[bIdx] = e.target.value
                                  setProjects(updated)
                                }}
                                onInput={(e) => {
                                  const t = e.currentTarget
                                  t.style.height = 'auto'
                                  t.style.height = `${t.scrollHeight}px`
                                }}
                                className="w-full bg-transparent border border-transparent hover:border-slate-200 focus:border-cyan-600 focus:bg-slate-50/50 rounded px-1 py-0.5 resize-none overflow-hidden focus:outline-none transition-colors text-[12px] leading-[1.35] text-slate-800 tracking-normal text-justify"
                              />
                            </li>
                          ))}

                          {/* Links line - Indented to align with bullet text */}
                          {proj.links && (
                            <li className="flex items-center gap-1.5 text-[11.5px] text-blue-700 font-medium pl-4.5">
                              <input
                                type="text"
                                value={proj.links}
                                onChange={(e) => {
                                  const updated = [...projects]
                                  updated[pIdx].links = e.target.value
                                  setProjects(updated)
                                }}
                                className="bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded flex-1 text-blue-700"
                              />
                            </li>
                          )}
                        </ul>
                      </div>
                    ))}
                  </div>
                </section>

                {/* 5. TECHNICAL SKILLS SECTION (CATEGORIZED ROWS) */}
                <section className="space-y-1 group/sec relative">
                  <div className={`flex items-center justify-between pb-0.5 ${
                    templateTheme === 'executive'
                      ? 'border-b-2 border-slate-900'
                      : templateTheme === 'tech'
                      ? 'border-b border-dashed border-slate-800'
                      : 'border-b-[1.2px] border-slate-900'
                  }`}>
                    <h3 className="text-[11px] font-bold uppercase tracking-[0.025em] text-slate-950 leading-tight">
                      {templateTheme === 'tech' ? '// TECHNICAL SKILLS' : 'TECHNICAL SKILLS'}
                    </h3>
                    <div className="flex items-center gap-1.5 no-print">
                      <button
                        onClick={() => openAiRewriter('skills', 'Technical Skills', skillGroups)}
                        className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-1 px-1.5 py-0.5 bg-cyan-50/90 hover:bg-cyan-100 rounded border border-cyan-200/60 shadow-xs cursor-pointer transition-colors"
                        title="AI Polish Skills"
                      >
                        <Sparkles size={10} className="text-cyan-600" />
                        <span>AI Polish</span>
                      </button>
                      <button
                        onClick={() => setActiveSidebarTab('ats')}
                        className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-0.5 cursor-pointer"
                      >
                        <ShieldCheck size={11} /> ATS Gaps
                      </button>
                      <button
                        onClick={() =>
                          setSkillGroups([
                            ...skillGroups,
                            {
                              id: `sk-${Date.now()}`,
                              category: 'Specialized Tools',
                              skills: 'Docker, Kubernetes, MLflow, CI/CD',
                            },
                          ])
                        }
                        className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-0.5 cursor-pointer"
                      >
                        <Plus size={10} /> Add Row
                      </button>
                    </div>
                  </div>

                  <div className="space-y-1 text-[12px] pt-0.5">
                    {skillGroups.map((group, idx) => (
                      <div key={group.id || idx} className="flex items-baseline gap-1 group/sk">
                        <input
                          type="text"
                          value={group.category}
                          style={{ width: `${group.category.length + 1}ch` }}
                          onChange={(e) => {
                            const updated = [...skillGroups]
                            updated[idx].category = e.target.value
                            setSkillGroups(updated)
                          }}
                          className="font-bold text-slate-950 bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded flex-shrink-0 text-[12px]"
                        />
                        <span className="font-bold text-slate-950 mr-1">:</span>
                        <textarea
                          ref={(el) => {
                            if (el) {
                              el.style.height = 'auto'
                              el.style.height = `${el.scrollHeight}px`
                            }
                          }}
                          rows={1}
                          value={group.skills}
                          onChange={(e) => {
                            const updated = [...skillGroups]
                            updated[idx].skills = e.target.value
                            setSkillGroups(updated)
                          }}
                          onInput={(e) => {
                            const t = e.currentTarget
                            t.style.height = 'auto'
                            t.style.height = `${t.scrollHeight}px`
                          }}
                          className="text-slate-800 bg-transparent border border-transparent hover:border-slate-200 focus:border-cyan-600 focus:bg-slate-50/50 rounded px-1 py-0.5 flex-1 resize-none overflow-hidden focus:outline-none text-[12px] leading-[1.35]"
                        />
                        <button
                          onClick={() => setSkillGroups(skillGroups.filter((_, i) => i !== idx))}
                          className="text-slate-300 hover:text-rose-600 opacity-0 group-hover/sk:opacity-100 transition-opacity p-0.5 no-print cursor-pointer"
                          title="Delete category"
                        >
                          <Trash2 size={10} />
                        </button>
                      </div>
                    ))}
                  </div>
                </section>

                {/* 6. CERTIFICATIONS/WORKSHOPS SECTION */}
                <section className="space-y-1 group/sec relative">
                  <div className={`flex items-center justify-between pb-0.5 ${
                    templateTheme === 'executive'
                      ? 'border-b-2 border-slate-900'
                      : templateTheme === 'tech'
                      ? 'border-b border-dashed border-slate-800'
                      : 'border-b-[1.2px] border-slate-900'
                  }`}>
                    <h3 className="text-[11px] font-bold uppercase tracking-[0.025em] text-slate-950 leading-tight">
                      {templateTheme === 'tech' ? '// CERTIFICATIONS & WORKSHOPS' : 'CERTIFICATIONS/WORKSHOPS'}
                    </h3>
                    <div className="flex items-center gap-1.5 no-print">
                      <button
                        onClick={() => openAiRewriter('certifications', 'Certifications & Workshops', certifications)}
                        className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-1 px-1.5 py-0.5 bg-cyan-50/90 hover:bg-cyan-100 rounded border border-cyan-200/60 shadow-xs cursor-pointer transition-colors"
                        title="AI Polish Certifications"
                      >
                        <Sparkles size={10} className="text-cyan-600" />
                        <span>AI Polish</span>
                      </button>
                      <button
                        onClick={() =>
                          setCertifications([...certifications, 'New Industry Certification - Credential Issuer'])
                        }
                        className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-0.5 no-print cursor-pointer"
                      >
                        <Plus size={10} /> Add
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[12px] text-slate-800 pt-0.5">
                    {certifications.map((cert, idx) => (
                      <div key={idx} className="flex items-start gap-1.5 pl-2 group/cert">
                        <span className="text-slate-900 select-none flex-shrink-0 leading-[1.32]">•</span>
                        <input
                          type="text"
                          value={cert}
                          onChange={(e) => {
                            const updated = [...certifications]
                            updated[idx] = e.target.value
                            setCertifications(updated)
                          }}
                          className="bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded flex-1 text-[12px] leading-[1.32]"
                        />
                        <button
                          onClick={() => setCertifications(certifications.filter((_, i) => i !== idx))}
                          className="text-slate-300 hover:text-rose-600 opacity-0 group-hover/cert:opacity-100 transition-opacity p-0.5 no-print cursor-pointer"
                        >
                          <Trash2 size={9} />
                        </button>
                      </div>
                    ))}
                  </div>
                </section>

                {/* 7. WORK EXPERIENCE (OPTIONAL - ONLY IF USER HAS EXPERIENCE) */}
                {experience.length > 0 && (
                  <section className="space-y-2 group/sec relative">
                    <div className={`flex items-center justify-between pb-0.5 ${
                      templateTheme === 'executive'
                        ? 'border-b-2 border-slate-900'
                        : templateTheme === 'tech'
                        ? 'border-b border-dashed border-slate-800'
                        : 'border-b-[1.2px] border-slate-900'
                    }`}>
                      <h3 className="text-[11px] font-bold uppercase tracking-[0.03em] text-slate-950 leading-tight">
                        {templateTheme === 'tech' ? '// PROFESSIONAL EXPERIENCE' : 'WORK EXPERIENCE'}
                      </h3>
                      <div className="flex items-center gap-1.5 no-print">
                        <button
                          onClick={() => openAiRewriter('experience', 'Work Experience', experience)}
                          className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-1 px-1.5 py-0.5 bg-cyan-50/90 hover:bg-cyan-100 rounded border border-cyan-200/60 shadow-xs cursor-pointer transition-colors"
                          title="AI Polish Experience with STAR bullets"
                        >
                          <Sparkles size={10} className="text-cyan-600" />
                          <span>AI Polish</span>
                        </button>
                        <button
                          onClick={() =>
                            setExperience([
                              ...experience,
                              {
                                id: `exp-${Date.now()}`,
                                title: 'Machine Learning Engineer',
                                company: 'Tech Enterprise',
                                dates: '2023 - Present',
                                highlights: ['Engineered scalable pipelines improving throughput by 35%.'],
                              },
                            ])
                          }
                          className="text-[10px] text-cyan-800 hover:text-cyan-950 font-bold flex items-center gap-0.5 no-print cursor-pointer"
                        >
                          <Plus size={10} /> Add
                        </button>
                      </div>
                    </div>

                    <div className="space-y-2">
                      {experience.map((exp, expIdx) => (
                        <div key={exp.id || expIdx} className="space-y-1">
                          <div className="flex items-baseline justify-between">
                            <div className="flex items-center gap-1">
                              <input
                                type="text"
                                value={exp.title}
                                onChange={(e) => {
                                  const updated = [...experience]
                                  updated[expIdx].title = e.target.value
                                  setExperience(updated)
                                }}
                                className="font-bold text-[12.5px] text-slate-950 bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded"
                              />
                              <span className="text-slate-400 mx-0.5">|</span>
                              <input
                                type="text"
                                value={exp.company}
                                onChange={(e) => {
                                  const updated = [...experience]
                                  updated[expIdx].company = e.target.value
                                  setExperience(updated)
                                }}
                                className="text-[12px] font-semibold text-slate-700 bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded"
                              />
                            </div>
                            <input
                              type="text"
                              value={exp.dates}
                              onChange={(e) => {
                                const updated = [...experience]
                                updated[expIdx].dates = e.target.value
                                setExperience(updated)
                              }}
                              className="text-[12px] text-slate-700 font-medium text-right bg-transparent border-b border-transparent hover:border-slate-300 focus:border-cyan-600 focus:outline-none px-0.5 rounded w-32"
                            />
                          </div>

                          <ul className="space-y-1 pl-4">
                            {exp.highlights.map((h, hIdx) => (
                              <li key={hIdx} className="flex items-start gap-2 text-[12px] text-slate-800 leading-[1.35]">
                                <span className="text-slate-900 select-none flex-shrink-0 w-2.5 text-center leading-[1.35]">•</span>
                                <textarea
                                  rows={1}
                                  value={h}
                                  onChange={(e) => {
                                    const updated = [...experience]
                                    updated[expIdx].highlights[hIdx] = e.target.value
                                    setExperience(updated)
                                  }}
                                  onInput={(e) => {
                                    const t = e.currentTarget
                                    t.style.height = 'auto'
                                    t.style.height = t.scrollHeight + 'px'
                                  }}
                                  className="w-full bg-transparent border border-transparent hover:border-slate-200 focus:border-cyan-600 focus:bg-slate-50/50 rounded px-1 py-0.5 resize-none overflow-hidden focus:outline-none text-[12px] leading-[1.35] text-slate-800"
                                />
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* Subtile bottom button to add Experience if desired */}
                {experience.length === 0 && (
                  <div className="pt-2 border-t border-dashed border-slate-200 flex justify-center no-print">
                    <button
                      onClick={() =>
                        setExperience([
                          {
                            id: `exp-${Date.now()}`,
                            title: 'Machine Learning Engineer / Intern',
                            company: 'Technology Partner',
                            dates: '2024 - Present',
                            highlights: [
                              'Built and deployed end-to-end model inference pipelines; optimized throughput by 35% with asynchronous batching.',
                            ],
                          },
                        ])
                      }
                      className="text-[10px] font-semibold text-slate-400 hover:text-cyan-800 flex items-center gap-1 py-0.5 px-2 rounded hover:bg-slate-50 transition-colors cursor-pointer"
                    >
                      <Plus size={11} /> Add Experience / Internship Section
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* RAW DOCUMENT TEXT / MARKDOWN VIEW */
            <div className="w-[820px] h-full flex flex-col space-y-3">
              <div className="flex items-center justify-between bg-jarvis-surface/40 p-3 rounded-xl border border-jarvis-border/30">
                <div>
                  <h4 className="text-xs font-bold text-white">Raw Document Text / Markdown</h4>
                  <p className="text-[11px] text-jarvis-muted">
                    Syncs continuously with your visual sheet.
                  </p>
                </div>
                <button
                  onClick={() => setViewMode('sheet')}
                  className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-semibold transition-all cursor-pointer"
                >
                  Return to Visual Sheet
                </button>
              </div>

              <textarea
                value={rawTextContent}
                onChange={(e) => setRawTextContent(e.target.value)}
                className="flex-1 w-full bg-jarvis-surface/30 border border-jarvis-border/40 rounded-xl p-4 font-mono text-xs text-jarvis-light leading-relaxed focus:outline-none focus:border-cyan-500 resize-none scrollbar-thin"
              />
            </div>
          )}
        </main>

        {/* ========================================================================= */}
        {/* RIGHT: DEDICATED THREE-TAB SIDEBAR (COPILOT / ATS AUDIT / GAPS) */}
        {/* ========================================================================= */}
        <aside className="w-[420px] min-w-[360px] max-w-[460px] bg-jarvis-dark/95 border-l border-jarvis-border/40 flex flex-col flex-shrink-0 z-10 no-print">
          {/* Sidebar Tabs */}
          <div className="flex border-b border-jarvis-border/40 bg-jarvis-surface/20 text-xs font-semibold">
            <button
              onClick={() => setActiveSidebarTab('copilot')}
              className={`flex-1 py-2.5 flex items-center justify-center gap-1.5 border-b-2 transition-all cursor-pointer ${
                activeSidebarTab === 'copilot'
                  ? 'border-cyan-400 text-cyan-300 bg-cyan-500/10'
                  : 'border-transparent text-jarvis-muted hover:text-white'
              }`}
            >
              <Bot size={13} />
              <span>AI Copilot</span>
            </button>

            <button
              onClick={() => setActiveSidebarTab('ats')}
              className={`flex-1 py-2.5 flex items-center justify-center gap-1.5 border-b-2 transition-all cursor-pointer ${
                activeSidebarTab === 'ats'
                  ? 'border-emerald-400 text-emerald-300 bg-emerald-500/10'
                  : 'border-transparent text-jarvis-muted hover:text-white'
              }`}
            >
              <ShieldCheck size={13} className="text-emerald-400" />
              <span>ATS Tool</span>
            </button>

            <button
              onClick={() => setActiveSidebarTab('suggestions')}
              className={`flex-1 py-2.5 flex items-center justify-center gap-1.5 border-b-2 transition-all cursor-pointer ${
                activeSidebarTab === 'suggestions'
                  ? 'border-indigo-400 text-indigo-300 bg-indigo-500/10'
                  : 'border-transparent text-jarvis-muted hover:text-white'
              }`}
            >
              <Sparkles size={13} className="text-amber-400" />
              <span>Stand Out</span>
            </button>
          </div>

          {/* TAB 1: COPILOT CONVERSATIONAL CHAT (STREAMING) */}
          {activeSidebarTab === 'copilot' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Active Document Badge */}
              <div className="px-3 py-1.5 bg-jarvis-surface/40 border-b border-jarvis-border/30 flex items-center justify-between text-[11px]">
                <div className="flex items-center gap-1.5 text-cyan-300">
                  <FileText size={11} />
                  <span className="font-semibold">
                    Target: {targetJob?.title || 'Machine Learning Engineer'}
                  </span>
                </div>
                <span className="text-slate-400 text-[10px]">
                  {projects.length} projects • {certifications.length} certs
                </span>
              </div>

              {/* Messages Area */}
              <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5 scrollbar-thin">
                {chatMessages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex items-start gap-2 text-xs ${
                      msg.sender === 'user' ? 'justify-end' : 'justify-start'
                    }`}
                  >
                    {msg.sender === 'assistant' && (
                      <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center text-white flex-shrink-0 shadow-sm shadow-cyan-500/30">
                        <Bot size={12} />
                      </div>
                    )}

                    <div
                      className={`max-w-[85%] rounded-xl p-3 leading-relaxed space-y-2 ${
                        msg.sender === 'user'
                          ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-br-none'
                          : 'bg-jarvis-surface/60 border border-jarvis-border/40 text-jarvis-light rounded-bl-none'
                      }`}
                    >
                      <p className="whitespace-pre-wrap">{msg.text}</p>

                      {/* Interactive Insertion Suggestion Chips */}
                      {msg.suggestions && msg.suggestions.length > 0 && (
                        <div className="pt-2 border-t border-jarvis-border/20 space-y-1.5">
                          <span className="text-[10px] uppercase font-bold text-cyan-300 flex items-center gap-1">
                            <Sparkles size={10} /> Click to Apply into Canvas:
                          </span>
                          {msg.suggestions.map((sug, sIdx) => (
                            <button
                              key={sIdx}
                              onClick={() => {
                                if (sug.type === 'summary') {
                                  setSummary(sug.content)
                                } else if (sug.type === 'skill') {
                                  handleInsertSkill(sug.content)
                                } else if (sug.type === 'bullet') {
                                  handleInsertBullet(
                                    typeof sug.content === 'string' ? sug.content : sug.content.text
                                  )
                                } else if (sug.type === 'project') {
                                  handleInsertProject(sug.content)
                                }
                              }}
                              className="w-full text-left p-2 rounded-lg bg-jarvis-dark/80 hover:bg-cyan-950/40 border border-cyan-500/30 text-[11px] text-cyan-200 transition-all flex items-center justify-between gap-2 group cursor-pointer"
                            >
                              <span className="font-medium truncate">{sug.label}</span>
                              <Plus
                                size={12}
                                className="text-cyan-400 group-hover:scale-125 transition-transform flex-shrink-0"
                              />
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    {msg.sender === 'user' && (
                      <div className="w-6 h-6 rounded-full bg-slate-700 flex items-center justify-center text-white flex-shrink-0">
                        <User size={12} />
                      </div>
                    )}
                  </div>
                ))}

                {isCopilotThinking && (
                  <div className="flex items-center gap-2 text-xs text-jarvis-muted bg-jarvis-surface/40 p-2.5 rounded-xl border border-jarvis-border/20 w-fit">
                    <RefreshCw size={12} className="animate-spin text-cyan-400" />
                    <span>Copilot is streaming response in real-time...</span>
                  </div>
                )}
                <div ref={chatBottomRef} />
              </div>

              {/* Chat Input Box & Fast Action Shortcuts */}
              <div className="p-3 border-t border-jarvis-border/30 bg-jarvis-dark/80 space-y-2">
                <div className="flex gap-1.5 overflow-x-auto scrollbar-hide pb-0.5">
                  <button
                    onClick={() =>
                      handleSendCopilotMessage(
                        'Rewrite my summary to emphasize machine learning engineering, low latency, and LangGraph'
                      )
                    }
                    className="text-[10px] px-2 py-1 rounded bg-amber-500/15 text-amber-300 hover:bg-amber-500/25 border border-amber-500/30 whitespace-nowrap transition-all cursor-pointer"
                  >
                    ✨ Polish Summary
                  </button>
                  <button
                    onClick={() =>
                      handleSendCopilotMessage('Add top missing ATS keywords for this Machine Learning role')
                    }
                    className="text-[10px] px-2 py-1 rounded bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25 border border-cyan-500/30 whitespace-nowrap transition-all cursor-pointer"
                  >
                    ⚡ Add ATS Skills
                  </button>
                  <button
                    onClick={() =>
                      handleSendCopilotMessage(
                        'Rewrite the Olympics Trends project bullets using the STAR method with quantifiable metrics'
                      )
                    }
                    className="text-[10px] px-2 py-1 rounded bg-indigo-500/15 text-indigo-300 hover:bg-indigo-500/25 border border-indigo-500/30 whitespace-nowrap transition-all cursor-pointer"
                  >
                    🎯 STAR Bullets
                  </button>
                </div>

                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSendCopilotMessage()}
                    placeholder="Ask Copilot (e.g. Polish summary, rewrite bullet, add skills)..."
                    className="flex-1 text-xs p-2 rounded-lg bg-jarvis-surface/60 border border-jarvis-border/40 text-white placeholder-jarvis-muted/50 focus:outline-none focus:border-cyan-400"
                  />
                  <button
                    onClick={() => handleSendCopilotMessage()}
                    disabled={!chatInput.trim() || isCopilotThinking}
                    className="p-2 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 text-white hover:brightness-110 disabled:opacity-40 transition-all cursor-pointer"
                  >
                    <Send size={13} />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: DEDICATED ATS TOOL PANEL */}
          {activeSidebarTab === 'ats' && (
            <AtsToolPanel
              currentResumeText={rawTextContent}
              targetJobTitle={targetJob?.title || 'Machine Learning Engineer'}
              targetCompany={targetJob?.company || 'Target Employer'}
              targetJdDescription={targetJob?.description || ''}
              onAddSkill={handleInsertSkill}
              onUpdateSummary={(newSum) => setSummary(newSum)}
              onInsertBullet={(b) => handleInsertBullet(b)}
              onAskCopilot={(prompt) => {
                setActiveSidebarTab('copilot')
                handleSendCopilotMessage(prompt)
              }}
            />
          )}

          {/* TAB 3: STAND OUT & GAPS */}
          {activeSidebarTab === 'suggestions' && (
            <div className="flex-1 overflow-y-auto p-3.5 space-y-4 scrollbar-thin">
              {suggestionsLoading && (
                <div className="flex items-center gap-2 text-xs text-indigo-300 bg-indigo-500/10 p-2.5 rounded-xl border border-indigo-500/20">
                  <RefreshCw size={12} className="animate-spin text-indigo-400" />
                  <span>Analyzing target job description for standout gaps...</span>
                </div>
              )}

              {/* Meter */}
              <div className="p-3 rounded-xl bg-gradient-to-br from-indigo-950/50 to-jarvis-surface/80 border border-indigo-500/30 space-y-2">
                <div className="flex items-center justify-between text-xs font-bold">
                  <span className="text-amber-400">
                    Current Match: {Math.round(targetMatch?.score ?? 72)}%
                  </span>
                  <span className="text-emerald-400">Target Fit: 95%</span>
                </div>
                <div className="w-full h-2 rounded-full bg-jarvis-dark overflow-hidden flex">
                  <div style={{ width: `${targetMatch?.score ?? 72}%` }} className="h-full bg-amber-500/80" />
                  <div
                    style={{ width: `${Math.max(0, 95 - (targetMatch?.score ?? 72))}%` }}
                    className="h-full bg-gradient-to-r from-cyan-400 to-emerald-400 animate-pulse"
                  />
                </div>
                <p className="text-[11px] text-jarvis-muted leading-relaxed">
                  Adding missing keywords (PyTorch, Docker) and highlighting quantifiable latency metrics will boost your application into the top tier.
                </p>
              </div>

              {/* Missing ATS Skills */}
              {suggestionsData?.missing_skills && suggestionsData.missing_skills.length > 0 && (
                <div className="space-y-2">
                  <span className="text-[11px] font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1">
                    <Flame size={12} className="text-amber-400" />
                    Missing ATS Keywords ({suggestionsData.missing_skills.length})
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {suggestionsData.missing_skills.map((sObj: any, idx: number) => {
                      const name = sObj.name || sObj
                      return (
                        <button
                          key={idx}
                          onClick={() => handleInsertSkill(name)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-cyan-500/10 text-cyan-200 border border-cyan-500/30 hover:bg-cyan-500/20 transition-all cursor-pointer"
                        >
                          <span>{name}</span>
                          <Plus size={10} />
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Standout Projects */}
              {suggestionsData?.standout_projects && suggestionsData.standout_projects.length > 0 && (
                <div className="space-y-2.5">
                  <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1">
                    <Layers size={12} className="text-indigo-400" />
                    Recommended Standout Projects
                  </span>

                  {suggestionsData.standout_projects.map((proj: any, idx: number) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-jarvis-surface/40 border border-indigo-500/20 hover:border-indigo-500/40 transition-all space-y-1.5"
                    >
                      <h5 className="text-xs font-bold text-white leading-snug">{proj.title}</h5>
                      <p className="text-[11px] text-cyan-300/90">{proj.tagline}</p>
                      <p className="text-[11px] text-jarvis-muted leading-relaxed">{proj.architecture}</p>

                      <div className="pt-2 border-t border-jarvis-border/20 flex items-center justify-between">
                        <span className="text-[10px] text-emerald-400 font-semibold">{proj.metrics}</span>
                        <button
                          onClick={() => handleInsertProject(proj)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-all cursor-pointer"
                        >
                          <Plus size={11} /> + Insert Project
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </aside>
      </div>

      {/* Interactive AI Section Rewriter Modal */}
      <AiSectionRewriterModal
        isOpen={aiModal.isOpen}
        onClose={() => setAiModal((prev) => ({ ...prev, isOpen: false }))}
        sectionTitle={aiModal.sectionTitle}
        sectionId={aiModal.sectionId}
        currentContent={aiModal.currentContent}
        defaultTargetRole={targetJob?.title || 'Machine Learning Engineer'}
        targetJob={targetJob}
        resumeContext={{
          fullName,
          contactLocation,
          contactPhone,
          contactEmail,
          linkedinUrl,
          githubUrl,
          portfolioUrl,
          summary,
          education,
          projects,
          skillGroups,
          certifications,
          experience,
          rawTextContent,
        }}
        onApply={handleApplySectionRewrite}
      />
    </div>
  )
}

