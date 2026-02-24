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
    <article className="rounded-lg border border-black/10 bg-white p-3">
      <p className="text-sm text-black/85">{item.content}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={readonly || disableMoveUp}
          onClick={() => onMove(item.id, 'up')}
          className="rounded border border-black/20 px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
        >
          Up
        </button>
        <button
          type="button"
          disabled={readonly || disableMoveDown}
          onClick={() => onMove(item.id, 'down')}
          className="rounded border border-black/20 px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
        >
          Down
        </button>
        <button
          type="button"
          disabled={readonly}
          onClick={() => onDelete(item.id)}
          className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label={`Delete ${item.content}`}
        >
          Delete
        </button>
      </div>
    </article>
  )
}
