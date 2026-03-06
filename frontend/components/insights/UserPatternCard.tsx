'use client'

import { useEffect, useState } from 'react'

import { getUserPatterns } from '../../lib/api'

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
    <div className="rounded-xl border border-[#1e1e1e]/10 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-[#1e1e1e]">Your Decision Patterns</h2>
          <p className="mt-0.5 text-xs text-[#1e1e1e]/50">
            Learned from your past choices across ideas.
          </p>
        </div>
        <span className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
          Demo data
        </span>
      </div>

      {loading ? (
        <div className="mt-4 space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-7 animate-pulse rounded-lg bg-[#f5f5f5]" />
          ))}
        </div>
      ) : error ? (
        <p className="mt-3 text-xs text-red-600">{error}</p>
      ) : entries.length === 0 ? (
        <p className="mt-4 text-xs text-[#1e1e1e]/40">
          No patterns learned yet. Make decisions across multiple ideas to build your profile.
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {entries.map(([key, value]) => (
            <li
              key={key}
              className="flex items-center justify-between gap-3 rounded-lg border border-[#1e1e1e]/8 bg-[#f5f5f5] px-3 py-2"
            >
              <span className="text-[11px] font-medium tracking-wide text-[#1e1e1e]/60 uppercase">
                {key.replace(/_/g, ' ')}
              </span>
              <span className="rounded-full bg-[#b9eb10] px-2 py-0.5 text-[11px] font-bold text-[#1e1e1e]">
                {value}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
