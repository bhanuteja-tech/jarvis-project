import { motion } from 'framer-motion'
import { ShieldCheck, AlertTriangle, CheckCircle2, XCircle, FileSearch } from 'lucide-react'
import { useStore } from '../../store/useStore'

export function ValidationWorkspace() {
  const { validationReport } = useStore()

  if (!validationReport) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center">
        <div className="w-14 h-14 rounded-2xl bg-jarvis-accent/10 border border-jarvis-accent/20 flex items-center justify-center mb-4">
          <ShieldCheck className="w-7 h-7 text-jarvis-accent" />
        </div>
        <h3 className="text-base font-semibold text-white mb-2">No Validation Report Yet</h3>
        <p className="text-xs text-jarvis-muted/70 max-w-xs">
          Tailor a resume for any job to automatically run Phase 6 Truth Validation (T1–T10) and ATS Analysis (A1–A8).
        </p>
      </div>
    )
  }

  const rawOverall = String(validationReport.overall_status || validationReport.status || '').toUpperCase()
  const overallPassed = rawOverall === 'PASS' || rawOverall === 'PASSED' || validationReport.passed === true

  // Truth section mapping
  const truthObj = validationReport.truth || validationReport.truth_validation || {}
  let truthCheckList: { name: string; status: string; detail: string }[] = []
  if (Array.isArray(truthObj.checks)) {
    truthCheckList = truthObj.checks.map((c: any) => ({
      name: c.name || 'check',
      status: String(c.status || 'passed'),
      detail: c.detail || '',
    }))
  } else if (Array.isArray(truthObj)) {
    truthCheckList = truthObj.map((c: any) => ({
      name: c.name || 'check',
      status: String(c.status || 'passed'),
      detail: c.detail || '',
    }))
  } else if (typeof truthObj === 'object' && truthObj !== null) {
    truthCheckList = Object.entries(truthObj).map(([key, val]: [string, any]) => ({
      name: key,
      status: String(typeof val === 'object' ? val.status || val.passed || 'passed' : val),
      detail: typeof val === 'object' ? val.detail || val.message || '' : '',
    }))
  }

  // ATS section mapping
  const atsObj = validationReport.ats || validationReport.ats_validation || {}
  const atsMetrics = atsObj.metrics || validationReport.metrics || {}
  const reqCov = atsMetrics.required_coverage_pct ?? atsMetrics.required_coverage ?? atsObj.required_coverage
  const prefCov = atsMetrics.preferred_coverage_pct ?? atsMetrics.preferred_coverage ?? atsObj.preferred_coverage
  const respCov = atsMetrics.responsibility_token_coverage_pct ?? atsMetrics.keyword_coverage ?? atsObj.keyword_coverage

  const getStatusIcon = (status: string | boolean) => {
    const s = String(status).toUpperCase()
    const isPass = s === 'PASSED' || s === 'PASS' || status === true
    const isFail = s === 'FAILED' || s === 'FAIL' || status === false
    if (isPass) return <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
    if (isFail) return <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
    return <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
  }

  const getBadgeStyle = (status: string | boolean) => {
    const s = String(status).toUpperCase()
    const isPass = s === 'PASSED' || s === 'PASS' || status === true
    const isFail = s === 'FAILED' || s === 'FAIL' || status === false
    if (isPass) return 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
    if (isFail) return 'bg-rose-500/10 border-rose-500/30 text-rose-300'
    return 'bg-amber-500/10 border-amber-500/30 text-amber-300'
  }

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 scrollbar-hide">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-jarvis-accent" />
          <h3 className="text-sm font-semibold text-white">Truth & ATS Validation</h3>
        </div>
        <span className={`px-2.5 py-0.5 text-[10px] font-bold uppercase rounded-full border ${overallPassed ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' : 'bg-rose-500/20 text-rose-400 border-rose-500/40'}`}>
          {overallPassed ? 'VERIFIED PASS' : 'VALIDATION ISSUES'}
        </span>
      </div>

      {/* Summary Banner */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className={`p-4 rounded-xl border ${overallPassed ? 'bg-emerald-950/20 border-emerald-500/30' : 'bg-rose-950/20 border-rose-500/30'}`}
      >
        <div className="flex items-start gap-3">
          {overallPassed ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-400 mt-0.5 flex-shrink-0" />
          ) : (
            <XCircle className="w-5 h-5 text-rose-400 mt-0.5 flex-shrink-0" />
          )}
          <div>
            <h4 className="text-sm font-bold text-white">
              {overallPassed ? 'Zero Hallucinations Verified' : 'Truth Verification Alert'}
            </h4>
            <p className="text-xs text-jarvis-muted/90 mt-1 leading-relaxed">
              {overallPassed
                ? 'All claims, dates, and skills in the tailored resume strictly map to original candidate evidence.'
                : 'One or more truth constraints were not fully satisfied. Review details below.'}
            </p>
          </div>
        </div>
      </motion.div>

      {/* Truth Validation Section (T1-T10) */}
      <div className="space-y-2">
        <div className="flex items-center justify-between px-1">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-jarvis-accent flex items-center gap-1.5">
            <ShieldCheck size={14} /> Truth Checks (T1–T10)
          </h4>
          <span className="text-[10px] text-jarvis-muted">Read-Only Safety Guard</span>
        </div>

        <div className="space-y-1.5">
          {truthCheckList.map((check: any, idx: number) => {
            const nameStr = check.name || `check_${idx}`
            const label = nameStr.replace(/^t\d+_?/i, '').replace(/_/g, ' ')
            const status = check.status || 'passed'
            const detail = check.detail

            return (
              <motion.div
                key={nameStr + idx}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.03 }}
                className="p-2.5 rounded-lg bg-jarvis-surface/40 border border-jarvis-border/40 space-y-1"
              >
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] font-bold text-jarvis-accent/70 uppercase">
                      {nameStr.split('_')[0]}
                    </span>
                    <span className="text-jarvis-light font-medium capitalize">{label}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className={`px-2 py-0.5 text-[10px] font-medium rounded border ${getBadgeStyle(status)}`}>
                      {String(status).toUpperCase()}
                    </span>
                    {getStatusIcon(status)}
                  </div>
                </div>
                {detail && (
                  <p className="text-[11px] text-jarvis-muted/80 pl-6 leading-normal">{detail}</p>
                )}
              </motion.div>
            )
          })}
        </div>
      </div>

      {/* ATS Validation Section (A1-A8) */}
      {(reqCov !== undefined || prefCov !== undefined || respCov !== undefined) && (
        <div className="space-y-2 pt-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-cyan-400 px-1 flex items-center gap-1.5">
            <FileSearch size={14} /> ATS Compliance Metrics
          </h4>

          <div className="grid grid-cols-2 gap-2">
            {reqCov !== undefined && (
              <div className="p-3 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40">
                <p className="text-[10px] text-jarvis-muted uppercase tracking-wider font-semibold">Required Coverage</p>
                <p className="text-lg font-bold text-white mt-0.5">{reqCov}%</p>
              </div>
            )}
            {prefCov !== undefined && (
              <div className="p-3 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40">
                <p className="text-[10px] text-jarvis-muted uppercase tracking-wider font-semibold">Preferred Coverage</p>
                <p className="text-lg font-bold text-white mt-0.5">{prefCov}%</p>
              </div>
            )}
            {respCov !== undefined && (
              <div className="p-3 rounded-xl bg-jarvis-surface/40 border border-jarvis-border/40">
                <p className="text-[10px] text-jarvis-muted uppercase tracking-wider font-semibold">Responsibility Match</p>
                <p className="text-lg font-bold text-white mt-0.5">{respCov}%</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
