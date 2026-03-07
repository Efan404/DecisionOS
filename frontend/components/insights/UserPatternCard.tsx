'use client'

import { useEffect, useState } from 'react'

import { getUserPatterns } from '../../lib/api'

// ── Color system ──────────────────────────────────────────────────────────────

type CardTheme = {
  border: string
  bg: string
  highlightBorder: string
  highlightBg: string
  badge: string
  badgeBg: string
  label: string
}

const THEMES: Record<string, CardTheme> = {
  risk_tolerance: {
    border: 'border-orange-300/40',
    bg: 'bg-orange-50/60',
    highlightBorder: 'border-orange-400',
    highlightBg: 'bg-orange-50',
    badge: 'text-orange-700',
    badgeBg: 'bg-orange-100',
    label: 'Risk Tolerance',
  },
  business_model_preference: {
    border: 'border-purple-300/40',
    bg: 'bg-purple-50/60',
    highlightBorder: 'border-purple-400',
    highlightBg: 'bg-purple-50',
    badge: 'text-purple-700',
    badgeBg: 'bg-purple-100',
    label: 'Business Model',
  },
  decision_style: {
    border: 'border-blue-300/40',
    bg: 'bg-blue-50/60',
    highlightBorder: 'border-blue-400',
    highlightBg: 'bg-blue-50',
    badge: 'text-blue-700',
    badgeBg: 'bg-blue-100',
    label: 'Decision Style',
  },
  focus_area: {
    border: 'border-cyan-300/40',
    bg: 'bg-cyan-50/60',
    highlightBorder: 'border-cyan-400',
    highlightBg: 'bg-cyan-50',
    badge: 'text-cyan-700',
    badgeBg: 'bg-cyan-100',
    label: 'Focus Area',
  },
}

const DEFAULT_THEME: CardTheme = {
  border: 'border-[#1e1e1e]/10',
  bg: 'bg-[#f5f5f5]',
  highlightBorder: 'border-[#b9eb10]',
  highlightBg: 'bg-[#f5f5f5]',
  badge: 'text-[#1e1e1e]/60',
  badgeBg: 'bg-[#1e1e1e]/8',
  label: '',
}

const EMOJIS: Record<string, string> = {
  risk_tolerance: '⚡',
  business_model_preference: '💼',
  decision_style: '🧭',
  focus_area: '🎯',
}

const PATTERN_ORDER = [
  'risk_tolerance',
  'business_model_preference',
  'decision_style',
  'focus_area',
]

// ── Types ─────────────────────────────────────────────────────────────────────

interface AdvisorNote {
  text: string
  linked_patterns: string[]
}

// ── Component ─────────────────────────────────────────────────────────────────

export function UserPatternCard() {
  const [preferences, setPreferences] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hoveredPattern, setHoveredPattern] = useState<string | null>(null)

  useEffect(() => {
    const run = async () => {
      try {
        const result = await getUserPatterns()
        setPreferences(result.preferences as Record<string, unknown>)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load patterns.')
      } finally {
        setLoading(false)
      }
    }
    void run()
  }, [])

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-[#f5f5f5]" />
          ))}
        </div>
        <div className="h-32 animate-pulse rounded-xl bg-[#f5f5f5]" />
      </div>
    )
  }

  if (error) {
    return <p className="text-xs text-red-600">{error}</p>
  }

  if (!preferences || Object.keys(preferences).length === 0) {
    return (
      <p className="text-xs text-[#1e1e1e]/40">
        No patterns learned yet. Make decisions across multiple ideas to build your profile.
      </p>
    )
  }

  // Extract advisor_note; everything else is a pattern card
  const advisorNote = preferences['advisor_note'] as AdvisorNote | undefined
  const bullets: string[] = advisorNote?.text
    ? advisorNote.text
        .split('\n')
        .map((b) => b.replace(/^[•\-]\s*/, '').trim())
        .filter(Boolean)
    : []
  const linkedPatterns: string[] = advisorNote?.linked_patterns ?? []

  // Build ordered pattern entries (only known keys, in order)
  const patternEntries = PATTERN_ORDER.filter((k) => k in preferences && k !== 'advisor_note').map(
    (k) => [k, String(preferences[k])] as [string, string]
  )

  // Also include any unexpected keys (not in PATTERN_ORDER, not advisor_note)
  const knownKeys = new Set([...PATTERN_ORDER, 'advisor_note'])
  const extraEntries = Object.entries(preferences)
    .filter(([k]) => !knownKeys.has(k))
    .map(([k, v]) => [k, String(v)] as [string, string])

  const allPatterns = [...patternEntries, ...extraEntries]

  return (
    <div className="space-y-3">
      {/* Bento 2×2 pattern grid */}
      <div className="grid grid-cols-2 gap-3">
        {allPatterns.map(([key, value]) => {
          const theme = THEMES[key] ?? DEFAULT_THEME
          const isHighlighted = hoveredPattern === key
          const emoji = EMOJIS[key] ?? '◆'
          const label = theme.label || key.replace(/_/g, ' ')

          return (
            <div
              key={key}
              className={[
                'flex flex-col gap-2 rounded-xl border-2 px-4 py-3 transition-all duration-200',
                isHighlighted
                  ? `${theme.highlightBorder} ${theme.highlightBg} scale-[1.01] shadow-md`
                  : `${theme.border} ${theme.bg}`,
              ].join(' ')}
            >
              {/* Header row */}
              <div className="flex items-center gap-2">
                <span
                  className={[
                    'flex h-6 w-6 items-center justify-center rounded-md text-xs',
                    theme.badgeBg,
                  ].join(' ')}
                >
                  {emoji}
                </span>
                <span
                  className={[
                    'text-[10px] font-semibold tracking-wider uppercase',
                    theme.badge,
                  ].join(' ')}
                >
                  {label}
                </span>
              </div>
              {/* Value */}
              <p className="line-clamp-3 text-[12px] leading-snug font-medium text-[#1e1e1e]">
                {value}
              </p>
            </div>
          )
        })}
      </div>

      {/* Advisor note card */}
      {bullets.length > 0 && (
        <div className="rounded-xl border border-[#b9eb10]/30 bg-[#1e1e1e] px-5 py-4">
          <div className="mb-3 flex items-center gap-2">
            <span className="text-[10px] font-semibold tracking-widest text-[#b9eb10] uppercase">
              Advisor Note
            </span>
          </div>
          <ul className="space-y-2.5">
            {bullets.map((bullet, i) => {
              const patternKey = linkedPatterns[i] ?? null
              const theme = patternKey ? (THEMES[patternKey] ?? null) : null

              return (
                <li key={i} className="flex items-start gap-2.5">
                  <span className="mt-0.5 text-xs text-[#b9eb10] select-none">•</span>
                  <p className="text-[12px] leading-relaxed text-white/80">
                    {bullet}
                    {patternKey && theme && (
                      <>
                        {' '}
                        <button
                          type="button"
                          onMouseEnter={() => setHoveredPattern(patternKey)}
                          onMouseLeave={() => setHoveredPattern(null)}
                          className={[
                            'inline-flex cursor-pointer items-center rounded px-1.5 py-0.5 text-[10px] font-semibold transition-all duration-150',
                            hoveredPattern === patternKey
                              ? `${theme.badge} ${theme.badgeBg} opacity-100`
                              : 'bg-white/10 text-white/50 hover:text-white/80',
                          ].join(' ')}
                        >
                          {EMOJIS[patternKey] ?? '◆'} {theme.label || patternKey.replace(/_/g, ' ')}
                        </button>
                      </>
                    )}
                  </p>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
