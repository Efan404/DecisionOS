'use client'

import { useState } from 'react'

import { CompetitorCardList } from './CompetitorCardList'
import { MarketSignalsPanel } from './MarketSignalsPanel'
import { useMarketEvidence } from './useMarketEvidence'

interface MarketEvidencePanelProps {
  ideaId: string | null | undefined
  /** Start collapsed (default: true) */
  defaultCollapsed?: boolean
}

export function MarketEvidencePanel({
  ideaId,
  defaultCollapsed = true,
}: MarketEvidencePanelProps) {
  const { competitors, signals, loadingCompetitors, loadingSignals } =
    useMarketEvidence(ideaId)
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  const totalItems = competitors.length + signals.length
  const isLoading = loadingCompetitors || loadingSignals

  return (
    <section className="rounded-xl border border-[#1e1e1e]/8 bg-[#f5f5f5]">
      <button
        type="button"
        onClick={() => setCollapsed((prev) => !prev)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-medium tracking-wide text-[#1e1e1e]/60 uppercase">
            Market Evidence
          </h3>
          {!isLoading && totalItems > 0 && (
            <span className="rounded-full bg-[#b9eb10]/20 px-2 py-0.5 text-xs font-medium text-[#1e1e1e]/60">
              {totalItems}
            </span>
          )}
        </div>
        <svg
          className={`h-4 w-4 text-[#1e1e1e]/40 transition-transform ${
            collapsed ? '' : 'rotate-180'
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {!collapsed && (
        <div className="space-y-4 px-4 pb-4">
          {/* Competitors */}
          <div>
            <h4 className="mb-2 text-xs font-medium text-[#1e1e1e]/50">Competitors</h4>
            <CompetitorCardList
              competitors={competitors}
              loading={loadingCompetitors}
            />
          </div>

          {/* Signals */}
          <div>
            <h4 className="mb-2 text-xs font-medium text-[#1e1e1e]/50">Market Signals</h4>
            <MarketSignalsPanel signals={signals} loading={loadingSignals} />
          </div>
        </div>
      )}
    </section>
  )
}
