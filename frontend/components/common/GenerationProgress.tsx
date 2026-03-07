'use client'

type StepStatus = 'pending' | 'active' | 'done'

export type ProgressStep = {
  key: string
  label: string
  status: StepStatus
}

type Props = {
  steps: ProgressStep[]
  isActive: boolean
  /** Optional explicit pct (0-100) from backend — overrides step-count calculation */
  pct?: number
}

export function GenerationProgress({ steps, isActive, pct: pctProp }: Props) {
  const doneCount = steps.filter((s) => s.status === 'done').length
  const activeCount = steps.filter((s) => s.status === 'active').length
  const calculatedPct =
    steps.length > 0 ? Math.round(((doneCount + activeCount * 0.5) / steps.length) * 100) : 0
  // Use explicit pct from backend if provided (more accurate), else fall back to step-count
  const pct = pctProp !== undefined ? pctProp : calculatedPct

  return (
    <div className="rounded-xl border border-zinc-200 bg-white px-5 py-4 shadow-sm">
      {/* Progress bar */}
      <div className="mb-4 h-1 w-full overflow-hidden rounded-full bg-zinc-100">
        {isActive ? (
          <div
            className="h-full rounded-full bg-[#b9eb10] transition-all duration-700 ease-out"
            style={{ width: `${Math.max(4, pct)}%` }}
          />
        ) : (
          <div className="h-full w-full rounded-full bg-[#b9eb10]" />
        )}
      </div>

      {/* Step list */}
      <ul className="space-y-2">
        {steps.map((step) => (
          <li key={step.key} className="flex items-center gap-2.5 text-sm">
            {step.status === 'done' ? (
              <svg
                aria-hidden="true"
                className="h-4 w-4 shrink-0 text-[#b9eb10]"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M2.5 8.5l3.5 3.5 7-7" />
              </svg>
            ) : step.status === 'active' ? (
              <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
                <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-[#b9eb10] opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#b9eb10]" />
              </span>
            ) : (
              <span className="h-4 w-4 shrink-0 rounded-full border border-zinc-200" />
            )}
            <span
              className={
                step.status === 'done'
                  ? 'text-zinc-400 line-through'
                  : step.status === 'active'
                    ? 'font-medium text-zinc-800'
                    : 'text-zinc-400'
              }
            >
              {step.label}
              {step.status === 'active' && (
                <span className="ml-1 inline-flex gap-0.5">
                  <span className="animate-bounce" style={{ animationDelay: '0ms' }}>
                    .
                  </span>
                  <span className="animate-bounce" style={{ animationDelay: '150ms' }}>
                    .
                  </span>
                  <span className="animate-bounce" style={{ animationDelay: '300ms' }}>
                    .
                  </span>
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
