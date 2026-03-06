'use client'

import { useState } from 'react'

import type { PrdFeedbackDimensions } from '../../lib/schemas'

type FeedbackLevel = 'perfect' | 'good' | 'needs_work'

const FEEDBACK_MAP: Record<
  FeedbackLevel,
  { rating_overall: number; rating_dimensions: PrdFeedbackDimensions }
> = {
  perfect: {
    rating_overall: 5,
    rating_dimensions: { clarity: 5, completeness: 5, actionability: 5, scope_fit: 5 },
  },
  good: {
    rating_overall: 4,
    rating_dimensions: { clarity: 4, completeness: 4, actionability: 4, scope_fit: 4 },
  },
  needs_work: {
    rating_overall: 2,
    rating_dimensions: { clarity: 2, completeness: 2, actionability: 2, scope_fit: 2 },
  },
}

type PrdFeedbackBubbleProps = {
  onSubmit: (payload: {
    rating_overall: number
    rating_dimensions: PrdFeedbackDimensions
  }) => Promise<void>
  submitting?: boolean
  onDismiss: () => void
}

export function PrdFeedbackBubble({
  onSubmit,
  submitting = false,
  onDismiss,
}: PrdFeedbackBubbleProps) {
  const [submitted, setSubmitted] = useState(false)

  const handleClick = async (level: FeedbackLevel) => {
    try {
      await onSubmit(FEEDBACK_MAP[level])
      setSubmitted(true)
      setTimeout(onDismiss, 1200)
    } catch {
      // error handled by parent (toast)
    }
  }

  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-[bubble-in_0.3s_ease-out]">
      <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-3 shadow-lg">
        {submitted ? (
          <span className="text-sm text-emerald-600 font-medium">Thanks for your feedback!</span>
        ) : (
          <>
            <span className="text-sm font-medium text-slate-700">How&apos;s this PRD?</span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                disabled={submitting}
                onClick={() => void handleClick('perfect')}
                className="cursor-pointer rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 disabled:opacity-50"
              >
                Perfect
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => void handleClick('good')}
                className="cursor-pointer rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400 disabled:opacity-50"
              >
                Good
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => void handleClick('needs_work')}
                className="cursor-pointer rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-400 disabled:opacity-50"
              >
                Needs Work
              </button>
            </div>
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Dismiss feedback"
              className="ml-1 cursor-pointer rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            >
              <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M4 4l8 8M12 4l-8 8" />
              </svg>
            </button>
          </>
        )}
      </div>
    </div>
  )
}
