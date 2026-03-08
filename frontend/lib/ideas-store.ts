'use client'

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { createIdea, deleteIdea, getIdea, listIdeas } from './api'
import type { IdeaDetail, IdeaSummary } from './schemas'

type IdeasStoreState = {
  ideas: IdeaSummary[]
  activeIdeaId: string | null
  loading: boolean
  error: string | null
  setActiveIdeaId: (ideaId: string) => void
  setIdeaDetail: (detail: IdeaDetail) => void
  setIdeaVersion: (ideaId: string, version: number) => void
  loadIdeas: () => Promise<void>
  createIdea: (title: string) => Promise<IdeaDetail | null>
  loadIdeaDetail: (ideaId: string) => Promise<IdeaDetail | null>
  deleteIdea: (ideaId: string) => Promise<void>
}

const pickDefaultActiveIdea = (
  ideas: IdeaSummary[],
  currentActiveIdeaId: string | null
): string | null => {
  if (currentActiveIdeaId && ideas.some((idea) => idea.id === currentActiveIdeaId)) {
    return currentActiveIdeaId
  }

  return ideas[0]?.id ?? null
}

export const useIdeasStore = create<IdeasStoreState>()(
  persist(
    (set, get) => ({
      ideas: [],
      activeIdeaId: null,
      loading: false,
      error: null,
      setActiveIdeaId: (ideaId) => {
        set({ activeIdeaId: ideaId })
      },
      setIdeaDetail: (detail) => {
        set((state) => {
          const next = state.ideas.filter((idea) => idea.id !== detail.id)
          return {
            ideas: [detail, ...next],
            activeIdeaId: detail.id,
          }
        })
      },
      setIdeaVersion: (ideaId, version) => {
        set((state) => ({
          ideas: state.ideas.map((idea) =>
            idea.id === ideaId ? { ...idea, version, updated_at: new Date().toISOString() } : idea
          ),
        }))
      },
      loadIdeas: async () => {
        set({ loading: true, error: null })
        try {
          const ideas = await listIdeas()
          set({
            ideas,
            activeIdeaId: pickDefaultActiveIdea(ideas, get().activeIdeaId),
            loading: false,
          })
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to load ideas.'
          set({ loading: false, error: message })
        }
      },
      createIdea: async (title) => {
        set({ loading: true, error: null })
        try {
          const created = await createIdea({ title })
          const nextIdeas = [created, ...get().ideas.filter((idea) => idea.id !== created.id)]
          set({
            ideas: nextIdeas,
            activeIdeaId: created.id,
            loading: false,
          })
          return created
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to create idea.'
          set({ loading: false, error: message })
          return null
        }
      },
      loadIdeaDetail: async (ideaId) => {
        set({ loading: true, error: null })
        try {
          const detail = await getIdea(ideaId)
          get().setIdeaDetail(detail)
          set({ loading: false })
          return detail
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to load idea.'
          set({ loading: false, error: message })
          return null
        }
      },
      deleteIdea: async (ideaId) => {
        set({ loading: true, error: null })
        try {
          await deleteIdea(ideaId)
          set((state) => {
            const nextIdeas = state.ideas.filter((idea) => idea.id !== ideaId)
            const nextActiveIdeaId =
              state.activeIdeaId === ideaId ? (nextIdeas[0]?.id ?? null) : state.activeIdeaId
            return {
              loading: false,
              ideas: nextIdeas,
              activeIdeaId: nextActiveIdeaId,
            }
          })
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to delete idea.'
          set({ loading: false, error: message })
        }
      },
    }),
    {
      name: 'decisionos_ideas_v1',
      partialize: (state) => ({
        activeIdeaId: state.activeIdeaId,
      }),
    }
  )
)
