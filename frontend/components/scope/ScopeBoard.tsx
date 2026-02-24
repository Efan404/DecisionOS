'use client'

import { useMemo } from 'react'

import { ScopeColumn } from './ScopeColumn'
import type { ScopeBaselineItem } from '../../lib/schemas'

type ScopeBoardProps = {
  items: ScopeBaselineItem[]
  readonly?: boolean
  onAddItem: (lane: 'in' | 'out', content: string) => void
  onDeleteItem: (itemId: string) => void
  onMoveItem: (itemId: string, direction: 'up' | 'down') => void
  onReorderItems: (items: ScopeBaselineItem[]) => void
}

const sortByDisplayOrder = (items: ScopeBaselineItem[]): ScopeBaselineItem[] => {
  return [...items].sort((left, right) => left.display_order - right.display_order)
}

export function ScopeBoard({
  items,
  readonly = false,
  onAddItem,
  onDeleteItem,
  onMoveItem,
}: ScopeBoardProps) {
  const inItems = useMemo(
    () => sortByDisplayOrder(items.filter((item) => item.lane === 'in')),
    [items]
  )
  const outItems = useMemo(
    () => sortByDisplayOrder(items.filter((item) => item.lane === 'out')),
    [items]
  )

  return (
    <section className="relative mx-auto w-full max-w-5xl p-6">
      <div className="grid gap-4 md:grid-cols-2">
        <ScopeColumn
          title="IN Scope"
          lane="in"
          items={inItems}
          readonly={readonly}
          onAdd={onAddItem}
          onDelete={onDeleteItem}
          onMove={onMoveItem}
        />
        <ScopeColumn
          title="OUT Scope"
          lane="out"
          items={outItems}
          readonly={readonly}
          onAdd={onAddItem}
          onDelete={onDeleteItem}
          onMove={onMoveItem}
        />
      </div>

      {readonly ? (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-2xl bg-white/45 backdrop-blur-[1px]">
          <div className="rounded-md border border-black/20 bg-white px-3 py-1 text-xs font-medium tracking-wide text-black/70 uppercase">
            Scope Locked
          </div>
        </div>
      ) : null}
    </section>
  )
}
