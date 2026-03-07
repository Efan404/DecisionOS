'use client'

import type { CardComponentProps } from 'onborda'

export function OnboardingCard({
  step,
  currentStep,
  totalSteps,
  nextStep,
  prevStep,
  arrow,
  skipTour,
}: CardComponentProps) {
  const progress = ((currentStep + 1) / totalSteps) * 100

  return (
    <div
      className="relative w-72 rounded-2xl p-5 shadow-2xl"
      style={{ background: '#1e1e1e', border: '1.5px solid #b9eb1044' }}
    >
      {/* Arrow pointer rendered by onborda */}
      {arrow}

      {/* Step counter */}
      <div className="mb-3 flex items-center justify-between">
        <span
          className="text-[10px] font-bold tracking-widest uppercase"
          style={{ color: '#b9eb10' }}
        >
          Step {currentStep + 1} / {totalSteps}
        </span>
        <button
          type="button"
          onClick={skipTour}
          className="text-[11px] text-white/30 transition hover:text-white/60"
        >
          Skip
        </button>
      </div>

      {/* Progress bar */}
      <div className="mb-4 h-0.5 w-full rounded-full bg-white/10">
        <div
          className="h-0.5 rounded-full transition-all duration-300"
          style={{ width: `${progress}%`, background: '#b9eb10' }}
        />
      </div>

      {/* Title */}
      {step.title && <p className="mb-1.5 text-sm font-bold text-white">{step.title}</p>}

      {/* Content */}
      <div className="text-[13px] leading-relaxed text-white/70">{step.content}</div>

      {/* Nav buttons */}
      <div className="mt-5 flex items-center justify-between gap-2">
        {currentStep > 0 ? (
          <button
            type="button"
            onClick={prevStep}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-[12px] font-medium text-white/60 transition hover:border-white/30 hover:text-white"
          >
            Back
          </button>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={nextStep}
          className="rounded-lg px-4 py-1.5 text-[12px] font-bold text-[#1e1e1e] transition hover:brightness-110"
          style={{ background: '#b9eb10' }}
        >
          {currentStep + 1 === totalSteps ? 'Done' : 'Next'}
        </button>
      </div>
    </div>
  )
}
