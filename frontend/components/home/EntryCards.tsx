'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'

import { buildIdeaStepHref } from '../../lib/idea-routes'
import { useIdeasStore } from '../../lib/ideas-store'

type EntryStep = 'idea-canvas' | 'feasibility' | 'scope-freeze' | 'prd'

const ENTRY_STEPS: EntryStep[] = ['idea-canvas', 'feasibility', 'scope-freeze', 'prd']

const ENTRY_STEP_KEYS: Record<EntryStep, string> = {
  'idea-canvas': 'ideaCanvas',
  feasibility: 'feasibility',
  'scope-freeze': 'scopeFreeze',
  prd: 'prd',
}

export function EntryCards() {
  const t = useTranslations('home')
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)

  return (
    <section className="mx-auto grid max-w-5xl grid-cols-1 gap-4 px-4 py-6 sm:grid-cols-2 sm:px-6">
      {ENTRY_STEPS.map((step) => {
        const key = ENTRY_STEP_KEYS[step]
        return (
          <Link
            key={step}
            href={activeIdeaId ? buildIdeaStepHref(activeIdeaId, step) : '/ideas'}
            className="group rounded-2xl border border-slate-200 bg-white/95 p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-[#b9eb10]/60 hover:shadow-md focus-visible:ring-2 focus-visible:ring-[#b9eb10] focus-visible:ring-offset-2 focus-visible:outline-none active:translate-y-0 active:shadow-sm motion-reduce:transition-none"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold tracking-tight text-slate-900">
                {t(`entries.${key}.title`)}
              </h2>
              <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-600 transition-colors duration-200 group-hover:border-[#b9eb10]/40 group-hover:bg-[#b9eb10]/10 group-hover:text-[#1e1e1e]">
                {t('open')}
              </span>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              {t(`entries.${key}.description`)}
            </p>
          </Link>
        )
      })}
    </section>
  )
}
