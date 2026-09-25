import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ScrollToTop } from './components/ScrollToTop'
import { PublicLayout } from './components/public/PublicLayout'
import { LandingPage } from './pages/LandingPage'
import { FeaturesPage } from './pages/FeaturesPage'
import { HowItWorksPage } from './pages/HowItWorksPage'
import { VoiceAgentPage } from './pages/VoiceAgentPage'
import { CareerIntelligencePage } from './pages/CareerIntelligencePage'
import { ArchitecturePage } from './pages/ArchitecturePage'
import { AboutPage } from './pages/AboutPage'
import { DocsPage } from './pages/DocsPage'
import { AuthPage } from './pages/AuthPage'
import { DashboardApp } from './pages/DashboardApp'
import { ComputerDashboardApp } from './pages/ComputerDashboardApp'

export default function App() {
  return (
    <BrowserRouter>
      <ScrollToTop />
      <Routes>
        {/* Public Website Routes wrapped with PublicLayout */}
        <Route element={<PublicLayout />}>
          <Route path="/" element={<LandingPage />} />
          <Route path="/features" element={<FeaturesPage />} />
          <Route path="/how-it-works" element={<HowItWorksPage />} />
          <Route path="/voice-agent" element={<VoiceAgentPage />} />
          <Route path="/career-intelligence" element={<CareerIntelligencePage />} />
          <Route path="/architecture" element={<ArchitecturePage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/docs" element={<DocsPage />} />
          <Route path="/login" element={<AuthPage />} />
          <Route path="/signup" element={<AuthPage />} />
          <Route path="/demo" element={<LandingPage />} />
        </Route>

        {/* Two completely separate application pages: /app/career and /app/computer */}
        <Route path="/app/career" element={<DashboardApp />} />
        <Route path="/app/computer" element={<ComputerDashboardApp />} />

        {/* Backward-compatible redirects */}
        <Route path="/app" element={<Navigate to="/app/career" replace />} />
        <Route path="/dashboard" element={<Navigate to="/app/career" replace />} />
        <Route path="/computer" element={<Navigate to="/app/computer" replace />} />

        {/* Fallback to Home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
