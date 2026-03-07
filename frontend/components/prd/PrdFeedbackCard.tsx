import { useState } from 'react'
import { useTranslations } from 'next-intl'

import type { PrdFeedbackDimensions, PrdFeedbackLatest } from '../../lib/schemas'

type PrdFeedbackSubmitInput = {
  rating_overall: number
  rating_dimensions: PrdFeedbackDimensions
  comment?: string
}

type PrdFeedbackCardProps = {
  baselineId: string
  latest?: PrdFeedbackLatest
  disabled?: boolean
  submitting?: boolean
  errorMessage?: string | null
  onSubmit: (payload: PrdFeedbackSubmitInput) => Promise<void>
}

const DEFAULT_DIMENSIONS: PrdFeedbackDimensions = {
  clarity: 4,
  completeness: 4,
  actionability: 4,
  scope_fit: 4,
}

const RatingButtons = ({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (next: number) => void
}) => (
  <div>
    <p className="mb-1 text-xs font-medium text-slate-700">{label}</p>
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((score) => (
        <button
          key={score}
          type="button"
          onClick={() => onChange(score)}
          className={`min-h-11 min-w-11 cursor-pointer rounded-md border text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400 ${
            value === score
              ? 'border-cyan-600 bg-cyan-600 text-white'
              : 'border-slate-300 bg-white text-slate-700'
          }`}
        >
          {score}
        </button>
      ))}
    </div>
  </div>
)

export function PrdFeedbackCard({
  baselineId,
  latest,
  disabled = false,
  submitting = false,
  errorMessage = null,
  onSubmit,
}: PrdFeedbackCardProps) {
  const t = useTranslations('prd')
  const [expanded, setExpanded] = useState(false)
  const [overall, setOverall] = useState<number>(latest?.rating_overall ?? 4)
  const [dimensions, setDimensions] = useState<PrdFeedbackDimensions>(
    latest?.rating_dimensions ?? DEFAULT_DIMENSIONS
  )
  const [comment, setComment] = useState(latest?.comment ?? '')
  const [submitState, setSubmitState] = useState<'idle' | 'success' | 'failed'>('idle')

  const submit = async (input: PrdFeedbackSubmitInput) => {
    setSubmitState('idle')
    try {
      await onSubmit(input)
      setSubmitState('success')
    } catch {
      setSubmitState('failed')
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <header>
        <h2 className="text-sm font-semibold text-slate-900">Output Feedback</h2>
        <p className="text-xs text-slate-600">
          Only the latest feedback is kept for this baseline.
        </p>
        <p className="text-xs text-slate-500">Baseline: {baselineId}</p>
      </header>

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          disabled={disabled || submitting}
          onClick={() =>
            void submit({
              rating_overall: 5,
              rating_dimensions: { clarity: 5, completeness: 5, actionability: 5, scope_fit: 5 },
            })
          }
          className="min-h-11 cursor-pointer rounded-md border border-emerald-300 bg-emerald-50 px-4 text-sm text-emerald-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-50"
        >
          Good
        </button>
        <button
          type="button"
          disabled={disabled || submitting}
          onClick={() =>
            void submit({
              rating_overall: 2,
              rating_dimensions: { clarity: 2, completeness: 2, actionability: 2, scope_fit: 2 },
            })
          }
          className="min-h-11 cursor-pointer rounded-md border border-amber-300 bg-amber-50 px-4 text-sm text-amber-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-400 disabled:opacity-50"
        >
          Needs Work
        </button>
        <button
          type="button"
          onClick={() => setExpanded((previous) => !previous)}
          className="min-h-11 cursor-pointer rounded-md border border-slate-300 px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400"
        >
          {expanded ? 'Hide Details' : 'Detailed Rating'}
        </button>
      </div>

      {expanded ? (
        <form
          className="mt-3 space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            void submit({
              rating_overall: overall,
              rating_dimensions: dimensions,
              comment: comment.trim() ? comment.trim() : undefined,
            })
          }}
        >
          <RatingButtons label="Overall" value={overall} onChange={setOverall} />
          <RatingButtons
            label="Clarity"
            value={dimensions.clarity}
            onChange={(next) => setDimensions((previous) => ({ ...previous, clarity: next }))}
          />
          <RatingButtons
            label="Completeness"
            value={dimensions.completeness}
            onChange={(next) => setDimensions((previous) => ({ ...previous, completeness: next }))}
          />
          <RatingButtons
            label="Actionability"
            value={dimensions.actionability}
            onChange={(next) => setDimensions((previous) => ({ ...previous, actionability: next }))}
          />
          <RatingButtons
            label="Scope Fit"
            value={dimensions.scope_fit}
            onChange={(next) => setDimensions((previous) => ({ ...previous, scope_fit: next }))}
          />
          <label className="block text-xs text-slate-700">
            Comment
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              rows={3}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-2 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={disabled || submitting}
            className="min-h-11 cursor-pointer rounded-md bg-slate-900 px-4 text-sm text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400 disabled:opacity-50"
          >
            {submitting ? t('feedback.submitting') : t('feedback.submit')}
          </button>
        </form>
      ) : null}

      {submitState === 'success' ? (
        <p className="mt-2 text-xs text-emerald-700">Feedback saved.</p>
      ) : null}
      {submitState === 'failed' || errorMessage ? (
        <p className="mt-2 text-xs text-red-700">{errorMessage ?? 'Feedback submission failed.'}</p>
      ) : null}
    </section>
  )
}
