import { beforeEach, describe, expect, test, vi } from 'vitest'

import { useIdeasStore } from '../ideas-store'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    deleteIdea: vi.fn().mockResolvedValue(undefined),
    createIdea: vi.fn(),
    getIdea: vi.fn(),
    listIdeas: vi.fn(),
  }
})

describe('ideas-store', () => {
  beforeEach(() => {
    useIdeasStore.setState({
      ideas: [],
      activeIdeaId: null,
      loading: false,
      error: null,
    })
  })

  test('falls back to the next available idea when deleting the active idea', async () => {
    useIdeasStore.setState({
      activeIdeaId: 'idea-1',
      ideas: [
        {
          id: 'idea-1',
          workspace_id: 'default',
          title: 'Idea 1',
          stage: 'idea_canvas',
          status: 'draft',
          version: 1,
          created_at: '2026-03-08T00:00:00.000Z',
          updated_at: '2026-03-08T00:00:00.000Z',
        },
        {
          id: 'idea-2',
          workspace_id: 'default',
          title: 'Idea 2',
          stage: 'idea_canvas',
          status: 'draft',
          version: 1,
          created_at: '2026-03-08T00:00:00.000Z',
          updated_at: '2026-03-08T00:00:00.000Z',
        },
      ],
    })

    await useIdeasStore.getState().deleteIdea('idea-1')

    expect(useIdeasStore.getState().ideas.map((idea) => idea.id)).toEqual(['idea-2'])
    expect(useIdeasStore.getState().activeIdeaId).toBe('idea-2')
  })
})
