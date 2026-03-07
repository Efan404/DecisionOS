'use client'

import { useEffect, useState } from 'react'

import { getUserPatterns } from '../../lib/api'
import { HoverCard } from '../common/HoverCard'

/** Truncate long values for the pill badge — full text shown in hover card */
const truncate = (s: string, max = 40): string =>
  s.length > max ? s.slice(0, max).trimEnd() + '…' : s

export function UserPatternCard() {
  const [preferences, setPreferences] = useState<Record<string, string> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const run = async () => {
      try {
        const result = await getUserPatterns()
        setPreferences(result.preferences)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load patterns.')
      } finally {
        setLoading(false)
      }
    }
    void run()
  }, [])

  const entries = preferences ? Object.entries(preferences) : []

  return (
    <div>
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-[#f5f5f5]" />
          ))}
        </div>
      ) : error ? (
        <p className="text-xs text-red-600">{error}</p>
      ) : entries.length === 0 ? (
        <p className="text-xs text-[#1e1e1e]/40">
          No patterns learned yet. Make decisions across multiple ideas to build your profile.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {entries.map(([key, value]) => (
            <li
              key={key}
              className="flex flex-col gap-2 rounded-lg border border-[#1e1e1e]/8 bg-[#f5f5f5] px-3 py-3"
            >
              <span className="text-[10px] font-semibold tracking-wider text-[#1e1e1e]/40 uppercase">
                {key.replace(/_/g, ' ')}
              </span>
              <HoverCard
                align="left"
                trigger={
                  <p className="line-clamp-2 cursor-default text-[12px] leading-snug font-medium text-[#1e1e1e]">
                    {truncate(value, 80)}
                  </p>
                }
              >
                <p className="text-[11px] text-slate-500">Full value</p>
                <p className="mt-0.5 text-[11px] font-medium break-words whitespace-pre-wrap text-slate-800">
                  {value}
                </p>
              </HoverCard>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
