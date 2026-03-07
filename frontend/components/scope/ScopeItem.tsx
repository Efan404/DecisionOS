'use client'

import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

import type { ScopeBaselineItem } from '../../lib/schemas'

type ScopeItemProps = {
  item: ScopeBaselineItem
  readonly?: boolean
  onDelete: (itemId: string) => void
}

export function ScopeItem({ item, readonly = false, onDelete }: ScopeItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
    disabled: readonly,
    data: { lane: item.lane },
  })

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    zIndex: isDragging ? 50 : undefined,
  }

  return (
    <article
      ref={setNodeRef}
      style={style}
      className="group flex items-start gap-2 rounded-xl border border-[#1e1e1e]/8 bg-white px-3 py-3 shadow-sm transition-shadow hover:shadow-md"
    >
      {/* Drag handle */}
      {!readonly && (
        <span
          {...attributes}
          {...listeners}
          className="mt-0.5 shrink-0 cursor-grab touch-none text-[#1e1e1e]/20 transition hover:text-[#1e1e1e]/50 active:cursor-grabbing"
          aria-label="Drag to reorder"
        >
          <svg viewBox="0 0 10 16" fill="currentColor" className="h-4 w-2.5" aria-hidden="true">
            <circle cx="2.5" cy="2" r="1.5" />
            <circle cx="7.5" cy="2" r="1.5" />
            <circle cx="2.5" cy="8" r="1.5" />
            <circle cx="7.5" cy="8" r="1.5" />
            <circle cx="2.5" cy="14" r="1.5" />
            <circle cx="7.5" cy="14" r="1.5" />
          </svg>
        </span>
      )}

      <p className="min-w-0 flex-1 text-sm leading-relaxed text-[#1e1e1e]/80">{item.content}</p>

      {!readonly && (
        <button
          type="button"
          onClick={() => onDelete(item.id)}
          aria-label={`Delete: ${item.content}`}
          className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[#1e1e1e]/20 opacity-0 transition group-hover:opacity-100 hover:text-red-500"
        >
          <svg viewBox="0 0 12 12" fill="none" className="h-3 w-3" aria-hidden="true">
            <path
              d="M2 2l8 8M10 2L2 10"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </button>
      )}
    </article>
  )
}
