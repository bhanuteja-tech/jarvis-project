import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Activity,
  Lock,
  Mail,
  ArrowRight,
  ShieldCheck,
  Sparkles
} from 'lucide-react'

export function AuthPage() {
  const [isSignUp, setIsSignUp] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // Direct entry into /app
    navigate('/app')
  }

  const handleGuestEntry = () => {
    // Immediate instant access
    navigate('/app')
  }

  return (
    <div className="min-h-[85vh] flex items-center justify-center px-4 sm:px-6 lg:px-8 py-12">
      <div className="w-full max-w-md space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <Link to="/" className="inline-flex items-center gap-2 group">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 via-indigo-600 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-500/25 group-hover:scale-105 transition-transform">
              <Activity className="text-white" size={20} />
            </div>
            <span className="text-xl font-bold font-mono text-white tracking-wider">J.A.R.V.I.S</span>
          </Link>
          <h2 className="text-2xl font-extrabold text-white tracking-tight">
            {isSignUp ? 'Create Sovereign Account' : 'Welcome Back to JARVIS'}
          </h2>
          <p className="text-xs text-jarvis-muted">
            {isSignUp
              ? 'Access real-time voice, job radar, and truth-guarded tailoring.'
              : 'Sign in to access your sovereign career dashboard.'}
          </p>
        </div>

        {/* Auth Card */}
        <div className="p-6 sm:p-8 rounded-3xl glass-strong border border-jarvis-border/60 shadow-2xl space-y-6">
          {/* Guest / Instant Demo Access Button */}
          <div className="space-y-2">
            <button
              onClick={handleGuestEntry}
              className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-500 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-xs shadow-lg shadow-blue-500/25 flex items-center justify-center gap-2 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <Sparkles size={14} className="text-cyan-300" />
              <span>Instant Demo Access (Continue as Guest)</span>
              <ArrowRight size={14} />
            </button>
            <p className="text-[10px] text-center text-jarvis-muted font-mono">
              Zero login required · Instant session isolation
            </p>
          </div>

          <div className="relative flex py-1 items-center">
            <div className="flex-grow border-t border-jarvis-border/40" />
            <span className="flex-shrink mx-3 text-[10px] font-mono uppercase text-jarvis-muted">or continue with credentials</span>
            <div className="flex-grow border-t border-jarvis-border/40" />
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-medium text-jarvis-light block">Email Address</label>
              <div className="relative">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="engineer@company.com"
                  required
                  className="w-full px-3.5 py-2.5 rounded-xl bg-jarvis-surface/60 border border-jarvis-border/50 text-white placeholder-jarvis-muted/50 text-xs focus:outline-none focus:border-blue-500 transition-colors pl-9"
                />
                <Mail size={14} className="text-jarvis-muted absolute left-3 top-3" />
              </div>
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-jarvis-light">Password</label>
                {!isSignUp && (
                  <button type="button" className="text-[11px] text-cyan-400 hover:underline">
                    Forgot password?
                  </button>
                )}
              </div>
              <div className="relative">
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  className="w-full px-3.5 py-2.5 rounded-xl bg-jarvis-surface/60 border border-jarvis-border/50 text-white placeholder-jarvis-muted/50 text-xs focus:outline-none focus:border-blue-500 transition-colors pl-9"
                />
                <Lock size={14} className="text-jarvis-muted absolute left-3 top-3" />
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-2.5 rounded-xl bg-jarvis-surface hover:bg-jarvis-surface/80 text-white font-medium text-xs border border-jarvis-border/60 transition-all flex items-center justify-center gap-2"
            >
              <span>{isSignUp ? 'Create Account' : 'Sign In'}</span>
              <ArrowRight size={13} />
            </button>
          </form>

          {/* Toggle between sign in & sign up */}
          <div className="text-center pt-2">
            <button
              onClick={() => setIsSignUp(!isSignUp)}
              className="text-xs text-jarvis-muted hover:text-white transition-colors"
            >
              {isSignUp ? (
                <>Already have an account? <span className="text-cyan-400 font-semibold">Sign In</span></>
              ) : (
                <>Don't have an account? <span className="text-cyan-400 font-semibold">Create one</span></>
              )}
            </button>
          </div>
        </div>

        {/* Security / Sovereignty Notice */}
        <div className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20 flex items-center gap-2 text-xs text-emerald-300">
          <ShieldCheck size={16} className="text-emerald-400 shrink-0" />
          <span className="text-[11px]">All profile and resume data is PII-quarantined and sovereign.</span>
        </div>
      </div>
    </div>
  )
}
