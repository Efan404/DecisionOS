'use client'

import { EXPANSION_PATTERNS } from '../../../lib/dag-api'

interface Props {
  onSelect: (patternId: string) => void
  loading?: boolean
}

export function ExpansionPatternPicker({ onSelect, loading }: Props) {
  return (
    <div className="grid grid-cols-1 gap-2">
      {EXPANSION_PATTERNS.map((p) => (
        <button
          key={p.id}
          onClick={() => onSelect(p.id)}
          disabled={loading}
          className="cursor-pointer rounded-lg border border-[#334155] px-3 py-2.5 text-left transition-all duration-150 hover:border-[#22C55E] hover:bg-[#22C55E]/5 disabled:opacity-50"
        >
          <div className="text-sm font-medium text-[#F8FAFC]">{p.label}</div>
          <div className="mt-0.5 text-xs text-[#64748B]">{p.description}</div>
        </button>
      ))}
    </div>
  )
}
