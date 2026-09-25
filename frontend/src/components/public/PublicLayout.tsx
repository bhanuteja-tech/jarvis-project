import { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { PublicNavbar } from './PublicNavbar'
import { PublicFooter } from './PublicFooter'

interface PublicLayoutProps {
  children?: ReactNode
}

export function PublicLayout({ children }: PublicLayoutProps) {
  return (
    <div className="min-h-screen bg-jarvis-darker text-jarvis-light flex flex-col relative overflow-x-hidden selection:bg-blue-500/30 selection:text-cyan-200">
      {/* Ambient background glows */}
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
        <div className="absolute top-[-10%] left-1/2 -translate-x-1/2 w-[1000px] h-[550px] bg-gradient-to-b from-blue-600/15 via-cyan-500/10 to-transparent blur-[120px] rounded-full" />
        <div className="absolute top-[35%] right-[-10%] w-[600px] h-[600px] bg-violet-600/10 blur-[140px] rounded-full" />
        <div className="absolute bottom-[-10%] left-[-10%] w-[600px] h-[600px] bg-blue-600/10 blur-[130px] rounded-full" />
        {/* Subtle grid pattern */}
        <div className="absolute inset-0 tech-grid-bg opacity-30" />
      </div>

      {/* Navigation Header */}
      <PublicNavbar />

      {/* Main Public Page Content */}
      <main className="flex-1 relative z-10 pt-20">
        {children || <Outlet />}
      </main>

      {/* Footer */}
      <PublicFooter />
    </div>
  )
}
