import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { PrdPage } from '../PrdPage'
import { getIdea } from '../../../lib/api'
import { useIdeasStore } from '../../../lib/ideas-store'
import { streamPost } from '../../../lib/sse'
import { useDecisionStore } from '../../../lib/store'
import { nextNavigationMock } from '../../../test/setup'

vi.mock('../../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/api')>()
  return {
    ...actual,
    getIdea: vi.fn(),
  }
})

vi.mock('../../../lib/sse', () => ({
  streamPost: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    message: vi.fn(),
  },
}))

const buildPrdBundle = () => ({
  baseline_id: 'baseline-1',
  context_fingerprint: 'fp-test',
  generated_at: '2026-03-06T10:00:00Z',
  generation_meta: {
    provider_id: 'mock',
    model: 'mock-v1',
    confirmed_path_id: 'path-1',
    selected_plan_id: 'plan-a',
    baseline_id: 'baseline-1',
  },
  output: {
    markdown: '# Existing PRD',
    sections: [
      { id: 'problem', title: 'Problem', content: 'Problem section' },
      { id: 'users', title: 'Users', content: 'Users section' },
    ],
    requirements: [
      {
        id: 'REQ-1',
        title: 'Requirement 1',
        description: 'Requirement description 1',
        rationale: 'Rationale',
        acceptance_criteria: ['Criterion A', 'Criterion B'],
        source_refs: ['step2', 'step3'],
      },
    ],
    backlog: {
      items: [
        {
          id: 'BL-1',
          title: 'Backlog 1',
          requirement_id: 'REQ-1',
          priority: 'P1',
          type: 'story',
          summary: 'Backlog summary 1',
          acceptance_criteria: ['Ship endpoint', 'Add test'],
          source_refs: ['step4'],
          depends_on: [],
        },
      ],
    },
    generation_meta: {
      provider_id: 'mock',
      model: 'mock-v1',
      confirmed_path_id: 'path-1',
      selected_plan_id: 'plan-a',
      baseline_id: 'baseline-1',
    },
  },
})

describe('PrdPage stream recovery', () => {
  let loadIdeaDetail: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    nextNavigationMock.setSearchParams('baseline_id=baseline-1')
    loadIdeaDetail = vi.fn().mockResolvedValue(null)

    useIdeasStore.setState({
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
      activeIdeaId: 'idea-1',
      loading: false,
      error: null,
      loadIdeaDetail,
    })

    useDecisionStore.setState({
      context: {
        session_id: 'session-1',
        created_at: '2026-02-20T00:00:00.000Z',
        idea_seed: 'seed',
        selected_plan_id: 'plan-a',
        confirmed_dag_path_id: 'path-1',
        scope_frozen: true,
        current_scope_baseline_id: 'baseline-1',
        current_scope_baseline_version: 1,
        scope: {
          in_scope: [{ id: 'in-1', title: 'MVP', desc: 'desc', priority: 'P1' as const }],
          out_scope: [{ id: 'out-1', title: 'Billing', desc: 'desc', reason: 'later' }],
        },
        prd_bundle: buildPrdBundle(),
      },
    })

    vi.mocked(getIdea).mockResolvedValue({
      id: 'idea-1',
      workspace_id: 'default',
      title: 'Idea 1',
      stage: 'prd',
      status: 'draft',
      version: 13,
      created_at: '2026-02-20T00:00:00.000Z',
      updated_at: '2026-02-20T00:00:00.000Z',
      archived_at: null,
      context: useDecisionStore.getState().context,
    })
  })

  test('keeps the previous PRD output visible when regenerate stream fails', async () => {
    vi.mocked(streamPost).mockRejectedValue(new Error('PRD stream failed'))

    render(<PrdPage />)

    await userEvent.click(await screen.findByRole('button', { name: /prd\.tabRequirements/i }))
    expect(await screen.findByText('Backlog 1')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'prd.regenerate' }))

    await waitFor(() => {
      expect(streamPost).toHaveBeenCalled()
      expect(screen.getByText('Backlog 1')).toBeInTheDocument()
    })
  })

  test('loads the refreshed PRD bundle after regenerate completes', async () => {
    loadIdeaDetail.mockResolvedValue({
      id: 'idea-1',
      workspace_id: 'default',
      title: 'Idea 1',
      stage: 'prd',
      status: 'draft',
      version: 14,
      created_at: '2026-02-20T00:00:00.000Z',
      updated_at: '2026-02-20T00:00:00.000Z',
      archived_at: null,
      context: {
        ...useDecisionStore.getState().context,
        prd_bundle: {
          ...buildPrdBundle(),
          output: {
            ...buildPrdBundle().output,
            backlog: {
              items: [
                {
                  ...buildPrdBundle().output.backlog.items[0],
                  id: 'BL-99',
                  title: 'Backlog 99',
                  summary: 'Backlog summary 99',
                },
              ],
            },
          },
        },
      },
    })
    vi.mocked(streamPost).mockImplementation(async (_path, _payload, handlers) => {
      handlers.onDone?.({ idea_id: 'idea-1', idea_version: 14 })
    })

    render(<PrdPage />)

    await userEvent.click(await screen.findByRole('button', { name: /prd\.tabRequirements/i }))
    expect(await screen.findByText('Backlog 1')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'prd.regenerate' }))

    await waitFor(() => {
      expect(loadIdeaDetail).toHaveBeenCalledWith('idea-1')
      expect(screen.getByText('Backlog 99')).toBeInTheDocument()
    })
  })
})
