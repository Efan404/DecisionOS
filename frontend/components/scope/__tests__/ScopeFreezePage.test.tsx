import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ScopeFreezePage } from '../ScopeFreezePage'
import { useIdeasStore } from '../../../lib/ideas-store'
import { useDecisionStore } from '../../../lib/store'
import { nextNavigationMock } from '../../../test/setup'
import {
  bootstrapScopeDraft,
  createScopeNewVersion,
  freezeScope,
  getScopeDraft,
  patchIdeaContext,
  postIdeaScopedAgent,
  patchScopeDraft,
} from '../../../lib/api'

vi.mock('../../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/api')>()
  return {
    ...actual,
    getScopeDraft: vi.fn(),
    bootstrapScopeDraft: vi.fn(),
    patchScopeDraft: vi.fn(),
    freezeScope: vi.fn(),
    createScopeNewVersion: vi.fn(),
    patchIdeaContext: vi.fn(),
    postIdeaScopedAgent: vi.fn(),
  }
})

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    message: vi.fn(),
  },
}))

const draftData = {
  readonly: false,
  baseline: {
    id: 'baseline-1',
    idea_id: 'idea-1',
    version: 1,
    status: 'draft' as const,
    source_baseline_id: null,
    created_at: '2026-02-20T00:00:00.000Z',
    frozen_at: null,
  },
  items: [
    {
      id: 'item-in',
      baseline_id: 'baseline-1',
      lane: 'in' as const,
      content: 'Core workflow',
      display_order: 0,
      created_at: '2026-02-20T00:00:00.000Z',
    },
    {
      id: 'item-out',
      baseline_id: 'baseline-1',
      lane: 'out' as const,
      content: 'Billing v2',
      display_order: 0,
      created_at: '2026-02-20T00:00:00.000Z',
    },
  ],
}

const initStores = () => {
  useIdeasStore.setState({
    activeIdeaId: 'idea-1',
    ideas: [
      {
        id: 'idea-1',
        workspace_id: 'default',
        title: 'Idea 1',
        stage: 'scope_freeze',
        status: 'draft',
        version: 7,
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
      confirmed_dag_path_id: 'path-1',
      confirmed_dag_node_id: 'node-1',
      confirmed_dag_node_content: 'Confirmed node',
      confirmed_dag_path_summary: 'Confirmed summary',
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
    },
  })
  nextNavigationMock.setPathname('/ideas/idea-1/scope-freeze')
}

const buildIdeaDetail = (version: number) => ({
  id: 'idea-1',
  workspace_id: 'default',
  title: 'Idea 1',
  stage: 'scope_freeze' as const,
  status: 'draft' as const,
  version,
  created_at: '2026-02-20T00:00:00.000Z',
  updated_at: '2026-02-20T00:00:00.000Z',
  context: useDecisionStore.getState().context,
})

describe('ScopeFreezePage baseline flow', () => {
  let loadIdeaDetailMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    initStores()
    vi.mocked(getScopeDraft).mockResolvedValue(draftData)
    loadIdeaDetailMock = vi.fn().mockResolvedValue(buildIdeaDetail(9))
    useIdeasStore.setState({
      loadIdeaDetail: loadIdeaDetailMock,
    })
    vi.mocked(patchIdeaContext).mockResolvedValue(buildIdeaDetail(9))
  })

  test('loads scope draft and renders both lanes', async () => {
    render(<ScopeFreezePage />)

    await waitFor(() => {
      expect(getScopeDraft).toHaveBeenCalledWith('idea-1')
    })

    expect(await screen.findByText('Core workflow')).toBeInTheDocument()
    expect(screen.getByText('Billing v2')).toBeInTheDocument()
  })

  test('freezes draft and allows creating new version', async () => {
    vi.mocked(freezeScope).mockResolvedValue({
      idea_id: 'idea-1',
      idea_version: 8,
      data: {
        ...draftData,
        readonly: true,
        baseline: {
          ...draftData.baseline,
          status: 'frozen',
          frozen_at: '2026-02-20T00:20:00.000Z',
        },
      },
    })
    vi.mocked(createScopeNewVersion).mockResolvedValue({
      idea_id: 'idea-1',
      idea_version: 9,
      data: {
        ...draftData,
        baseline: {
          ...draftData.baseline,
          id: 'baseline-2',
          version: 2,
          source_baseline_id: 'baseline-1',
        },
      },
    })

    render(<ScopeFreezePage />)
    await screen.findByText('Core workflow')

    await userEvent.click(screen.getByRole('button', { name: 'Freeze Baseline' }))
    await waitFor(() => {
      expect(freezeScope).toHaveBeenCalledWith('idea-1', { version: 7 })
    })
    expect(await screen.findByRole('button', { name: 'Create New Version' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Create New Version' }))
    await waitFor(() => {
      expect(createScopeNewVersion).toHaveBeenCalledWith('idea-1', { version: 9 })
    })
  })

  test('adds and deletes draft item via patch API', async () => {
    const withAddedItem = {
      ...draftData,
      items: [
        ...draftData.items,
        {
          id: 'item-new',
          baseline_id: 'baseline-1',
          lane: 'in' as const,
          content: 'MVP onboarding',
          display_order: 1,
          created_at: '2026-02-20T00:00:00.000Z',
        },
      ],
    }
    vi.mocked(patchScopeDraft)
      .mockResolvedValueOnce({
        idea_id: 'idea-1',
        idea_version: 8,
        data: withAddedItem,
      })
      .mockResolvedValueOnce({
        idea_id: 'idea-1',
        idea_version: 9,
        data: draftData,
      })

    render(<ScopeFreezePage />)
    await screen.findByText('Core workflow')

    await userEvent.type(screen.getByLabelText('Add item to IN scope'), 'MVP onboarding')
    await userEvent.click(screen.getByRole('button', { name: 'Add IN Item' }))

    await waitFor(() => {
      expect(patchScopeDraft).toHaveBeenCalledWith(
        'idea-1',
        expect.objectContaining({
          version: 7,
          items: expect.arrayContaining([
            expect.objectContaining({ lane: 'in', content: 'MVP onboarding' }),
          ]),
        })
      )
    })

    await userEvent.click(screen.getByRole('button', { name: 'Delete MVP onboarding' }))
    await waitFor(() => {
      expect(patchScopeDraft).toHaveBeenCalledTimes(2)
    })
  })

  test('bootstraps draft when no draft exists', async () => {
    vi.mocked(getScopeDraft).mockRejectedValueOnce(
      Object.assign(new Error('Request failed with 404'), { status: 404 })
    )
    vi.mocked(bootstrapScopeDraft).mockResolvedValueOnce({
      idea_id: 'idea-1',
      idea_version: 8,
      data: draftData,
    })

    render(<ScopeFreezePage />)
    await waitFor(() => {
      expect(bootstrapScopeDraft).toHaveBeenCalledWith('idea-1', { version: 7 })
    })
  })

  test('hydrates empty draft from persisted context.scope', async () => {
    useDecisionStore.setState({
      context: {
        ...useDecisionStore.getState().context,
        scope: {
          in_scope: [{ id: 'in-1', title: 'In One', desc: 'desc', priority: 'P1' }],
          out_scope: [{ id: 'out-1', title: 'Out One', desc: 'desc', reason: 'later' }],
        },
      },
    })
    vi.mocked(getScopeDraft).mockResolvedValueOnce({
      ...draftData,
      items: [],
    })
    vi.mocked(patchScopeDraft).mockResolvedValueOnce({
      idea_id: 'idea-1',
      idea_version: 8,
      data: {
        ...draftData,
        items: [
          {
            id: 'item-1',
            baseline_id: 'baseline-1',
            lane: 'in',
            content: 'In One',
            display_order: 0,
            created_at: '2026-02-20T00:00:00.000Z',
          },
          {
            id: 'item-2',
            baseline_id: 'baseline-1',
            lane: 'out',
            content: 'Out One',
            display_order: 0,
            created_at: '2026-02-20T00:00:00.000Z',
          },
        ],
      },
    })

    render(<ScopeFreezePage />)

    await waitFor(() => {
      expect(patchScopeDraft).toHaveBeenCalledWith('idea-1', {
        version: 7,
        items: [
          { lane: 'in', content: 'In One', display_order: 0 },
          { lane: 'out', content: 'Out One', display_order: 0 },
        ],
      })
    })
    expect(postIdeaScopedAgent).not.toHaveBeenCalled()
  })

  test('generates scope then patches empty draft using latest idea version', async () => {
    vi.mocked(getScopeDraft).mockResolvedValueOnce({
      ...draftData,
      items: [],
    })
    vi.mocked(postIdeaScopedAgent).mockResolvedValueOnce({
      idea_id: 'idea-1',
      idea_version: 8,
      data: {
        in_scope: [{ id: 'in-1', title: 'Generated In', desc: 'desc', priority: 'P1' }],
        out_scope: [{ id: 'out-1', title: 'Generated Out', desc: 'desc', reason: 'later' }],
      },
    })
    vi.mocked(patchScopeDraft).mockResolvedValueOnce({
      idea_id: 'idea-1',
      idea_version: 9,
      data: {
        ...draftData,
        items: [
          {
            id: 'item-in-generated',
            baseline_id: 'baseline-1',
            lane: 'in',
            content: 'Generated In',
            display_order: 0,
            created_at: '2026-02-20T00:00:00.000Z',
          },
          {
            id: 'item-out-generated',
            baseline_id: 'baseline-1',
            lane: 'out',
            content: 'Generated Out',
            display_order: 0,
            created_at: '2026-02-20T00:00:00.000Z',
          },
        ],
      },
    })

    render(<ScopeFreezePage />)

    await waitFor(() => {
      expect(postIdeaScopedAgent).toHaveBeenCalledWith('idea-1', 'scope', {
        version: 7,
        idea_seed: 'seed',
        confirmed_path_id: 'path-1',
        confirmed_node_id: 'node-1',
        confirmed_node_content: 'Confirmed node',
        confirmed_path_summary: 'Confirmed summary',
        selected_plan_id: 'plan-a',
        feasibility: expect.any(Object),
      })
    })
    await waitFor(() => {
      expect(patchScopeDraft).toHaveBeenCalledWith('idea-1', {
        version: 8,
        items: [
          { lane: 'in', content: 'Generated In', display_order: 0 },
          { lane: 'out', content: 'Generated Out', display_order: 0 },
        ],
      })
    })
  })

  test('continue to PRD stays disabled for draft baseline and enables only when frozen', async () => {
    vi.mocked(freezeScope).mockResolvedValueOnce({
      idea_id: 'idea-1',
      idea_version: 8,
      data: {
        ...draftData,
        readonly: true,
        baseline: {
          ...draftData.baseline,
          status: 'frozen',
          frozen_at: '2026-02-20T00:20:00.000Z',
        },
      },
    })

    render(<ScopeFreezePage />)
    await screen.findByText('Core workflow')

    const continueButton = screen.getByRole('button', { name: 'Continue to PRD' })
    expect(continueButton).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Freeze Baseline' }))
    await waitFor(() => {
      expect(freezeScope).toHaveBeenCalledWith('idea-1', { version: 7 })
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Continue to PRD' })).toBeEnabled()
    })

    await userEvent.click(screen.getByRole('button', { name: 'Continue to PRD' }))
    await waitFor(() => {
      expect(loadIdeaDetailMock).toHaveBeenCalled()
      expect(nextNavigationMock.router.push).toHaveBeenCalledWith(
        '/ideas/idea-1/prd?baseline_id=baseline-1'
      )
    })
  })
})
