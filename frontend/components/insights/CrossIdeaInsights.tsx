'use client'

import { useEffect, useState } from 'react'

import { getCrossIdeaInsights, type CrossIdeaInsight } from '../../lib/api'
import { HoverCard } from '../common/HoverCard'

export function CrossIdeaInsights() {
  const [insights, setInsights] = useState<CrossIdeaInsight[]>([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const run = async () => {
      try {
        const result = await getCrossIdeaInsights()
        setInsights(result.insights)
      } catch {
        // Silently fail on initial load — user can click Analyze
      } finally {
        setLoading(false)
      }
    }
    void run()
  }, [])

  const handleRefresh = async () => {
    setAnalyzing(true)
    setError(null)
    try {
      const result = await getCrossIdeaInsights()
      setInsights(result.insights)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load insights.')
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="rounded-xl border border-[#1e1e1e]/10 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-[#1e1e1e]">Cross-Idea Insights</h2>
          <p className="mt-0.5 text-xs text-[#1e1e1e]/50">
            Discover patterns and connections across your ideas.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleRefresh()}
          disabled={analyzing}
          className="shrink-0 rounded-lg bg-[#b9eb10] px-3 py-1.5 text-xs font-bold text-[#1e1e1e] transition hover:bg-[#d4f542] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {analyzing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error ? <p className="mt-3 text-xs text-red-600">{error}</p> : null}

      {!loading && insights.length === 0 && !analyzing && !error ? (
        <p className="mt-4 text-xs text-[#1e1e1e]/40">
          No cross-idea connections found yet. Add more ideas to unlock insights.
        </p>
      ) : null}

      {insights.length > 0 && (
        <ul className="mt-4 space-y-3">
          {insights.map((insight, i) => (
            <li
              key={`${insight.idea_a_id ?? ''}-${insight.idea_b_id ?? ''}-${i}`}
              className="rounded-lg border border-[#1e1e1e]/8 bg-[#f5f5f5] px-4 py-3"
            >
              {insight.idea_a_id && insight.idea_b_id ? (
                <p className="mb-1 text-[11px] font-bold tracking-wide text-[#1e1e1e]/40 uppercase">
                  <HoverCard align="left" trigger={
                    <span className="cursor-default underline decoration-dotted decoration-[#1e1e1e]/20 underline-offset-2">
                      {insight.idea_a_id.length > 12 ? `${insight.idea_a_id.slice(0, 12)}…` : insight.idea_a_id}
                    </span>
                  }>
                    <span className="break-all font-mono text-[11px]">{insight.idea_a_id}</span>
                  </HoverCard>
                  {' ↔ '}
                  <HoverCard align="left" trigger={
                    <span className="cursor-default underline decoration-dotted decoration-[#1e1e1e]/20 underline-offset-2">
                      {insight.idea_b_id.length > 12 ? `${insight.idea_b_id.slice(0, 12)}…` : insight.idea_b_id}
                    </span>
                  }>
                    <span className="break-all font-mono text-[11px]">{insight.idea_b_id}</span>
                  </HoverCard>
                </p>
              ) : null}
              <p className="text-xs leading-relaxed text-[#1e1e1e]/70">
                {insight.analysis ?? JSON.stringify(insight)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
