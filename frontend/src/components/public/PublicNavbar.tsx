import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Activity, Menu, X, ArrowRight, Mic, Sparkles } from 'lucide-react'

const NAV_LINKS = [
  { label: 'Features', to: '/features' },
  { label: 'How It Works', to: '/how-it-works' },
  { label: 'Voice Agent', to: '/voice-agent', badge: 'Voice' },
  { label: 'Career Intelligence', to: '/career-intelligence' },
  { label: 'Architecture', to: '/architecture' },
  { label: 'Docs', to: '/docs' },
]

export function PublicNavbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Close mobile drawer on route change
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? 'glass-strong border-b border-jarvis-border/40 py-3 shadow-2xl shadow-black/40'
          : 'bg-transparent py-5 border-b border-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between">
        {/* Brand Logo */}
        <Link to="/" className="flex items-center gap-3 group focus:outline-none">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 via-indigo-600 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-500/25 group-hover:scale-105 transition-transform">
            <Activity className="text-white" size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold text-white tracking-wider font-mono">J.A.R.V.I.S</span>
              <span className="text-[10px] uppercase font-semibold tracking-widest px-1.5 py-0.5 rounded bg-blue-500/10 text-cyan-400 border border-cyan-500/30">
                Agentic OS
              </span>
            </div>
            <p className="text-[10px] text-jarvis-muted tracking-widest uppercase font-medium">Career Intelligence</p>
          </div>
        </Link>

        {/* Desktop Navigation Links */}
        <nav className="hidden lg:flex items-center gap-1 xl:gap-2">
          {NAV_LINKS.map((item) => {
            const active = location.pathname === item.to
            return (
              <Link
                key={item.to}
                to={item.to}
                className={`relative px-3 py-1.5 rounded-lg text-xs font-medium tracking-wide transition-all ${
                  active
                    ? 'text-white bg-jarvis-surface/70 border border-blue-500/30'
                    : 'text-jarvis-muted hover:text-white hover:bg-jarvis-surface/40'
                }`}
              >
                <span className="flex items-center gap-1.5">
                  {item.label}
                  {item.badge && (
                    <span className="flex items-center gap-0.5 text-[9px] font-semibold px-1 py-0.2 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                      <Mic size={9} />
                      {item.badge}
                    </span>
                  )}
                </span>
                {active && (
                  <motion.div
                    layoutId="activeNav"
                    className="absolute -bottom-1 left-2 right-2 h-0.5 bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full"
                  />
                )}
              </Link>
            )
          })}
        </nav>

        {/* Right Actions */}
        <div className="hidden md:flex items-center gap-2.5">
          <Link
            to="/demo"
            className="px-3 py-1.5 rounded-lg text-xs font-medium text-jarvis-muted hover:text-white bg-jarvis-surface/40 hover:bg-jarvis-surface border border-jarvis-border/40 transition-all flex items-center gap-1.5"
          >
            <Sparkles size={12} className="text-cyan-400" />
            <span>Interactive Demo</span>
          </Link>
          <Link
            to="/login"
            className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-jarvis-light hover:text-white hover:bg-jarvis-surface/60 transition-all"
          >
            Sign In
          </Link>
          <Link
            to="/app"
            className="group relative inline-flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-500 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-blue-500/25 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <span>Launch App</span>
            <ArrowRight size={13} className="group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>

        {/* Mobile menu button */}
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden p-2 rounded-lg text-jarvis-muted hover:text-white hover:bg-jarvis-surface focus:outline-none"
          aria-label="Toggle Navigation Menu"
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile Drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="md:hidden glass-strong border-b border-jarvis-border/40 overflow-hidden"
          >
            <div className="px-4 pt-3 pb-6 space-y-2">
              {NAV_LINKS.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`block px-3 py-2 rounded-lg text-sm font-medium ${
                    location.pathname === item.to
                      ? 'bg-blue-600/20 text-white border border-blue-500/30'
                      : 'text-jarvis-muted hover:text-white hover:bg-jarvis-surface/50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span>{item.label}</span>
                    {item.badge && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                        {item.badge}
                      </span>
                    )}
                  </div>
                </Link>
              ))}
              <div className="pt-3 border-t border-jarvis-border/30 grid grid-cols-2 gap-2">
                <Link
                  to="/demo"
                  className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium text-white bg-jarvis-surface border border-jarvis-border"
                >
                  <Sparkles size={12} className="text-cyan-400" />
                  <span>Demo</span>
                </Link>
                <Link
                  to="/login"
                  className="flex items-center justify-center px-3 py-2 rounded-lg text-xs font-medium text-white bg-jarvis-surface/60 border border-jarvis-border/40"
                >
                  Sign In
                </Link>
              </div>
              <Link
                to="/app"
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 text-white text-xs font-semibold shadow-lg shadow-blue-500/20 mt-2"
              >
                <span>Launch JARVIS App</span>
                <ArrowRight size={14} />
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  )
}
