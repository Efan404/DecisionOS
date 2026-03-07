'use client'

import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useRouter } from 'next/navigation'
import { useOnboarding } from './useOnboarding'
import { useIdeasStore } from '../../lib/ideas-store'
import { TourOverlay } from './TourOverlay'
import { STEPS, STEP_ROUTES, _useTourState, _setState } from './tourState'

export default function TourController() {
  const { active, stepIndex } = _useTourState()
  const { shouldAutoStart, markCompleted } = useOnboarding()
  const router = useRouter()
  const activeIdeaId = useIdeasStore((s) => s.activeIdeaId)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  // Auto-start
  useEffect(() => {
    if (!shouldAutoStart) return
    const t = setTimeout(() => _setState({ active: true, stepIndex: 0 }), 600)
    return () => clearTimeout(t)
  }, [shouldAutoStart])

  const closeTour = useCallback(() => {
    _setState({ active: false })
    markCompleted()
  }, [markCompleted])

  const handleNext = useCallback(() => {
    const step = STEPS[stepIndex]
    if (step.nextRoute) {
      router.push(step.nextRoute)
    } else {
      const builder = STEP_ROUTES[stepIndex]
      if (builder) {
        const r = builder(activeIdeaId)
        if (r) router.push(r)
      }
    }
    if (stepIndex + 1 >= STEPS.length) {
      closeTour()
    } else {
      _setState({ stepIndex: stepIndex + 1 })
    }
  }, [stepIndex, router, closeTour, activeIdeaId])

  const handlePrev = useCallback(() => {
    _setState({ stepIndex: Math.max(0, stepIndex - 1) })
  }, [stepIndex])

  if (!mounted || !active) return null

  return createPortal(
    <TourOverlay
      stepIndex={stepIndex}
      onNext={handleNext}
      onPrev={handlePrev}
      onSkip={closeTour}
    />,
    document.body
  )
}
