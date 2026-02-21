import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { PrdPage } from '../PrdPage'
import { getScopeBaseline, postIdeaScopedAgent } from '../../../lib/api'
import { useIdeasStore } from '../../../lib/ideas-store'
import { useDecisionStore } from '../../../lib/store'
import { nextNavigationMock } from '../../../test/setup'

vi.mock('../../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/api')>()
  return {
    ...actual,
    getScopeBaseline: vi.fn(),
    postIdeaScopedAgent: vi.fn(),
  }
})

vi.mock('../../../lib/dag-api', () => ({
  getLatestPath: vi.fn().mockResolvedValue({ id: 'path-1' }),
  buildConfirmedPathContext: vi.fn().mockReturnValue({
    confirmed_path_id: 'path-1',
    confirmed_node_id: 'node-1',
    confirmed_node_content: 'Node content',
    confirmed_path_summary: 'Summary',
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    message: vi.fn(),
  },
}))

const initStores = () => {
  useIdeasStore.setState({
    activeIdeaId: 'idea-1',
    ideas: [
      {
        id: 'idea-1',
        workspace_id: 'default',
        title: 'Idea 1',
        stage: 'prd',
        status: 'draft',
        version: 12,
        created_at: '2026-02-20T00:00:00.000Z',
        updated_at: '2026-02-20T00:00:00.000Z',
      },
    ],
  })
  useDecisionStore.setState({
    context: {
      session_id: 'session-1',
      created_at: '2026-02-20T00:00:00.000Z',
      idea_seed: 'seed',
      selected_plan_id: 'plan-a',
      scope_frozen: true,
      current_scope_baseline_id: 'baseline-1',
      current_scope_baseline_version: 1,
      feasibility: {
        plans: [
          {
            id: 'plan-a',
            name: 'Plan A',
            summary: 'Summary',
            score_overall: 7.3,
            scores: {
              technical_feasibility: 7,
              market_viability: 8,
              execution_risk: 7,
            },
            reasoning: {
              technical_feasibility: 'tech',
              market_viability: 'market',
              execution_risk: 'risk',
            },
            recommended_positioning: 'position',
          },
        ],
      },
      scope: {
        in_scope: [{ id: 'in-1', title: 'MVP', desc: 'desc', priority: 'P1' as const }],
        out_scope: [{ id: 'out-1', title: 'Billing', desc: 'desc', reason: 'later' }],
      },
    },
  })
}

describe('PrdPage baseline selection', () => {
  beforeEach(() => {
    initStores()
    vi.mocked(postIdeaScopedAgent).mockResolvedValue({
      idea_id: 'idea-1',
      idea_version: 13,
      data: {
        markdown: '# PRD',
        sections: {
          problem_statement: 'problem',
          target_user: 'user',
          core_workflow: 'workflow',
          mvp_scope: 'scope',
          success_metrics: 'metrics',
          risk_analysis: 'risk',
        },
      },
    })
    vi.mocked(getScopeBaseline).mockResolvedValue({
      baseline: {
        id: 'baseline-1',
        idea_id: 'idea-1',
        version: 1,
        status: 'frozen',
        source_baseline_id: null,
        created_at: '2026-02-20T00:00:00.000Z',
        frozen_at: '2026-02-20T00:05:00.000Z',
      },
      items: [
        {
          id: 'item-1',
          baseline_id: 'baseline-1',
          lane: 'in',
          content: 'Core workflow',
          display_order: 0,
          created_at: '2026-02-20T00:00:00.000Z',
        },
      ],
    })
  })

  test('prefers frozen baseline when baseline_id is provided', async () => {
    nextNavigationMock.setSearchParams('baseline_id=baseline-1')

    render(<PrdPage />)
    await waitFor(() => {
      expect(getScopeBaseline).toHaveBeenCalledWith('idea-1', 'baseline-1')
    })
  })

  test('shows warning when baseline_id is missing', async () => {
    nextNavigationMock.setSearchParams('')

    render(<PrdPage />)
    expect(
      await screen.findByText('Using draft scope because no frozen baseline is selected.')
    ).toBeInTheDocument()
  })
})
