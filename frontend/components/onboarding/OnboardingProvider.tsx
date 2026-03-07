'use client'

import { createContext, useCallback, useContext } from 'react'
import dynamic from 'next/dynamic'
import { _setState } from './tourState'

// TourController loaded client-only — avoids SSR hydration mismatch
// that causes ForceClientRender flag and prevents useEffect from running
const TourController = dynamic(() => import('./TourController'), { ssr: false })

// ── Context ───────────────────────────────────────────────────────────────────

interface TourContextType {
  startTour: () => void
}

const TourContext = createContext<TourContextType>({ startTour: () => {} })

export function useTour() {
  return useContext(TourContext)
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  const startTour = useCallback(() => {
    _setState({ active: true, stepIndex: 0 })
  }, [])

  return (
    <TourContext.Provider value={{ startTour }}>
      {children}
      <TourController />
    </TourContext.Provider>
  )
}
