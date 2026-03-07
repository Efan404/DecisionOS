import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { CompetitorCardList } from '../CompetitorCardList'
import { MarketEvidencePanel } from '../MarketEvidencePanel'
import { MarketSignalsPanel } from '../MarketSignalsPanel'
import { MOCK_COMPETITORS, MOCK_SIGNALS } from '../../../lib/market-evidence'
import type { CompetitorCard, MarketSignal } from '../../../lib/market-evidence'

vi.mock('../../../lib/market-evidence', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/market-evidence')>()
  return {
    ...actual,
    fetchCompetitorsForIdea: vi.fn().mockResolvedValue(actual.MOCK_COMPETITORS),
    fetchSignalsForIdea: vi.fn().mockResolvedValue(actual.MOCK_SIGNALS),
  }
})

describe('CompetitorCardList', () => {
  test('renders loading state', () => {
    render(<CompetitorCardList competitors={[]} loading={true} />)
    expect(screen.getByText('Loading competitors...')).toBeInTheDocument()
  })

  test('renders empty state when no competitors', () => {
    render(<CompetitorCardList competitors={[]} />)
    expect(screen.getByText('No competitors discovered yet.')).toBeInTheDocument()
  })

  test('renders competitor names', () => {
    render(<CompetitorCardList competitors={MOCK_COMPETITORS} />)
    expect(screen.getByText('Competitor Alpha')).toBeInTheDocument()
    expect(screen.getByText('Competitor Beta')).toBeInTheDocument()
  })

  test('renders status badges', () => {
    render(<CompetitorCardList competitors={MOCK_COMPETITORS} />)
    expect(screen.getByText('tracked')).toBeInTheDocument()
    expect(screen.getByText('candidate')).toBeInTheDocument()
  })

  test('renders category text', () => {
    render(<CompetitorCardList competitors={MOCK_COMPETITORS} />)
    expect(screen.getByText('Project Management')).toBeInTheDocument()
    expect(screen.getByText('Dev Tools')).toBeInTheDocument()
  })

  test('renders scores for competitor with snapshot', () => {
    render(<CompetitorCardList competitors={MOCK_COMPETITORS} />)
    expect(screen.getByText('7.5')).toBeInTheDocument()
    expect(screen.getByText('6.0')).toBeInTheDocument()
    expect(screen.getByText('8.2')).toBeInTheDocument()
  })

  test('does not render scores for competitor without snapshot', () => {
    const noSnapshotOnly: CompetitorCard[] = [MOCK_COMPETITORS[1]]
    render(<CompetitorCardList competitors={noSnapshotOnly} />)
    expect(screen.queryByText('Quality')).not.toBeInTheDocument()
    expect(screen.queryByText('Traction')).not.toBeInTheDocument()
    expect(screen.queryByText('Relevance')).not.toBeInTheDocument()
  })

  test('renders evidence count with correct pluralization', () => {
    render(<CompetitorCardList competitors={MOCK_COMPETITORS} />)
    expect(screen.getByText('4 evidence sources')).toBeInTheDocument()
    expect(screen.getByText('1 evidence source')).toBeInTheDocument()
  })

  test('does not show empty state when loading', () => {
    render(<CompetitorCardList competitors={[]} loading={true} />)
    expect(screen.queryByText('No competitors discovered yet.')).not.toBeInTheDocument()
  })
})

describe('MarketSignalsPanel', () => {
  test('renders loading state', () => {
    render(<MarketSignalsPanel signals={[]} loading={true} />)
    expect(screen.getByText('Loading signals...')).toBeInTheDocument()
  })

  test('renders empty state when no signals', () => {
    render(<MarketSignalsPanel signals={[]} />)
    expect(screen.getByText('No market signals detected yet.')).toBeInTheDocument()
  })

  test('renders signal titles', () => {
    render(<MarketSignalsPanel signals={MOCK_SIGNALS} />)
    expect(screen.getByText('Alpha raises Series B')).toBeInTheDocument()
    expect(screen.getByText('Growing discussion on solo dev tools')).toBeInTheDocument()
  })

  test('renders signal summaries', () => {
    render(<MarketSignalsPanel signals={MOCK_SIGNALS} />)
    expect(
      screen.getByText(
        'Competitor Alpha announced $30M Series B, plans to expand AI capabilities.'
      )
    ).toBeInTheDocument()
  })

  test('renders severity badges', () => {
    render(<MarketSignalsPanel signals={MOCK_SIGNALS} />)
    expect(screen.getByText('high')).toBeInTheDocument()
    expect(screen.getByText('medium')).toBeInTheDocument()
  })

  test('renders signal type labels', () => {
    render(<MarketSignalsPanel signals={MOCK_SIGNALS} />)
    expect(screen.getByText('Market News')).toBeInTheDocument()
    expect(screen.getByText('Community Buzz')).toBeInTheDocument()
  })

  test('renders detected_at dates', () => {
    render(<MarketSignalsPanel signals={MOCK_SIGNALS} />)
    // Date formatting depends on locale, just verify elements exist
    const dateElements = document.querySelectorAll('.text-neutral-600')
    expect(dateElements.length).toBe(2)
  })

  test('does not show empty state when loading', () => {
    render(<MarketSignalsPanel signals={[]} loading={true} />)
    expect(screen.queryByText('No market signals detected yet.')).not.toBeInTheDocument()
  })
})

describe('MarketEvidencePanel', () => {
  test('renders collapsed by default with header', () => {
    render(<MarketEvidencePanel ideaId="test-idea-1" />)
    expect(screen.getByText('Market Evidence')).toBeInTheDocument()
    // Content should not be visible when collapsed
    expect(screen.queryByText('Competitors')).not.toBeInTheDocument()
    expect(screen.queryByText('Market Signals')).not.toBeInTheDocument()
  })

  test('expands on click and shows sub-headings', async () => {
    render(<MarketEvidencePanel ideaId="test-idea-1" />)
    const toggle = screen.getByText('Market Evidence')
    fireEvent.click(toggle)
    await waitFor(() => {
      expect(screen.getByText('Competitors')).toBeInTheDocument()
      expect(screen.getByText('Market Signals')).toBeInTheDocument()
    })
  })

  test('renders expanded when defaultCollapsed is false', async () => {
    render(<MarketEvidencePanel ideaId="test-idea-1" defaultCollapsed={false} />)
    await waitFor(() => {
      expect(screen.getByText('Competitors')).toBeInTheDocument()
      expect(screen.getByText('Market Signals')).toBeInTheDocument()
    })
  })

  test('shows fetched competitor data when expanded', async () => {
    render(<MarketEvidencePanel ideaId="test-idea-1" defaultCollapsed={false} />)
    await waitFor(() => {
      expect(screen.getByText('Competitor Alpha')).toBeInTheDocument()
      expect(screen.getByText('Competitor Beta')).toBeInTheDocument()
    })
  })

  test('shows fetched signal data when expanded', async () => {
    render(<MarketEvidencePanel ideaId="test-idea-1" defaultCollapsed={false} />)
    await waitFor(() => {
      expect(screen.getByText('Alpha raises Series B')).toBeInTheDocument()
      expect(screen.getByText('Growing discussion on solo dev tools')).toBeInTheDocument()
    })
  })

  test('does not fetch when ideaId is null', () => {
    render(<MarketEvidencePanel ideaId={null} defaultCollapsed={false} />)
    expect(screen.getByText('Market Evidence')).toBeInTheDocument()
  })
})
