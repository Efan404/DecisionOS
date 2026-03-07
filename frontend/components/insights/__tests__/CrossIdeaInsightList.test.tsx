// @vitest-environment jsdom
import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'

import { CrossIdeaInsightList } from '../CrossIdeaInsightList'
import type { CrossIdeaInsightV2 } from '../../../lib/api'

const MOCK_INSIGHTS: CrossIdeaInsightV2[] = [
  {
    id: 'ins-1',
    idea_a_id: 'idea-a',
    idea_b_id: 'idea-b',
    idea_a_title: 'Idea Alpha',
    idea_b_title: 'Idea Beta',
    insight_type: 'execution_reuse',
    summary: 'Both ideas share a common notification subsystem.',
    why_it_matters: 'Reusing this component saves two weeks of development time.',
    recommended_action: 'reuse_scope',
    confidence: 0.87,
    similarity_score: 0.72,
    created_at: '2026-03-07T10:00:00Z',
  },
  {
    id: 'ins-2',
    idea_a_id: 'idea-c',
    idea_b_id: 'idea-d',
    idea_a_title: 'Idea Gamma',
    idea_b_title: 'Idea Delta',
    insight_type: 'merge_candidate',
    summary: 'These ideas target the same user segment with overlapping features.',
    why_it_matters: 'Merging avoids internal competition and duplicated effort.',
    recommended_action: 'merge_ideas',
    confidence: 0.63,
    similarity_score: 0.91,
    created_at: '2026-03-07T11:00:00Z',
  },
  {
    id: 'ins-3',
    idea_a_id: 'idea-e',
    idea_b_id: 'idea-f',
    idea_a_title: 'Idea Epsilon',
    idea_b_title: 'Idea Zeta',
    insight_type: 'positioning_conflict',
    summary: 'Both ideas compete for the same market positioning.',
    why_it_matters: 'You need to differentiate or prioritise one.',
    recommended_action: 'compare_feasibility',
    confidence: null,
    similarity_score: null,
    created_at: '2026-03-07T12:00:00Z',
  },
]

describe('CrossIdeaInsightList', () => {
  afterEach(() => {
    cleanup()
  })

  test('renders insight type badges', () => {
    render(<CrossIdeaInsightList insights={MOCK_INSIGHTS} />)
    expect(screen.getByText('Execution Reuse')).toBeTruthy()
    expect(screen.getByText('Merge Candidate')).toBeTruthy()
    expect(screen.getByText('Positioning Conflict')).toBeTruthy()
  })

  test('renders summary and why_it_matters', () => {
    render(<CrossIdeaInsightList insights={MOCK_INSIGHTS} />)
    expect(screen.getByText('Both ideas share a common notification subsystem.')).toBeTruthy()
    expect(screen.getByText('Reusing this component saves two weeks of development time.')).toBeTruthy()
    expect(screen.getByText('These ideas target the same user segment with overlapping features.')).toBeTruthy()
    expect(screen.getByText('Merging avoids internal competition and duplicated effort.')).toBeTruthy()
  })

  test('renders recommended action labels', () => {
    render(<CrossIdeaInsightList insights={MOCK_INSIGHTS} />)
    expect(screen.getByText('Reuse Scope')).toBeTruthy()
    expect(screen.getByText('Consider Merge')).toBeTruthy()
    expect(screen.getByText('Compare Plans')).toBeTruthy()
  })

  test('renders confidence when present', () => {
    render(<CrossIdeaInsightList insights={MOCK_INSIGHTS} />)
    expect(screen.getByText('87% confidence')).toBeTruthy()
    expect(screen.getByText('63% confidence')).toBeTruthy()
  })

  test('does not render confidence when null', () => {
    const noConfidence: CrossIdeaInsightV2[] = [MOCK_INSIGHTS[2]]
    render(<CrossIdeaInsightList insights={noConfidence} />)
    expect(screen.queryByText(/confidence/)).toBeNull()
  })

  test('renders related idea titles', () => {
    render(<CrossIdeaInsightList insights={MOCK_INSIGHTS} />)
    expect(screen.getByText(/Idea Alpha/)).toBeTruthy()
    expect(screen.getByText(/Idea Beta/)).toBeTruthy()
    expect(screen.getByText(/Idea Gamma/)).toBeTruthy()
    expect(screen.getByText(/Idea Delta/)).toBeTruthy()
  })

  test('handles empty state', () => {
    render(<CrossIdeaInsightList insights={[]} />)
    expect(screen.getByText('No cross-idea insights found yet.')).toBeTruthy()
  })

  test('handles loading state', () => {
    render(<CrossIdeaInsightList insights={[]} loading={true} />)
    expect(screen.getByText('Analyzing connections...')).toBeTruthy()
    expect(screen.queryByText('No cross-idea insights found yet.')).toBeNull()
  })

  test('does not show empty state when loading', () => {
    render(<CrossIdeaInsightList insights={[]} loading={true} />)
    expect(screen.queryByText('No cross-idea insights found yet.')).toBeNull()
  })
})
