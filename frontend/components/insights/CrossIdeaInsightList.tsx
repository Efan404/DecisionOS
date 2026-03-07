'use client'

import React from 'react'
import type { CrossIdeaInsightV2 } from '../../lib/api'

export interface CrossIdeaInsightListProps {
  insights: CrossIdeaInsightV2[]
  loading?: boolean
}

const INSIGHT_TYPE_STYLES: Record<CrossIdeaInsightV2['insight_type'], { bg: string; text: string; label: string }> = {
  merge_candidate: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'Merge Candidate' },
  positioning_conflict: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', label: 'Positioning Conflict' },
  execution_reuse: { bg: 'bg-[#b9eb10]/20', text: 'text-[#b9eb10]', label: 'Execution Reuse' },
  shared_audience: { bg: 'bg-blue-500/20', text: 'text-blue-400', label: 'Shared Audience' },
  shared_capability: { bg: 'bg-purple-500/20', text: 'text-purple-400', label: 'Shared Capability' },
  evidence_overlap: { bg: 'bg-neutral-700', text: 'text-neutral-400', label: 'Evidence Overlap' },
}

const ACTION_LABELS: Record<CrossIdeaInsightV2['recommended_action'], string> = {
  review: 'Review',
  compare_feasibility: 'Compare Plans',
  reuse_scope: 'Reuse Scope',
  reuse_prd_requirements: 'Reuse Requirements',
  merge_ideas: 'Consider Merge',
  keep_separate: 'Keep Separate',
}

export function CrossIdeaInsightList({ insights, loading }: CrossIdeaInsightListProps) {
  if (loading) {
    return (
      <div className="py-4 text-sm text-[#1e1e1e]/50">
        Analyzing connections...
      </div>
    )
  }

  if (insights.length === 0) {
    return (
      <div className="py-4 text-xs text-[#1e1e1e]/40">
        No cross-idea insights found yet.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {insights.map((insight) => {
        const typeStyle = INSIGHT_TYPE_STYLES[insight.insight_type] ?? INSIGHT_TYPE_STYLES.evidence_overlap
        const actionLabel = ACTION_LABELS[insight.recommended_action] ?? 'Review'

        return (
          <div
            key={insight.id}
            className="rounded-lg border border-[#1e1e1e]/8 bg-[#f5f5f5] px-4 py-3"
          >
            {/* Header row: badge + related idea */}
            <div className="mb-2 flex items-center gap-2">
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${typeStyle.bg} ${typeStyle.text}`}
              >
                {typeStyle.label}
              </span>
              {(insight.idea_a_title || insight.idea_b_title) && (
                <span className="truncate text-[11px] font-bold tracking-wide text-[#1e1e1e]/50">
                  {insight.idea_a_title || insight.idea_a_id}
                  <span className="mx-1.5 text-[#b9eb10]">&harr;</span>
                  {insight.idea_b_title || insight.idea_b_id}
                </span>
              )}
            </div>

            {/* Summary */}
            <p className="text-xs leading-relaxed text-[#1e1e1e]/80">
              {insight.summary}
            </p>

            {/* Why it matters */}
            {insight.why_it_matters && (
              <p className="mt-1 text-[11px] leading-relaxed text-[#1e1e1e]/50">
                {insight.why_it_matters}
              </p>
            )}

            {/* Footer: action pill + confidence */}
            <div className="mt-2.5 flex items-center gap-2">
              <span className="rounded-md bg-[#b9eb10]/20 px-2 py-0.5 text-[11px] font-semibold text-[#1e1e1e]/70">
                {actionLabel}
              </span>
              {insight.confidence != null && (
                <span className="text-[11px] text-[#1e1e1e]/40">
                  {Math.round(insight.confidence * 100)}% confidence
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
