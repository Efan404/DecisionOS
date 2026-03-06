'use client'

import Link from 'next/link'
import { useIdeasStore } from '../../lib/ideas-store'
import { buildIdeaStepHref } from '../../lib/idea-routes'

type GuardPanelProps = {
  title: string
  description: string
}

export function GuardPanel({ title, description }: GuardPanelProps) {
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const startHref = activeIdeaId ? buildIdeaStepHref(activeIdeaId, 'idea-canvas') : '/ideas'

  return (
    <section className="mx-auto w-full max-w-3xl rounded-2xl border border-slate-200 bg-gradient-to-b from-white to-slate-50/70 p-6 shadow-sm">
      <h1 className="text-xl font-semibold tracking-tight text-slate-900">{title}</h1>
      <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
      <Link
        href={startHref}
        className="mt-5 inline-flex items-center rounded-md border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-800 shadow-sm transition-all duration-200 hover:border-[#b9eb10] hover:bg-[#b9eb10]/10 hover:text-[#1e1e1e] focus-visible:ring-2 focus-visible:ring-[#b9eb10] focus-visible:ring-offset-2 focus-visible:outline-none active:translate-y-px motion-reduce:transition-none"
      >
        Start from Idea Canvas
      </Link>
    </section>
  )
}
