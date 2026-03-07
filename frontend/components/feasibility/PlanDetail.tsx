import type { FeasibilityPlan } from '../../lib/schemas'

type PlanDetailProps = {
  plan: FeasibilityPlan | null
  onConfirm?: () => void
  confirming?: boolean
}

type ScoreCardProps = {
  label: string
  value: number
  tooltip: string
}

function ScoreCard({ label, value, tooltip }: ScoreCardProps) {
  return (
    <div className="group relative rounded-lg border border-[#1e1e1e]/10 bg-[#f5f5f5] p-3 text-sm">
      <div className="flex items-center gap-1">
        <span className="text-[11px] font-medium tracking-wide text-[#1e1e1e]/40">{label}</span>
        <span className="text-[10px] text-[#1e1e1e]/25 cursor-default select-none">?</span>
      </div>
      <p className="mt-0.5 text-lg font-bold text-[#1e1e1e]">{value.toFixed(1)}</p>
      {/* Hover tooltip */}
      <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-56 -translate-x-1/2 rounded-lg border border-[#1e1e1e]/10 bg-[#1e1e1e] px-3 py-2.5 text-xs leading-relaxed text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100">
        {tooltip}
        {/* Arrow */}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-[#1e1e1e]" />
      </div>
    </div>
  )
}

const SCORE_TOOLTIPS = {
  technical: `How feasible the product is to build technically. Considers tech stack complexity, team skill requirements, third-party dependencies, and time-to-MVP. Higher = easier to build.`,
  market: `How strong the market opportunity is. Considers market size, demand signals, competition density, and monetisation potential. Higher = more attractive market.`,
  risk: `How well execution risk is managed under this approach. Considers funding risk, team risk, regulatory exposure, and go-to-market uncertainty. Higher = lower overall risk.`,
}

export function PlanDetail({ plan, onConfirm, confirming }: PlanDetailProps) {
  if (!plan) {
    return (
      <section className="mx-auto w-full max-w-3xl rounded-xl border border-dashed p-6">
        <h1 className="text-xl font-semibold">Plan not found</h1>
      </section>
    )
  }

  return (
    <section className="mx-auto w-full max-w-5xl rounded-xl border border-[#1e1e1e]/15 bg-white p-6 shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#1e1e1e]">{plan.name}</h1>
          <p className="mt-2 text-sm text-[#1e1e1e]/60">{plan.summary}</p>
        </div>
        <span className="shrink-0 rounded-lg bg-[#b9eb10] px-3 py-1.5 text-lg font-bold text-[#1e1e1e]">
          {plan.score_overall.toFixed(1)}
        </span>
      </div>

      {/* Two-column body */}
      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        {/* Left column: scores + reasoning + positioning + confirm */}
        <div className="space-y-4 lg:col-span-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <ScoreCard
              label="Technical"
              value={plan.scores.technical_feasibility}
              tooltip={SCORE_TOOLTIPS.technical}
            />
            <ScoreCard
              label="Market"
              value={plan.scores.market_viability}
              tooltip={SCORE_TOOLTIPS.market}
            />
            <ScoreCard
              label="Risk Control"
              value={plan.scores.execution_risk}
              tooltip={SCORE_TOOLTIPS.risk}
            />
          </div>

          <div className="space-y-3">
            <div className="rounded-lg border border-[#1e1e1e]/10 p-4">
              <h2 className="text-xs font-semibold tracking-wide text-[#1e1e1e]/50">
                Reasoning &middot; Technical
              </h2>
              <p className="mt-1.5 text-sm leading-relaxed text-[#1e1e1e]/70">
                {plan.reasoning.technical_feasibility}
              </p>
            </div>
            <div className="rounded-lg border border-[#1e1e1e]/10 p-4">
              <h2 className="text-xs font-semibold tracking-wide text-[#1e1e1e]/50">
                Reasoning &middot; Market
              </h2>
              <p className="mt-1.5 text-sm leading-relaxed text-[#1e1e1e]/70">
                {plan.reasoning.market_viability}
              </p>
            </div>
            <div className="rounded-lg border border-[#1e1e1e]/10 p-4">
              <h2 className="text-xs font-semibold tracking-wide text-[#1e1e1e]/50">
                Reasoning &middot; Execution Risk
              </h2>
              <p className="mt-1.5 text-sm leading-relaxed text-[#1e1e1e]/70">
                {plan.reasoning.execution_risk}
              </p>
            </div>
          </div>

          <div className="rounded-lg border border-[#1e1e1e]/10 p-4">
            <h2 className="text-xs font-semibold tracking-wide text-[#1e1e1e]/50">
              Recommended Positioning
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-[#1e1e1e]/70">
              {plan.recommended_positioning}
            </p>
          </div>

          {onConfirm ? (
            <button
              type="button"
              onClick={onConfirm}
              disabled={confirming}
              className="w-full rounded-xl bg-[#1e1e1e] px-5 py-3 text-sm font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {confirming ? 'Confirming\u2026' : 'Confirm This Plan'}
            </button>
          ) : null}
        </div>

        {/* Right column: competitors */}
        <div className="lg:col-span-2">
          <div className="rounded-xl border border-[#1e1e1e]/10 bg-[#f5f5f5] p-4">
            <h3 className="text-sm font-semibold text-[#1e1e1e]">Similar Products</h3>
            {!plan.competitors?.length ? (
              <p className="mt-3 text-xs text-[#1e1e1e]/40">
                No competitor data available for this plan.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {plan.competitors.map((c) => (
                  <li
                    key={c.name}
                    className="rounded-lg border border-[#1e1e1e]/8 bg-white px-3.5 py-3"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-[#1e1e1e]">{c.name}</span>
                      {c.url ? (
                        <a
                          href={c.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[#1e1e1e]/30 transition hover:text-[#1e1e1e]/60"
                        >
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            className="h-3.5 w-3.5"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                            />
                          </svg>
                        </a>
                      ) : null}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-[#1e1e1e]/50">
                      {c.similarity}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
