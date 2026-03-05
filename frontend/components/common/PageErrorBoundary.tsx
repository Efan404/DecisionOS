'use client'

import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { error: Error | null }

export class PageErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('PageErrorBoundary caught:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <main className="mx-auto mt-12 max-w-md px-6 text-center">
          <h1 className="text-lg font-semibold text-[#1e1e1e]">Something went wrong</h1>
          <p className="mt-2 text-sm text-[#1e1e1e]/50">{this.state.error.message}</p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="mt-4 rounded-lg border border-[#1e1e1e]/15 px-4 py-2 text-sm font-medium text-[#1e1e1e]/70 transition hover:bg-[#f5f5f5]"
          >
            Try Again
          </button>
        </main>
      )
    }
    return this.props.children
  }
}
