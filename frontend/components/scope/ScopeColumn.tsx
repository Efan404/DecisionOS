'use client'

import { useMemo, useState } from 'react'
import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'

import { ScopeItem } from './ScopeItem'
import type { ScopeBaselineItem } from '../../lib/schemas'

type ScopeColumnProps = {
  title: string
  tooltip: string
  lane: 'in' | 'out'
  items: ScopeBaselineItem[]
  readonly?: boolean
  isOver?: boolean
  onAdd: (lane: 'in' | 'out', content: string) => void
  onDelete: (itemId: string) => void
}

const sortByDisplayOrder = (items: ScopeBaselineItem[]): ScopeBaselineItem[] => {
  return [...items].sort((left, right) => left.display_order - right.display_order)
}

export function ScopeColumn({
  title,
  tooltip,
  lane,
  items,
  readonly = false,
  onAdd,
  onDelete,
}: ScopeColumnProps) {
  const [draft, setDraft] = useState('')
  const [showTooltip, setShowTooltip] = useState(false)
  const sortedItems = useMemo(() => sortByDisplayOrder(items), [items])
  const isInLane = lane === 'in'
  const labelText = isInLane ? 'Add item to IN scope' : 'Add item to OUT scope'
  const accentColor = isInLane ? '#b9eb10' : '#1e1e1e'
  const accentBg = isInLane ? 'bg-[#b9eb10] text-[#1e1e1e]' : 'bg-[#1e1e1e] text-white'
  const accentHover = isInLane ? 'hover:bg-[#d4f542]' : 'hover:bg-[#333]'

  const { setNodeRef, isOver } = useDroppable({ id: lane })

  return (
    <section
      ref={setNodeRef}
      className={`flex flex-col rounded-2xl border bg-white p-5 shadow-sm transition-colors ${isOver ? 'ring-2 ring-[#b9eb10]/60' : ''}`}
      style={{ borderColor: isOver ? `${accentColor}60` : `${accentColor}30` }}
    >
      {/* Header */}
      <div className="mb-4 flex items-center gap-2">
        <span
          className="h-2.5 w-2.5 rounded-full"
          style={{ background: accentColor }}
          aria-hidden="true"
        />
        <h3 className="text-sm font-bold tracking-tight text-[#1e1e1e]">{title}</h3>

        {/* Tooltip trigger */}
        <div className="relative">
          <button
            type="button"
            onMouseEnter={() => setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
            onFocus={() => setShowTooltip(true)}
            onBlur={() => setShowTooltip(false)}
            className="flex h-4 w-4 items-center justify-center rounded-full border border-[#1e1e1e]/15 bg-[#f5f5f5] text-[9px] font-bold text-[#1e1e1e]/40 transition hover:border-[#1e1e1e]/30 hover:text-[#1e1e1e]/70"
            aria-label={tooltip}
          >
            ?
          </button>
          {showTooltip && (
            <div className="absolute top-6 left-1/2 z-50 w-52 -translate-x-1/2 rounded-xl border border-[#1e1e1e]/10 bg-[#1e1e1e] px-3 py-2 text-xs text-white shadow-lg">
              {tooltip}
              <div className="absolute -top-1.5 left-1/2 h-3 w-3 -translate-x-1/2 rotate-45 rounded-sm border-t border-l border-[#1e1e1e]/10 bg-[#1e1e1e]" />
            </div>
          )}
        </div>

        <span className="ml-auto rounded-full bg-[#f5f5f5] px-2 py-0.5 text-[11px] font-medium text-[#1e1e1e]/50">
          {sortedItems.length}
        </span>
      </div>

      {/* Add item input */}
      {!readonly && (
        <div className="mb-4 flex items-center gap-2">
          <label htmlFor={`${lane}-item-input`} className="sr-only">
            {labelText}
          </label>
          <input
            id={`${lane}-item-input`}
            aria-label={labelText}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                const content = draft.trim()
                if (!content) return
                onAdd(lane, content)
                setDraft('')
              }
            }}
            placeholder="Add an item…"
            className="min-w-0 flex-1 rounded-xl border border-[#1e1e1e]/12 bg-[#f5f5f5] px-3 py-2 text-sm text-[#1e1e1e] transition outline-none placeholder:text-[#1e1e1e]/30 focus:border-[#b9eb10] focus:ring-2 focus:ring-[#b9eb10]/20"
          />
          <button
            type="button"
            disabled={!draft.trim()}
            onClick={() => {
              const content = draft.trim()
              if (!content) return
              onAdd(lane, content)
              setDraft('')
            }}
            className={`shrink-0 rounded-xl px-3 py-2 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-40 ${accentBg} ${accentHover}`}
          >
            Add
          </button>
        </div>
      )}

      {/* Item list */}
      <SortableContext items={sortedItems.map((i) => i.id)} strategy={verticalListSortingStrategy}>
        <div className="flex min-h-28 flex-col gap-2">
          {sortedItems.length > 0 ? (
            sortedItems.map((item) => (
              <ScopeItem key={item.id} item={item} readonly={readonly} onDelete={onDelete} />
            ))
          ) : (
            <div
              className={`flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed py-8 transition-colors ${isOver ? 'border-[#b9eb10]/60 bg-[#b9eb10]/5' : 'border-[#1e1e1e]/10'}`}
            >
              <p className="text-xs text-[#1e1e1e]/30">
                {readonly ? 'No items.' : 'Drop here or add one above.'}
              </p>
            </div>
          )}
        </div>
      </SortableContext>
    </section>
  )
}
