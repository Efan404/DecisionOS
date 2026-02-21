import { useMemo, useState } from 'react'

import type { PrdBacklogItem, PrdSourceRef } from '../../lib/schemas'

type PrdBacklogPanelProps = {
  items: PrdBacklogItem[]
  selectedRequirementId: string | null
  onSelectRequirement: (requirementId: string) => void
}

type FilterValue = 'all' | string

const PRIORITY_BADGE: Record<string, string> = {
  P0: 'bg-red-100 text-red-700',
  P1: 'bg-amber-100 text-amber-700',
  P2: 'bg-sky-100 text-sky-700',
}

const TYPE_BADGE: Record<string, string> = {
  epic: 'bg-purple-100 text-purple-700',
  story: 'bg-emerald-100 text-emerald-700',
  task: 'bg-slate-100 text-slate-600',
}

export function PrdBacklogPanel({
  items,
  selectedRequirementId,
  onSelectRequirement,
}: PrdBacklogPanelProps) {
  const [priorityFilter, setPriorityFilter] = useState<FilterValue>('all')
  const [typeFilter, setTypeFilter] = useState<FilterValue>('all')
  const [sourceFilter, setSourceFilter] = useState<FilterValue>('all')
  // When true, only show backlog items linked to the selected requirement
  const [filterByRequirement, setFilterByRequirement] = useState(true)

  const sourceOptions = useMemo(() => {
    const refs = new Set<PrdSourceRef>()
    for (const item of items) {
      for (const ref of item.source_refs) {
        refs.add(ref)
      }
    }
    return Array.from(refs.values()).sort()
  }, [items])

  const filtered = items.filter((item) => {
    if (filterByRequirement && selectedRequirementId && item.requirement_id !== selectedRequirementId) {
      return false
    }
    if (priorityFilter !== 'all' && item.priority !== priorityFilter) {
      return false
    }
    if (typeFilter !== 'all' && item.type !== typeFilter) {
      return false
    }
    if (sourceFilter !== 'all' && !item.source_refs.includes(sourceFilter as PrdSourceRef)) {
      return false
    }
    return true
  })

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900">
            Backlog
            <span className="ml-1.5 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
              {filtered.length}/{items.length}
            </span>
          </h2>
          {/* Requirement linkage toggle */}
          <button
            type="button"
            onClick={() => setFilterByRequirement((previous) => !previous)}
            className={`cursor-pointer rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 ${
              filterByRequirement && selectedRequirementId
                ? 'border-cyan-300 bg-cyan-50 text-cyan-700'
                : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
            }`}
          >
            {filterByRequirement && selectedRequirementId ? 'Linked to req' : 'All items'}
          </button>
        </div>
      </header>

      {/* Filters row */}
      <div className="grid gap-2 border-b border-slate-100 px-4 py-3 sm:grid-cols-3">
        <label className="text-[11px] font-medium text-slate-500">
          Priority
          <select
            value={priorityFilter}
            onChange={(event) => setPriorityFilter(event.target.value)}
            className="mt-1 w-full cursor-pointer rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
          >
            <option value="all">All</option>
            <option value="P0">P0</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
          </select>
        </label>
        <label className="text-[11px] font-medium text-slate-500">
          Type
          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="mt-1 w-full cursor-pointer rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
          >
            <option value="all">All</option>
            <option value="epic">Epic</option>
            <option value="story">Story</option>
            <option value="task">Task</option>
          </select>
        </label>
        <label className="text-[11px] font-medium text-slate-500">
          Source
          <select
            value={sourceFilter}
            onChange={(event) => setSourceFilter(event.target.value)}
            className="mt-1 w-full cursor-pointer rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
          >
            <option value="all">All</option>
            {sourceOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Items list */}
      <ul className="max-h-[50vh] divide-y divide-slate-100 overflow-auto">
        {filtered.length === 0 ? (
          <li className="px-4 py-6 text-center text-xs text-slate-400">
            No backlog items match the current filters.
          </li>
        ) : (
          filtered.map((item) => {
            const active = selectedRequirementId === item.requirement_id
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onSelectRequirement(item.requirement_id)}
                  className={`w-full cursor-pointer px-4 py-3 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400 ${
                    active ? 'bg-cyan-50' : 'hover:bg-slate-50'
                  }`}
                >
                  <p className="text-sm font-medium leading-5 text-slate-900">{item.title}</p>
                  <p className="mt-0.5 text-xs leading-4 text-slate-500">{item.summary}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <span
                      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${PRIORITY_BADGE[item.priority] ?? 'bg-slate-100 text-slate-600'}`}
                    >
                      {item.priority}
                    </span>
                    <span
                      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold capitalize ${TYPE_BADGE[item.type] ?? 'bg-slate-100 text-slate-600'}`}
                    >
                      {item.type}
                    </span>
                    <span className="inline-flex items-center rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                      {item.requirement_id}
                    </span>
                  </div>
                </button>
              </li>
            )
          })
        )}
      </ul>
    </section>
  )
}
