import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { PrdPage } from '../PrdPage'
import { downloadPrdBacklogExport, postIdeaScopedAgent, postPrdFeedback } from '../../../lib/api'
import { useIdeasStore } from '../../../lib/ideas-store'
import { useDecisionStore } from '../../../lib/store'
import { nextNavigationMock } from '../../../test/setup'

vi.mock('../../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/api')>()
  return {
    ...actual,
    postIdeaScopedAgent: vi.fn(),
    postPrdFeedback: vi.fn(),
    downloadPrdBacklogExport: vi.fn().mockResolvedValue(undefined),
  }
})

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    message: vi.fn(),
  },
}))

const buildPrdData = () => {
  const requirements = Array.from({ length: 6 }, (_, index) => ({
    id: `REQ-${index + 1}`,
    title: `Requirement ${index + 1}`,
    description: `Requirement description ${index + 1}`,
    rationale: 'Rationale',
    acceptance_criteria: ['Criterion A', 'Criterion B'],
    source_refs: ['step2', 'step3', 'step4'] as const,
  }))
  const backlogItems = Array.from({ length: 8 }, (_, index) => ({
    id: `BL-${index + 1}`,
    title: `Backlog ${index + 1}`,
    requirement_id: requirements[index % requirements.length].id,
    priority: 'P1' as const,
    type: 'story' as const,
    summary: `Backlog summary ${index + 1}`,
    acceptance_criteria: ['Ship endpoint', 'Add test'],
    source_refs: ['step4'] as const,
    depends_on: [],
  }))
  return {
    markdown: '# PRD',
    sections: [
      { id: 'problem', title: 'Problem', content: 'Problem section' },
      { id: 'users', title: 'Users', content: 'Users section' },
      { id: 'goals', title: 'Goals', content: 'Goals section' },
      { id: 'workflow', title: 'Workflow', content: 'Workflow section' },
      { id: 'scope', title: 'Scope', content: 'Scope section' },
      { id: 'risk', title: 'Risk', content: 'Risk section' },
    ],
    requirements,
    backlog: { items: backlogItems },
    generation_meta: {
      provider_id: 'mock',
      model: 'mock-v2',
      confirmed_path_id: 'path-1',
      selected_plan_id: 'plan-a',
      baseline_id: 'baseline-1',
    },
  }
}

const initStores = () => {
  const loadIdeaDetail = vi.fn().mockResolvedValue(null)
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
    },
  })
}

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
  output: buildPrdData(),
})

const initStoresWithBundle = () => {
  const loadIdeaDetail = vi.fn().mockResolvedValue(null)
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
}

describe('PrdPage export actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    initStoresWithBundle()
    nextNavigationMock.setSearchParams('baseline_id=baseline-1')
  })

  test('Export CSV button calls downloadPrdBacklogExport with csv format', async () => {
    render(<PrdPage />)
    const reqTab = await screen.findByRole('button', { name: /Requirements/ })
    await userEvent.click(reqTab)
    const csvButton = await screen.findByRole('button', { name: 'Export CSV' })
    await userEvent.click(csvButton)
    await waitFor(() => {
      expect(downloadPrdBacklogExport).toHaveBeenCalledWith('idea-1', 'csv')
    })
  })

  test('Export JSON button calls downloadPrdBacklogExport with json format', async () => {
    render(<PrdPage />)
    const reqTab = await screen.findByRole('button', { name: /Requirements/ })
    await userEvent.click(reqTab)
    const jsonButton = await screen.findByRole('button', { name: 'Export JSON' })
    await userEvent.click(jsonButton)
    await waitFor(() => {
      expect(downloadPrdBacklogExport).toHaveBeenCalledWith('idea-1', 'json')
    })
  })
})

describe('PrdPage baseline flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    initStores()
    nextNavigationMock.setSearchParams('baseline_id=baseline-1')
    vi.mocked(postIdeaScopedAgent).mockResolvedValue({
      idea_id: 'idea-1',
      idea_version: 13,
      data: buildPrdData(),
    })
    vi.mocked(postPrdFeedback).mockResolvedValue({
      idea_id: 'idea-1',
      idea_version: 14,
      data: {
        baseline_id: 'baseline-1',
        submitted_at: '2026-02-20T00:00:00.000Z',
        rating_overall: 5,
        rating_dimensions: {
          clarity: 5,
          completeness: 5,
          actionability: 5,
          scope_fit: 5,
        },
      },
    })
  })

  test('posts minimal PRD generation payload', async () => {
    render(<PrdPage />)
    await waitFor(() => {
      expect(postIdeaScopedAgent).toHaveBeenCalledWith('idea-1', 'prd', {
        version: 12,
        baseline_id: 'baseline-1',
      })
    })
  })

  test('renders backlog and requirement-linked output after generation', async () => {
    render(<PrdPage />)
    expect(await screen.findByText('Backlog 1')).toBeInTheDocument()
    expect(screen.getAllByText(/Requirement 1/).length).toBeGreaterThan(0)
  })

  test('shows explicit error state and retries generation', async () => {
    vi.mocked(postIdeaScopedAgent)
      .mockRejectedValueOnce(new Error('PRD generation failed'))
      .mockResolvedValueOnce({
        idea_id: 'idea-1',
        idea_version: 13,
        data: buildPrdData(),
      })

    render(<PrdPage />)
    expect(await screen.findByText('PRD generation failed')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => {
      expect(vi.mocked(postIdeaScopedAgent).mock.calls.length).toBeGreaterThanOrEqual(2)
    })
  })

  test('submits feedback via floating bubble after generation', async () => {
    render(<PrdPage />)
    await screen.findByText('Backlog 1')
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Good' })).toBeEnabled()
    })
    await userEvent.click(screen.getByRole('button', { name: 'Good' }))
    await waitFor(() => {
      expect(postPrdFeedback).toHaveBeenCalledWith(
        'idea-1',
        expect.objectContaining({
          baseline_id: 'baseline-1',
          rating_overall: 4,
        })
      )
    })
  })
})
