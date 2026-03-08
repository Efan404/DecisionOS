import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { IdeaScopedHydration } from '../IdeaScopedHydration'
import { useIdeasStore } from '../../../lib/ideas-store'
import { useDecisionStore } from '../../../lib/store'

describe('IdeaScopedHydration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useIdeasStore.setState({
      ideas: [],
      activeIdeaId: null,
      loading: false,
      error: null,
    })
    useDecisionStore.setState({
      context: {
        session_id: 'session-test',
        created_at: '2026-03-08T00:00:00.000Z',
      },
    })
  })

  test('returns to syncing state when ideaId changes until the new detail loads', async () => {
    let resolveFirst: ((value: unknown) => void) | null = null
    let resolveSecond: ((value: unknown) => void) | null = null

    const loadIdeaDetail = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve
          })
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSecond = resolve
          })
      )

    useIdeasStore.setState({
      loadIdeaDetail,
    })

    const view = render(
      <IdeaScopedHydration ideaId="idea-1">
        <div>hydrated child</div>
      </IdeaScopedHydration>
    )

    expect(screen.getByText('Syncing idea context...')).toBeInTheDocument()

    resolveFirst?.({
      id: 'idea-1',
      workspace_id: 'default',
      title: 'Idea 1',
      stage: 'idea_canvas',
      status: 'draft',
      version: 1,
      created_at: '2026-03-08T00:00:00.000Z',
      updated_at: '2026-03-08T00:00:00.000Z',
      context: {
        session_id: 'session-1',
        created_at: '2026-03-08T00:00:00.000Z',
        idea_seed: 'first idea',
      },
    })

    expect(await screen.findByText('hydrated child')).toBeInTheDocument()

    view.rerender(
      <IdeaScopedHydration ideaId="idea-2">
        <div>hydrated child</div>
      </IdeaScopedHydration>
    )

    expect(screen.getByText('Syncing idea context...')).toBeInTheDocument()

    resolveSecond?.({
      id: 'idea-2',
      workspace_id: 'default',
      title: 'Idea 2',
      stage: 'idea_canvas',
      status: 'draft',
      version: 1,
      created_at: '2026-03-08T00:00:00.000Z',
      updated_at: '2026-03-08T00:00:00.000Z',
      context: {
        session_id: 'session-2',
        created_at: '2026-03-08T00:00:00.000Z',
        idea_seed: 'second idea',
      },
    })

    expect(await screen.findByText('hydrated child')).toBeInTheDocument()
    expect(useDecisionStore.getState().context.idea_seed).toBe('second idea')
  })

  test('shows a recoverable error state when the idea detail cannot be loaded', async () => {
    const loadIdeaDetail = vi.fn().mockResolvedValue(null)

    useIdeasStore.setState({
      loadIdeaDetail,
    })

    render(
      <IdeaScopedHydration ideaId="missing-idea">
        <div>hydrated child</div>
      </IdeaScopedHydration>
    )

    expect(screen.getByText('Syncing idea context...')).toBeInTheDocument()
    expect(await screen.findByText('Idea not found or unavailable.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to ideas' })).toHaveAttribute('href', '/ideas')
  })
})
