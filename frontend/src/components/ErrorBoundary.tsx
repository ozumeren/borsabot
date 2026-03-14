import { Component, ReactNode } from 'react'

interface Props { children: ReactNode; fallback?: ReactNode }
interface State { error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (this.state.error) {
      return this.props.fallback ?? (
        <div className="card text-danger text-sm p-6 space-y-2">
          <div className="font-bold">Bir hata oluştu</div>
          <div className="text-muted font-mono text-xs">{this.state.error.message}</div>
          <button
            className="btn-muted text-xs mt-2"
            onClick={() => this.setState({ error: null })}
          >
            Tekrar Dene
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
