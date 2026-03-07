'use client'

import { MarketSignal } from '../../lib/market-evidence'

interface MarketSignalsPanelProps {
  signals: MarketSignal[]
  loading?: boolean
}

const SEVERITY_STYLES = {
  high: 'bg-red-500/20 text-red-400',
  medium: 'bg-yellow-500/20 text-yellow-400',
  low: 'bg-neutral-700 text-neutral-400',
} as const

const SIGNAL_TYPE_LABELS: Record<MarketSignal['signal_type'], string> = {
  competitor_update: 'Competitor Update',
  market_news: 'Market News',
  community_buzz: 'Community Buzz',
  pricing_change: 'Pricing Change',
}

export function MarketSignalsPanel({ signals, loading }: MarketSignalsPanelProps) {
  if (loading) {
    return <div className="text-neutral-500 text-sm">Loading signals...</div>
  }

  if (signals.length === 0) {
    return <div className="text-neutral-500 text-sm py-4">No market signals detected yet.</div>
  }

  return (
    <div className="space-y-3">
      {signals.map((signal) => (
        <div
          key={signal.id}
          className="bg-[#1e1e1e] rounded-lg p-4 border border-neutral-800"
        >
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${SEVERITY_STYLES[signal.severity]}`}
            >
              {signal.severity}
            </span>
            <span className="text-neutral-500 text-xs">
              {SIGNAL_TYPE_LABELS[signal.signal_type]}
            </span>
          </div>
          <h4 className="text-white text-sm font-medium mb-1">{signal.title}</h4>
          <p className="text-neutral-400 text-xs">{signal.summary}</p>
          <p className="text-neutral-600 text-xs mt-2">
            {new Date(signal.detected_at).toLocaleDateString()}
          </p>
        </div>
      ))}
    </div>
  )
}
