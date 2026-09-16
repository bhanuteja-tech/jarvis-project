import { Component, ErrorInfo, ReactNode } from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('JARVIS UI Render Error:', error, errorInfo)
    this.setState({ errorInfo })
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="h-full w-full flex items-center justify-center p-6 bg-jarvis-dark text-jarvis-light">
          <div className="max-w-md w-full p-6 rounded-2xl bg-jarvis-surface/60 border border-red-500/30 text-center space-y-4 shadow-2xl">
            <div className="w-12 h-12 mx-auto rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400">
              <AlertCircle size={24} />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Something went wrong</h3>
              <p className="text-xs text-jarvis-muted mt-1 leading-relaxed">
                An unexpected component rendering error occurred. The application recovered safely.
              </p>
            </div>
            {this.state.error && (
              <div className="p-3 rounded-lg bg-jarvis-darker/60 border border-jarvis-border/40 text-left overflow-x-auto max-h-32">
                <p className="text-[11px] font-mono text-red-300 whitespace-pre-wrap">
                  {this.state.error.toString()}
                </p>
              </div>
            )}
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null, errorInfo: null })
                window.location.reload()
              }}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-jarvis-accent text-jarvis-dark rounded-xl hover:bg-jarvis-accent/90 transition-all shadow-lg shadow-jarvis-accent/10"
            >
              <RefreshCw size={14} />
              Reload Application
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
