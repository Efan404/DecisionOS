'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { buildIdeaFeasibilityDetailHref, resolveIdeaIdForRouting } from '../../lib/idea-routes'
import { useIdeasStore } from '../../lib/ideas-store'
import type { FeasibilityPlan } from '../../lib/schemas'
import { HoverCard } from '../common/HoverCard'

type PlanCardsProps = {
  plans: FeasibilityPlan[]
  selectedPlanId?: string
  onSelect?: (planId: string) => void
  loadingSlots?: number
}

function PlanCardSkeleton() {
  return (
    <article className="animate-pulse rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="h-4 w-2/3 rounded bg-slate-200" />
        <div className="h-6 w-16 rounded bg-slate-200" />
      </div>
      <div className="mt-3 space-y-2">
        <div className="h-3 w-full rounded bg-slate-100" />
        <div className="h-3 w-4/5 rounded bg-slate-100" />
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2 rounded-lg border border-slate-200 bg-slate-50/80 p-3">
        <div className="h-3 w-full rounded bg-slate-200" />
        <div className="h-3 w-full rounded bg-slate-200" />
        <div className="h-3 w-full rounded bg-slate-200" />
      </div>
      <div className="mt-4 flex items-center gap-2">
        <div className="h-3 w-16 rounded bg-slate-100" />
        <span className="text-xs text-slate-400">Generating...</span>
      </div>
    </article>
  )
}

// Score color: green ≥7, yellow ≥4, red <4
const scoreColor = (score: number, selected: boolean) => {
  if (selected) return 'text-white/90'
  if (score >= 7) return 'text-emerald-600'
  if (score >= 4) return 'text-amber-600'
  return 'text-red-500'
}

const scoreBarColor = (score: number) => {
  if (score >= 7) return 'bg-[#b9eb10]'
  if (score >= 4) return 'bg-amber-400'
  return 'bg-red-400'
}

export function PlanCards({ plans, selectedPlanId, onSelect, loadingSlots = 0 }: PlanCardsProps) {
  const pathname = usePathname()
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const buildDetailHref = (planId: string): string => {
    const routeIdeaId = resolveIdeaIdForRouting(pathname, activeIdeaId)
    return routeIdeaId ? buildIdeaFeasibilityDetailHref(routeIdeaId, planId) : '/ideas'
  }

  const skeletonCount = Math.max(0, loadingSlots - plans.length)

  return (
    <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {plans.map((plan) => {
        const selected = selectedPlanId === plan.id

        return (
          <article
            key={plan.id}
            className={[
              'rounded-2xl border p-4 shadow-sm transition-all duration-200 motion-reduce:transition-none',
              selected
                ? 'border-[#b9eb10] bg-[#1e1e1e] text-slate-50 shadow-md shadow-[#b9eb10]/20'
                : 'border-slate-200 bg-white text-slate-900 hover:-translate-y-0.5 hover:border-[#b9eb10]/60 hover:shadow-md',
            ].join(' ')}
          >
            <Link
              href={buildDetailHref(plan.id)}
              className="group block w-full text-left focus-visible:ring-2 focus-visible:ring-[#b9eb10] focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-base font-semibold tracking-tight">{plan.name}</h2>
                <HoverCard
                  align="right"
                  trigger={
                    <span
                      className={[
                        'rounded-md border px-2 py-1 text-[11px] font-medium cursor-default',
                        selected
                          ? 'border-slate-200/20 bg-white/10 text-slate-100'
                          : 'border-slate-200 bg-slate-50 text-slate-600 group-hover:border-[#b9eb10]/40 group-hover:bg-[#b9eb10]/10 group-hover:text-[#1e1e1e]',
                      ].join(' ')}
                    >
                      Overall {plan.score_overall.toFixed(1)}
                    </span>
                  }
                >
                  <p className="mb-1.5 text-[11px] font-semibold text-slate-900">Score Breakdown</p>
                  <ul className="space-y-1 text-[11px]">
                    <li className="flex justify-between gap-4">
                      <span className="text-slate-500">Technical</span>
                      <span className="font-bold">{plan.scores.technical_feasibility.toFixed(1)}</span>
                    </li>
                    <li className="flex justify-between gap-4">
                      <span className="text-slate-500">Market</span>
                      <span className="font-bold">{plan.scores.market_viability.toFixed(1)}</span>
                    </li>
                    <li className="flex justify-between gap-4">
                      <span className="text-slate-500">Risk</span>
                      <span className="font-bold">{plan.scores.execution_risk.toFixed(1)}</span>
                    </li>
                  </ul>
                </HoverCard>
              </div>
              <p className="mt-2 text-sm leading-6 text-current/80">{plan.summary}</p>
              <div
                className={[
                  'mt-4 rounded-lg border p-3 text-xs',
                  selected ? 'border-slate-200/20 bg-white/5' : 'border-slate-200 bg-slate-50/80',
                ].join(' ')}
              >
                {[
                  { label: 'Tech', score: plan.scores.technical_feasibility },
                  { label: 'Market', score: plan.scores.market_viability },
                  { label: 'Risk', score: plan.scores.execution_risk },
                ].map(({ label, score }) => (
                  <div key={label} className="mb-2 last:mb-0">
                    <div className="mb-1 flex items-center justify-between">
                      <span className={selected ? 'text-white/60' : 'text-slate-500'}>{label}</span>
                      <span className={`font-bold ${scoreColor(score, selected)}`}>
                        {score.toFixed(1)}
                      </span>
                    </div>
                    <div
                      className={`h-1 w-full overflow-hidden rounded-full ${selected ? 'bg-white/10' : 'bg-slate-200'}`}
                    >
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${scoreBarColor(score)}`}
                        style={{ width: `${(score / 10) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Link>
            <div className="mt-4 flex flex-wrap gap-2">
              {onSelect ? (
                <button
                  type="button"
                  className="rounded-md border border-current/30 px-2.5 py-1.5 text-xs font-medium transition-colors duration-200 hover:bg-current/10 focus-visible:ring-2 focus-visible:ring-[#b9eb10] focus-visible:ring-offset-2 focus-visible:outline-none"
                  onClick={() => onSelect(plan.id)}
                >
                  Select
                </button>
              ) : null}
              <Link
                href={buildDetailHref(plan.id)}
                className="rounded-md border border-current/30 px-2.5 py-1.5 text-xs font-medium transition-colors duration-200 hover:bg-current/10 focus-visible:ring-2 focus-visible:ring-[#b9eb10] focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                View Detail
              </Link>
            </div>
          </article>
        )
      })}
      {Array.from({ length: skeletonCount }).map((_, i) => (
        <PlanCardSkeleton key={`skeleton-${i}`} />
      ))}
    </section>
  )
}
