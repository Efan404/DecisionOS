'use client'

import type { ScopeBaselineItem } from '../../lib/schemas'

type ScopeItemProps = {
  item: ScopeBaselineItem
  readonly?: boolean
  disableMoveUp?: boolean
  disableMoveDown?: boolean
  onDelete: (itemId: string) => void
  onMove: (itemId: string, direction: 'up' | 'down') => void
}

export function ScopeItem({
  item,
  readonly = false,
  disableMoveUp = false,
  disableMoveDown = false,
  onDelete,
  onMove,
}: ScopeItemProps) {
  return (
    <article className="group flex items-start gap-3 rounded-xl border border-[#1e1e1e]/8 bg-white px-4 py-3 shadow-sm transition-shadow hover:shadow-md">
      <p className="min-w-0 flex-1 text-sm leading-relaxed text-[#1e1e1e]/80">{item.content}</p>

      {!readonly && (
        <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          {/* Move up */}
          <button
            type="button"
            disabled={disableMoveUp}
            onClick={() => onMove(item.id, 'up')}
            aria-label="Move up"
            className="flex h-6 w-6 items-center justify-center rounded-md border border-[#1e1e1e]/10 bg-[#f5f5f5] text-[#1e1e1e]/50 transition hover:border-[#b9eb10]/60 hover:bg-[#b9eb10]/10 hover:text-[#1e1e1e] disabled:cursor-not-allowed disabled:opacity-30"
          >
            <svg viewBox="0 0 12 12" fill="none" className="h-3 w-3" aria-hidden="true">
              <path
                d="M2 8l4-4 4 4"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>

          {/* Move down */}
          <button
            type="button"
            disabled={disableMoveDown}
            onClick={() => onMove(item.id, 'down')}
            aria-label="Move down"
            className="flex h-6 w-6 items-center justify-center rounded-md border border-[#1e1e1e]/10 bg-[#f5f5f5] text-[#1e1e1e]/50 transition hover:border-[#b9eb10]/60 hover:bg-[#b9eb10]/10 hover:text-[#1e1e1e] disabled:cursor-not-allowed disabled:opacity-30"
          >
            <svg viewBox="0 0 12 12" fill="none" className="h-3 w-3" aria-hidden="true">
              <path
                d="M2 4l4 4 4-4"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>

          {/* Delete */}
          <button
            type="button"
            onClick={() => onDelete(item.id)}
            aria-label={`Delete: ${item.content}`}
            className="flex h-6 w-6 items-center justify-center rounded-md border border-red-200/60 bg-red-50/50 text-red-400 transition hover:border-red-300 hover:bg-red-50 hover:text-red-600"
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
        </div>
      )}
    </article>
  )
}
