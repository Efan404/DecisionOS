'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { AgentThoughtStream, useAgentThoughts } from '../agent/AgentThoughtStream'
import { listMarketInsightsForIdea, streamMarketInsight } from '../../lib/api'
import { useIdeasStore } from '../../lib/ideas-store'
import type { MarketInsightRecord } from '../../lib/schemas'

// ── Helpers ──────────────────────────────────────────────────────────────────

const formatDate = (iso: string): string => {
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return iso
  }
}

// ── Insight Card ─────────────────────────────────────────────────────────────

function InsightCard({ insight }: { insight: MarketInsightRecord }) {
  return (
    <div className="rounded-xl border border-[#1e1e1e]/10 bg-[#f5f5f5] px-5 py-4 shadow-sm">
      {/* Timestamp */}
      <p className="mb-3 text-[11px] font-bold tracking-wide text-[#1e1e1e]/40 uppercase">
        {formatDate(insight.generated_at)}
      </p>

      {/* Summary */}
      <div className="mb-3">
        <p className="mb-1 text-[11px] font-bold tracking-widest text-[#1e1e1e]/50 uppercase">
          Summary
        </p>
        <p className="text-sm leading-relaxed text-[#1e1e1e]">{insight.summary}</p>
      </div>

      {/* Decision Impact */}
      <div className="mb-3">
        <p className="mb-1 text-[11px] font-bold tracking-widest text-[#1e1e1e]/50 uppercase">
          Decision Impact
        </p>
        <p className="text-sm leading-relaxed text-[#1e1e1e]/80">{insight.decision_impact}</p>
      </div>

      {/* Recommended Actions */}
      {insight.recommended_actions.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-[11px] font-bold tracking-widest text-[#1e1e1e]/50 uppercase">
            Recommended Actions
          </p>
          <ul className="space-y-1">
            {insight.recommended_actions.map((action, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-[#1e1e1e]/80">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#b9eb10]" />
                {action}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Signal count */}
      <p className="mt-2 text-[11px] text-[#1e1e1e]/40">
        Based on {insight.signal_count} signal{insight.signal_count !== 1 ? 's' : ''}
      </p>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export function InsightsPage() {
  const ideas = useIdeasStore((state) => state.ideas)
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)

  // Selected idea defaults to activeIdeaId or first idea
  const [selectedIdeaId, setSelectedIdeaId] = useState<string>(() => {
    return activeIdeaId ?? ideas[0]?.id ?? ''
  })

  const [insights, setInsights] = useState<MarketInsightRecord[]>([])
  const [loadingInsights, setLoadingInsights] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { thoughts, addThought, reset: resetThoughts } = useAgentThoughts()
  const abortRef = useRef<AbortController | null>(null)

  // Load existing insights whenever selected idea changes
  const loadInsights = useCallback(async (ideaId: string) => {
    if (!ideaId) return
    setLoadingInsights(true)
    setError(null)
    try {
      const data = await listMarketInsightsForIdea(ideaId)
      setInsights(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load insights.')
    } finally {
      setLoadingInsights(false)
    }
  }, [])

  useEffect(() => {
    void loadInsights(selectedIdeaId)
  }, [selectedIdeaId, loadInsights])

  // Sync selectedIdeaId when activeIdeaId changes externally (and component hasn't been interacted with)
  useEffect(() => {
    if (activeIdeaId && !selectedIdeaId) {
      setSelectedIdeaId(activeIdeaId)
    }
  }, [activeIdeaId, selectedIdeaId])

  const handleAnalyze = async () => {
    if (!selectedIdeaId || analyzing) return

    // Cancel any in-flight request
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setAnalyzing(true)
    setError(null)
    resetThoughts()

    try {
      let newInsight: MarketInsightRecord | null = null

      await streamMarketInsight(selectedIdeaId, controller.signal, {
        onAgentThought: (data) => addThought(data),
        onDone: (data) => {
          const payload = data as {
            insight_id: string
            summary: string
            decision_impact: string
            recommended_actions: string[]
            signal_count: number
            generated_at: string
          }
          // Build a local record so we can prepend it immediately
          newInsight = {
            id: payload.insight_id ?? `local-${Date.now()}`,
            idea_id: selectedIdeaId,
            summary: payload.summary ?? '',
            decision_impact: payload.decision_impact ?? '',
            recommended_actions: payload.recommended_actions ?? [],
            signal_count: payload.signal_count ?? 0,
            generated_at: payload.generated_at ?? new Date().toISOString(),
          }
        },
        onError: (err) => {
          setError(err instanceof Error ? err.message : 'Analysis failed.')
        },
      })

      if (newInsight) {
        setInsights((prev) => [newInsight!, ...prev])
      }

      // Reload from server to get the persisted record with real signal_count/id
      await loadInsights(selectedIdeaId)
    } catch (err) {
      if ((err as { name?: string }).name !== 'AbortError') {
        setError(err instanceof Error ? err.message : 'Analysis failed. Please try again.')
      }
    } finally {
      setAnalyzing(false)
    }
  }

  const selectedIdea = ideas.find((i) => i.id === selectedIdeaId)

  return (
    <main className="min-h-[400px] p-6">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-[#1e1e1e]">Market Insights</h1>
          <p className="mt-0.5 text-xs text-[#1e1e1e]/50">
            AI-generated market intelligence for your ideas
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Idea selector */}
          {ideas.length > 1 && (
            <select
              value={selectedIdeaId}
              onChange={(e) => setSelectedIdeaId(e.target.value)}
              disabled={analyzing}
              className="rounded-lg border border-[#1e1e1e]/12 bg-white px-3 py-1.5 text-sm text-[#1e1e1e] shadow-sm focus:ring-2 focus:ring-[#b9eb10] focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            >
              {ideas.map((idea) => (
                <option key={idea.id} value={idea.id}>
                  {idea.title}
                </option>
              ))}
            </select>
          )}

          {/* Analyze button */}
          <button
            type="button"
            onClick={() => void handleAnalyze()}
            disabled={analyzing || !selectedIdeaId}
            className="rounded-lg bg-[#b9eb10] px-4 py-1.5 text-sm font-bold text-[#1e1e1e] shadow-sm transition hover:bg-[#d4f542] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {analyzing ? 'Analyzing\u2026' : 'Analyze'}
          </button>
        </div>
      </div>

      {/* Selected idea label (when only one idea) */}
      {ideas.length === 1 && selectedIdea && (
        <p className="mb-4 text-xs text-[#1e1e1e]/50">
          Analyzing: <span className="font-semibold text-[#1e1e1e]">{selectedIdea.title}</span>
        </p>
      )}

      {/* ── Agent Thought Stream ─────────────────────────────────────────────── */}
      {(analyzing || thoughts.length > 0) && (
        <div className="mb-5">
          <AgentThoughtStream thoughts={thoughts} isActive={analyzing} />
        </div>
      )}

      {/* ── Error state ──────────────────────────────────────────────────────── */}
      {error && (
        <div className="mb-5 rounded-lg border border-red-300 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* ── Insight list ─────────────────────────────────────────────────────── */}
      {loadingInsights ? (
        <div className="py-8 text-center text-sm text-[#1e1e1e]/40">Loading insights&hellip;</div>
      ) : insights.length === 0 && !analyzing ? (
        <div className="rounded-xl border border-dashed border-[#1e1e1e]/15 bg-[#f5f5f5] px-6 py-12 text-center">
          <p className="text-sm font-semibold text-[#1e1e1e]/50">No market insights yet</p>
          <p className="mt-1 text-xs text-[#1e1e1e]/35">
            Click &ldquo;Analyze&rdquo; to generate your first market insight for this idea.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {insights.map((insight) => (
            <InsightCard key={insight.id} insight={insight} />
          ))}
        </div>
      )}
    </main>
  )
}
