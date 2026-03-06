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
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-2xl bg-white/30 backdrop-blur-[1px]">
          <div className="flex items-center gap-2 rounded-xl border border-[#b9eb10]/50 bg-white px-4 py-2 shadow-md">
            <svg
              viewBox="0 0 16 16"
              fill="none"
              className="h-3.5 w-3.5 text-[#1e1e1e]/60"
              aria-hidden="true"
            >
              <rect
                x="3"
                y="7"
                width="10"
                height="8"
                rx="1.5"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <path
                d="M5 7V5a3 3 0 0 1 6 0v2"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
            <span className="text-xs font-semibold tracking-wide text-[#1e1e1e]/70 uppercase">
              Scope Locked
            </span>
          </div>
        </div>
      ) : null}
    </section>
  )
}
