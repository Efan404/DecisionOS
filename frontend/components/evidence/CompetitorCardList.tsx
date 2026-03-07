'use client'

import { CompetitorCard } from '../../lib/market-evidence'

interface CompetitorCardListProps {
  competitors: CompetitorCard[]
  loading?: boolean
}

export function CompetitorCardList({ competitors, loading }: CompetitorCardListProps) {
  if (loading) {
    return <div className="text-neutral-500 text-sm">Loading competitors...</div>
  }

  if (competitors.length === 0) {
    return <div className="text-neutral-500 text-sm py-4">No competitors discovered yet.</div>
  }

  return (
    <div className="space-y-3">
      {competitors.map((comp) => (
        <div key={comp.id} className="bg-[#1e1e1e] rounded-lg p-4 border border-neutral-800">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-white font-medium text-sm">{comp.name}</h4>
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                comp.status === 'tracked'
                  ? 'bg-[#b9eb10]/20 text-[#b9eb10]'
                  : comp.status === 'candidate'
                    ? 'bg-neutral-700 text-neutral-300'
                    : 'bg-neutral-800 text-neutral-500'
              }`}
            >
              {comp.status}
            </span>
          </div>
          {comp.category && <p className="text-neutral-400 text-xs mb-2">{comp.category}</p>}
          {comp.latest_snapshot && (
            <div className="flex gap-3 text-xs">
              {comp.latest_snapshot.quality_score != null && (
                <div>
                  <span className="text-neutral-500">Quality</span>{' '}
                  <span className="text-[#b9eb10]">
                    {comp.latest_snapshot.quality_score.toFixed(1)}
                  </span>
                </div>
              )}
              {comp.latest_snapshot.traction_score != null && (
                <div>
                  <span className="text-neutral-500">Traction</span>{' '}
                  <span className="text-[#b9eb10]">
                    {comp.latest_snapshot.traction_score.toFixed(1)}
                  </span>
                </div>
              )}
              {comp.latest_snapshot.relevance_score != null && (
                <div>
                  <span className="text-neutral-500">Relevance</span>{' '}
                  <span className="text-[#b9eb10]">
                    {comp.latest_snapshot.relevance_score.toFixed(1)}
                  </span>
                </div>
              )}
            </div>
          )}
          <div className="text-neutral-500 text-xs mt-2">
            {comp.evidence_count} evidence source{comp.evidence_count !== 1 ? 's' : ''}
          </div>
        </div>
      ))}
    </div>
  )
}
