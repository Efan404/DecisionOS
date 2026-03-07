'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type CompetitorCard,
  type MarketSignal,
  fetchCompetitorsForIdea,
  fetchSignalsForIdea,
} from '../../lib/market-evidence'

export function useMarketEvidence(ideaId: string | null | undefined) {
  const [competitors, setCompetitors] = useState<CompetitorCard[]>([])
  const [signals, setSignals] = useState<MarketSignal[]>([])
  const [loadingCompetitors, setLoadingCompetitors] = useState(false)
  const [loadingSignals, setLoadingSignals] = useState(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const fetchAll = useCallback(async () => {
    if (!ideaId) return

    setLoadingCompetitors(true)
    setLoadingSignals(true)

    const [comps, sigs] = await Promise.all([
      fetchCompetitorsForIdea(ideaId),
      fetchSignalsForIdea(ideaId),
    ])

    if (mountedRef.current) {
      setCompetitors(comps)
      setSignals(sigs)
      setLoadingCompetitors(false)
      setLoadingSignals(false)
    }
  }, [ideaId])

  useEffect(() => {
    void fetchAll()
  }, [fetchAll])

  return {
    competitors,
    signals,
    loadingCompetitors,
    loadingSignals,
    refetch: fetchAll,
  }
}
