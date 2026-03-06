'use client'

import { useState } from 'react'

import { triggerCrossIdeaAnalysis, type CrossIdeaInsight } from '../../lib/api'

export function CrossIdeaInsights() {
  const [insights, setInsights] = useState<CrossIdeaInsight[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ran, setRan] = useState(false)

  const handleAnalyze = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await triggerCrossIdeaAnalysis()
      setInsights(result.insights)
      setRan(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed.')
    } finally {
      setLoading(false)
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
          onClick={() => void handleAnalyze()}
          disabled={loading}
          className="shrink-0 rounded-lg bg-[#b9eb10] px-3 py-1.5 text-xs font-bold text-[#1e1e1e] transition hover:bg-[#d4f542] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Analyzing…' : 'Analyze'}
        </button>
      </div>

      {error ? <p className="mt-3 text-xs text-red-600">{error}</p> : null}

      {ran && insights.length === 0 && !loading && !error ? (
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
                  {insight.idea_a_id} ↔ {insight.idea_b_id}
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
