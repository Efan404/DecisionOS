'use client'

import { useMemo, useState } from 'react'

import { ScopeItem } from './ScopeItem'
import type { ScopeBaselineItem } from '../../lib/schemas'

type ScopeColumnProps = {
  title: string
  lane: 'in' | 'out'
  items: ScopeBaselineItem[]
  readonly?: boolean
  onAdd: (lane: 'in' | 'out', content: string) => void
  onDelete: (itemId: string) => void
  onMove: (itemId: string, direction: 'up' | 'down') => void
}

const sortByDisplayOrder = (items: ScopeBaselineItem[]): ScopeBaselineItem[] => {
  return [...items].sort((left, right) => left.display_order - right.display_order)
}

export function ScopeColumn({
  title,
  lane,
  items,
  readonly = false,
  onAdd,
  onDelete,
  onMove,
}: ScopeColumnProps) {
  const [draft, setDraft] = useState('')
  const sortedItems = useMemo(() => sortByDisplayOrder(items), [items])
  const isInLane = lane === 'in'
  const labelText = isInLane ? 'Add item to IN scope' : 'Add item to OUT scope'
  const buttonText = isInLane ? 'Add IN Item' : 'Add OUT Item'

  return (
    <section className="rounded-xl border border-black/20 bg-black/[0.02] p-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="mt-3 flex items-center gap-2">
        <label htmlFor={`${lane}-item-input`} className="sr-only">
          {labelText}
        </label>
        <input
          id={`${lane}-item-input`}
          aria-label={labelText}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          disabled={readonly}
          className="w-full rounded border border-black/20 bg-white px-2 py-1 text-sm disabled:cursor-not-allowed disabled:bg-slate-100"
        />
        <button
          type="button"
          disabled={readonly || !draft.trim()}
          onClick={() => {
            const content = draft.trim()
            if (!content) {
              return
            }
            onAdd(lane, content)
            setDraft('')
          }}
          className="rounded border border-black px-2 py-1 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-50"
        >
          {buttonText}
        </button>
      </div>
      <div className="mt-3 flex min-h-36 flex-col gap-2 rounded-md border border-dashed border-transparent p-1">
        {sortedItems.length ? (
          sortedItems.map((item, index) => (
            <ScopeItem
              key={item.id}
              item={item}
              readonly={readonly}
              disableMoveUp={index === 0}
              disableMoveDown={index === sortedItems.length - 1}
              onDelete={onDelete}
              onMove={onMove}
            />
          ))
        ) : (
          <p className="text-xs text-black/50">No items yet.</p>
        )}
      </div>
    </section>
  )
}
