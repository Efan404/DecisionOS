import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { FeasibilityPage } from '../FeasibilityPage'
import { getIdea } from '../../../lib/api'
import { getLatestPath } from '../../../lib/dag-api'
import { useIdeasStore } from '../../../lib/ideas-store'
import { streamPost } from '../../../lib/sse'
import { useDecisionStore } from '../../../lib/store'
import { nextNavigationMock } from '../../../test/setup'

vi.mock('../../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/api')>()
  return {
    ...actual,
    getIdea: vi.fn(),
    postIdeaScopedAgent: vi.fn(),
  }
})

vi.mock('../../../lib/dag-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/dag-api')>()
  return {
    ...actual,
    getLatestPath: vi.fn(),
  }
})

vi.mock('../../../lib/sse', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/sse')>()
  return {
    ...actual,
    streamPost: vi.fn(),
    isSseEventError: vi.fn().mockReturnValue(false),
  }
})

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    message: vi.fn(),
  },
}))

describe('FeasibilityPage route scope', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    nextNavigationMock.setPathname('/ideas/idea-2/feasibility')

    useIdeasStore.setState({
      ideas: [
        {
          id: 'idea-1',
          workspace_id: 'default',
          title: 'Idea 1',
          stage: 'feasibility',
          status: 'draft',
          version: 10,
          created_at: '2026-02-20T00:00:00.000Z',
          updated_at: '2026-02-20T00:00:00.000Z',
        },
        {
          id: 'idea-2',
          workspace_id: 'default',
          title: 'Idea 2',
          stage: 'feasibility',
          status: 'draft',
          version: 20,
          created_at: '2026-02-20T00:00:00.000Z',
          updated_at: '2026-02-20T00:00:00.000Z',
        },
      ],
      activeIdeaId: 'idea-1',
      loading: false,
      error: null,
    })

    useDecisionStore.setState({
      context: {
        session_id: 'session-1',
        created_at: '2026-02-20T00:00:00.000Z',
        idea_seed: 'seed',
        confirmed_dag_path_id: 'path-2',
        confirmed_dag_node_id: 'node-2',
        confirmed_dag_node_content: 'Node content 2',
        confirmed_dag_path_summary: 'Path summary 2',
      },
    })

    vi.mocked(getLatestPath).mockResolvedValue({
      id: 'path-2',
      idea_id: 'idea-2',
      node_chain: ['node-1', 'node-2'],
      path_md: '# path',
      path_json: JSON.stringify({
        node_chain: [
          { id: 'node-1', content: 'Root', depth: 0 },
          { id: 'node-2', content: 'Node content 2', depth: 1 },
        ],
        summary: 'Path summary 2',
      }),
      created_at: '2026-02-20T00:00:00.000Z',
    })
    vi.mocked(getIdea).mockResolvedValue({
      id: 'idea-2',
      workspace_id: 'default',
      title: 'Idea 2',
      stage: 'feasibility',
      status: 'draft',
      version: 21,
      created_at: '2026-02-20T00:00:00.000Z',
      updated_at: '2026-02-20T00:00:00.000Z',
      archived_at: null,
      context: useDecisionStore.getState().context,
    })
    vi.mocked(streamPost).mockImplementation(async (path, payload, handlers) => {
      expect(path).toBe('/ideas/idea-2/agents/feasibility/stream')
      expect(payload).toMatchObject({
        version: 21,
        confirmed_path_id: 'path-2',
      })
      handlers.onDone?.({
        idea_id: 'idea-2',
        idea_version: 22,
        data: {
          plans: [
            {
              id: 'plan1',
              name: 'Plan 1',
              summary: 'Summary',
              score_overall: 8,
              scores: {
                technical_feasibility: 8,
                market_viability: 8,
                execution_risk: 7,
              },
              reasoning: {
                technical_feasibility: 'tech',
                market_viability: 'market',
                execution_risk: 'risk',
              },
              recommended_positioning: 'positioning',
            },
          ],
        },
      })
    })
  })

  test('uses the route idea instead of the active store idea for feasibility generation', async () => {
    render(<FeasibilityPage />)

    await waitFor(() => {
      expect(getLatestPath).toHaveBeenCalledWith('idea-2')
      expect(getIdea).toHaveBeenCalledWith('idea-2')
    })

    await userEvent.click(await screen.findByRole('button', { name: 'feasibility.generatePlans' }))

    await waitFor(() => {
      expect(streamPost).toHaveBeenCalled()
    })
  })
})
