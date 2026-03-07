'use client'

import { useMemo, useState } from 'react'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { arrayMove } from '@dnd-kit/sortable'

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
  onReorderItems,
}: ScopeBoardProps) {
  const [activeItem, setActiveItem] = useState<ScopeBaselineItem | null>(null)

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  const inItems = useMemo(
    () => sortByDisplayOrder(items.filter((item) => item.lane === 'in')),
    [items]
  )
  const outItems = useMemo(
    () => sortByDisplayOrder(items.filter((item) => item.lane === 'out')),
    [items]
  )

  const handleDragStart = (event: DragStartEvent) => {
    const dragged = items.find((item) => item.id === event.active.id)
    setActiveItem(dragged ?? null)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveItem(null)
    const { active, over } = event
    if (!over) return

    const draggedItem = items.find((item) => item.id === active.id)
    if (!draggedItem) return

    // Determine target lane: either the droppable container id ('in'/'out') or the lane of the item being hovered
    const overItem = items.find((item) => item.id === over.id)
    const targetLane: 'in' | 'out' =
      over.id === 'in' || over.id === 'out'
        ? (over.id as 'in' | 'out')
        : (overItem?.lane ?? draggedItem.lane)

    const laneSwitched = draggedItem.lane !== targetLane

    if (laneSwitched) {
      // Move item to other lane at end
      const laneItems = items.filter((i) => i.lane === targetLane)
      const updated: ScopeBaselineItem[] = items.map((item) => {
        if (item.id === draggedItem.id) {
          return { ...item, lane: targetLane, display_order: laneItems.length }
        }
        return item
      })
      onReorderItems(updated)
    } else {
      // Reorder within same lane
      const laneItems = sortByDisplayOrder(items.filter((i) => i.lane === draggedItem.lane))
      const oldIndex = laneItems.findIndex((i) => i.id === active.id)
      const newIndex = laneItems.findIndex((i) => i.id === over.id)
      if (oldIndex === newIndex) return
      const reordered = arrayMove(laneItems, oldIndex, newIndex).map((item, idx) => ({
        ...item,
        display_order: idx,
      }))
      const otherItems = items.filter((i) => i.lane !== draggedItem.lane)
      onReorderItems([...otherItems, ...reordered])
    }
  }

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <section id="onboarding-scope-board" className="relative mx-auto w-full max-w-5xl p-6">
        <div className="grid gap-4 md:grid-cols-2">
          <ScopeColumn
            title="IN Scope"
            tooltip="MUST HAVE — features that are core to the MVP and required for launch."
            lane="in"
            items={inItems}
            readonly={readonly}
            onAdd={onAddItem}
            onDelete={onDeleteItem}
          />
          <ScopeColumn
            title="OUT Scope"
            tooltip="NOT HAVE — features intentionally excluded from this release."
            lane="out"
            items={outItems}
            readonly={readonly}
            onAdd={onAddItem}
            onDelete={onDeleteItem}
          />
        </div>

        {/* Drag overlay — ghost card while dragging */}
        <DragOverlay>
          {activeItem ? (
            <div className="rounded-xl border border-[#1e1e1e]/8 bg-white px-3 py-3 shadow-xl ring-2 ring-[#b9eb10]/60">
              <p className="text-sm leading-relaxed text-[#1e1e1e]/80">{activeItem.content}</p>
            </div>
          ) : null}
        </DragOverlay>

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
    </DndContext>
  )
}
