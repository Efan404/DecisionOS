import { describe, expect, test } from 'vitest'

import {
  MOCK_COMPETITORS,
  MOCK_SIGNALS,
  fetchCompetitorsForIdea,
  fetchSignalsForIdea,
} from '../market-evidence'
import type { CompetitorCard, CompetitorSnapshot, MarketSignal } from '../market-evidence'

describe('market-evidence types and mock data', () => {
  test('MOCK_COMPETITORS has expected shape', () => {
    expect(MOCK_COMPETITORS.length).toBeGreaterThanOrEqual(2)

    const tracked = MOCK_COMPETITORS.find((c) => c.status === 'tracked')
    expect(tracked).toBeDefined()
    expect(tracked!.name).toBe('Competitor Alpha')
    expect(tracked!.canonical_url).toBe('https://alpha.example.com')
    expect(tracked!.category).toBe('Project Management')
    expect(tracked!.evidence_count).toBe(4)
    expect(tracked!.latest_snapshot).not.toBeNull()
    expect(tracked!.latest_snapshot!.quality_score).toBe(7.5)
    expect(tracked!.latest_snapshot!.traction_score).toBe(6.0)
    expect(tracked!.latest_snapshot!.relevance_score).toBe(8.2)
  })

  test('MOCK_COMPETITORS includes a candidate without snapshot', () => {
    const candidate = MOCK_COMPETITORS.find((c) => c.status === 'candidate')
    expect(candidate).toBeDefined()
    expect(candidate!.name).toBe('Competitor Beta')
    expect(candidate!.latest_snapshot).toBeNull()
  })

  test('MOCK_SIGNALS has expected shape', () => {
    expect(MOCK_SIGNALS.length).toBeGreaterThanOrEqual(2)

    const highSeverity = MOCK_SIGNALS.find((s) => s.severity === 'high')
    expect(highSeverity).toBeDefined()
    expect(highSeverity!.signal_type).toBe('market_news')
    expect(highSeverity!.title).toBe('Alpha raises Series B')
    expect(highSeverity!.evidence_source_id).toBe('es-1')
  })

  test('MOCK_SIGNALS includes a signal without evidence_source_id', () => {
    const noSource = MOCK_SIGNALS.find((s) => s.evidence_source_id === null)
    expect(noSource).toBeDefined()
    expect(noSource!.signal_type).toBe('community_buzz')
  })

  test('fetchCompetitorsForIdea returns mock data', async () => {
    const result = await fetchCompetitorsForIdea('any-idea')
    expect(result).toEqual(MOCK_COMPETITORS)
  })

  test('fetchSignalsForIdea returns mock data', async () => {
    const result = await fetchSignalsForIdea('any-idea')
    expect(result).toEqual(MOCK_SIGNALS)
  })

  test('CompetitorCard status is a valid union member', () => {
    const validStatuses: CompetitorCard['status'][] = ['candidate', 'tracked', 'archived']
    for (const comp of MOCK_COMPETITORS) {
      expect(validStatuses).toContain(comp.status)
    }
  })

  test('MarketSignal severity is a valid union member', () => {
    const validSeverities: MarketSignal['severity'][] = ['low', 'medium', 'high']
    for (const sig of MOCK_SIGNALS) {
      expect(validSeverities).toContain(sig.severity)
    }
  })

  test('MarketSignal signal_type is a valid union member', () => {
    const validTypes: MarketSignal['signal_type'][] = [
      'competitor_update',
      'market_news',
      'community_buzz',
      'pricing_change',
    ]
    for (const sig of MOCK_SIGNALS) {
      expect(validTypes).toContain(sig.signal_type)
    }
  })

  test('CompetitorSnapshot dates are valid ISO strings', () => {
    for (const comp of MOCK_COMPETITORS) {
      if (comp.latest_snapshot) {
        const date = new Date(comp.latest_snapshot.created_at)
        expect(date.getTime()).not.toBeNaN()
      }
    }
  })
})
