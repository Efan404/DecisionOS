'use client'

import Link from 'next/link'

import { buildIdeaStepHref } from '../../lib/idea-routes'
import { useIdeasStore } from '../../lib/ideas-store'

const entries = [
  {
    step: 'idea-canvas' as const,
    title: 'Idea Canvas',
    description: 'Enter an idea seed and choose direction and path.',
  },
  {
    step: 'feasibility' as const,
    title: 'Feasibility',
    description: 'Review feasibility scorecards and confirm a plan.',
  },
  {
    step: 'scope-freeze' as const,
    title: 'Scope Freeze',
    description: 'Organize IN/OUT scope and freeze decisions.',
  },
  {
    step: 'prd' as const,
    title: 'PRD',
    description: 'Review generated PRD content.',
  },
]

export function EntryCards() {
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)

  return (
    <section className="mx-auto grid max-w-5xl grid-cols-1 gap-4 px-4 py-6 sm:grid-cols-2 sm:px-6">
      {entries.map((entry) => (
        <Link
          key={entry.step}
          href={activeIdeaId ? buildIdeaStepHref(activeIdeaId, entry.step) : '/ideas'}
          className="group rounded-2xl border border-slate-200 bg-white/95 p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-[#b9eb10]/60 hover:shadow-md focus-visible:ring-2 focus-visible:ring-[#b9eb10] focus-visible:ring-offset-2 focus-visible:outline-none active:translate-y-0 active:shadow-sm motion-reduce:transition-none"
        >
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-lg font-semibold tracking-tight text-slate-900">{entry.title}</h2>
            <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-600 transition-colors duration-200 group-hover:border-[#b9eb10]/40 group-hover:bg-[#b9eb10]/10 group-hover:text-[#1e1e1e]">
              Open
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{entry.description}</p>
        </Link>
      ))}
    </section>
  )
}
