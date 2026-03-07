'use client'

import { useCallback, useEffect, useState } from 'react'

const TOUR_KEY = 'decisionos_tour_completed'

export function useOnboarding() {
  const [shouldAutoStart, setShouldAutoStart] = useState(false)

  useEffect(() => {
    const completed = localStorage.getItem(TOUR_KEY)
    if (!completed) {
      setShouldAutoStart(true)
    }
  }, [])

  const markCompleted = useCallback(() => {
    localStorage.setItem(TOUR_KEY, 'true')
    setShouldAutoStart(false)
  }, [])

  const resetTour = useCallback(() => {
    localStorage.removeItem(TOUR_KEY)
  }, [])

  return { shouldAutoStart, markCompleted, resetTour }
}
