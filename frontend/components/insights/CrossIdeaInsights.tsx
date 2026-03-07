'use client'

import { useEffect, useState } from 'react'

import {
  getCrossIdeaInsights,
  getCrossIdeaInsightsForIdea,
  type CrossIdeaInsightV2,
  type CrossIdeaInsight,
} from '../../lib/api'
import { CrossIdeaInsightList } from './CrossIdeaInsightList'

interface CrossIdeaInsightsProps {
  ideaId?: string | null
}

/**
 * Convert a legacy freeform insight into a V2 shape for unified rendering.
 * Fields that don't exist in the legacy format are filled with sensible defaults.
 */
const legacyToV2 = (legacy: CrossIdeaInsight, index: number): CrossIdeaInsightV2 => ({
  id: `legacy-${legacy.idea_a_id ?? ''}-${legacy.idea_b_id ?? ''}-${index}`,
  idea_a_id: legacy.idea_a_id ?? '',
  idea_b_id: legacy.idea_b_id ?? '',
  idea_a_title: legacy.idea_a_title,
  idea_b_title: legacy.idea_b_title,
  insight_type: 'evidence_overlap',
  summary: legacy.analysis ?? JSON.stringify(legacy),
  why_it_matters: '',
  recommended_action: 'review',
  confidence: null,
  similarity_score: null,
  created_at: new Date().toISOString(),
})

export function CrossIdeaInsights({ ideaId }: CrossIdeaInsightsProps = {}) {
  const [insights, setInsights] = useState<CrossIdeaInsightV2[]>([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchInsights = async () => {
    if (ideaId) {
      const result = await getCrossIdeaInsightsForIdea(ideaId)
      return result.data
    }
    // Fallback to legacy endpoint
    const result = await getCrossIdeaInsights()
    return result.insights.map(legacyToV2)
  }

  useEffect(() => {
    const run = async () => {
      try {
        const data = await fetchInsights()
        setInsights(data)
      } catch {
        // Silently fail on initial load — user can click Refresh
      } finally {
        setLoading(false)
      }
    }
    void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ideaId])

  const handleRefresh = async () => {
    setAnalyzing(true)
    setError(null)
    try {
      const data = await fetchInsights()
      setInsights(data)
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
          {analyzing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {error ? <p className="mt-3 text-xs text-red-600">{error}</p> : null}

      <div className="mt-4">
        <CrossIdeaInsightList insights={insights} loading={loading || analyzing} />
      </div>
    </div>
  )
}
