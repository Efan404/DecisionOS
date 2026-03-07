// @vitest-environment jsdom
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

// Mock the store
vi.mock('../../../lib/ideas-store', () => ({
  useIdeasStore: vi.fn().mockImplementation((selector: (state: unknown) => unknown) =>
    selector({
      ideas: [
        { id: 'idea-1', title: 'Test Idea', stage: 'idea_canvas', status: 'active', version: 1 },
      ],
      activeIdeaId: 'idea-1',
    })
  ),
}))

// Mock api
vi.mock('../../../lib/api', () => ({
  listMarketInsightsForIdea: vi.fn().mockResolvedValue([
    {
      id: 'insight-1',
      idea_id: 'idea-1',
      summary: 'Market is growing',
      decision_impact: 'High impact',
      recommended_actions: ['Do this', 'Do that'],
      signal_count: 5,
      generated_at: '2026-01-01T00:00:00Z',
    },
  ]),
  streamMarketInsight: vi.fn().mockResolvedValue(undefined),
}))

import { InsightsPage } from '../InsightsPage'

describe('InsightsPage', () => {
  it('renders the page title', async () => {
    render(<InsightsPage />)
    expect(screen.getByText('Market Insights')).toBeInTheDocument()
  })

  it('shows Analyze button', async () => {
    render(<InsightsPage />)
    expect(screen.getByText(/Analyze/i)).toBeInTheDocument()
  })

  it('loads and displays existing insights', async () => {
    render(<InsightsPage />)
    await waitFor(() => expect(screen.getByText('Market is growing')).toBeInTheDocument())
  })
})
