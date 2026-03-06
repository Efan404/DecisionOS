'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { GuardPanel } from '../common/GuardPanel'
import { ScopeBoard } from './ScopeBoard'
import {
  ApiError,
  bootstrapScopeDraft,
  createScopeNewVersion,
  freezeScope,
  getScopeBaseline,
  getScopeDraft,
  patchScopeDraft,
  postIdeaScopedAgent,
} from '../../lib/api'
import { canOpenScope } from '../../lib/guards'
import { buildIdeaStepHref, resolveIdeaIdForRouting } from '../../lib/idea-routes'
import { useIdeasStore } from '../../lib/ideas-store'
import {
  type DecisionContext,
  type ScopeInput,
  type ScopeBaselineItem,
  type ScopeDraftItemInput,
  type ScopeDraftResponse,
  type ScopeOutput,
} from '../../lib/schemas'
import { useDecisionStore } from '../../lib/store'

const normalizeDisplayOrder = (items: ScopeBaselineItem[]): ScopeBaselineItem[] => {
  const grouped: Record<'in' | 'out', ScopeBaselineItem[]> = {
    in: [],
    out: [],
  }
  for (const item of items) {
    grouped[item.lane].push(item)
  }

  return (Object.keys(grouped) as Array<'in' | 'out'>).flatMap((lane) =>
    [...grouped[lane]]
      .sort((left, right) => left.display_order - right.display_order)
      .map((item, index) => ({
        ...item,
        display_order: index,
      }))
  )
}

const isNotFoundError = (error: unknown): boolean => {
  if (error instanceof ApiError) {
    return error.status === 404
  }
  return typeof error === 'object' && error !== null && 'status' in error && error.status === 404
}

const toDraftUpdateItems = (items: ScopeBaselineItem[]): ScopeDraftItemInput[] => {
  return items.map((item) => ({
    lane: item.lane,
    content: item.content,
    display_order: item.display_order,
  }))
}

const scopeHasContent = (scope: ScopeOutput | undefined): scope is ScopeOutput => {
  return Boolean(scope && (scope.in_scope.length > 0 || scope.out_scope.length > 0))
}

const toDraftItemsFromScopeOutput = (scope: ScopeOutput): ScopeDraftItemInput[] => {
  const inScopeItems = scope.in_scope.map((item, index) => ({
    lane: 'in' as const,
    content: item.title,
    display_order: index,
  }))
  const outScopeItems = scope.out_scope.map((item, index) => ({
    lane: 'out' as const,
    content: item.title,
    display_order: index,
  }))
  return [...inScopeItems, ...outScopeItems]
}

const toScopeGenerationPayload = (
  context: DecisionContext,
  version: number
): (ScopeInput & { version: number }) | null => {
  if (
    !context.idea_seed ||
    !context.confirmed_dag_path_id ||
    !context.confirmed_dag_node_id ||
    !context.confirmed_dag_node_content ||
    !context.selected_plan_id ||
    !context.feasibility
  ) {
    return null
  }

  return {
    version,
    idea_seed: context.idea_seed,
    confirmed_path_id: context.confirmed_dag_path_id,
    confirmed_node_id: context.confirmed_dag_node_id,
    confirmed_node_content: context.confirmed_dag_node_content,
    confirmed_path_summary: context.confirmed_dag_path_summary,
    selected_plan_id: context.selected_plan_id,
    feasibility: context.feasibility,
  }
}

export function ScopeFreezePage() {
  const router = useRouter()
  const pathname = usePathname()
  const context = useDecisionStore((state) => state.context)
  const replaceContext = useDecisionStore((state) => state.replaceContext)
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const ideas = useIdeasStore((state) => state.ideas)
  const setIdeaVersion = useIdeasStore((state) => state.setIdeaVersion)
  const loadIdeaDetail = useIdeasStore((state) => state.loadIdeaDetail)
  const [draft, setDraft] = useState<ScopeDraftResponse | null>(null)
  const [ideaVersion, setLocalIdeaVersion] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [loadedIdeaId, setLoadedIdeaId] = useState<string | null>(null)
  const canOpen = canOpenScope(context)
  const routeIdeaId = resolveIdeaIdForRouting(pathname, activeIdeaId)
  const activeIdea = useMemo(
    () => ideas.find((idea) => idea.id === (routeIdeaId ?? activeIdeaId)) ?? null,
    [activeIdeaId, ideas, routeIdeaId]
  )
  const readonly = Boolean(draft?.readonly)
  const canEnterPrd = Boolean(draft?.baseline.id && draft?.baseline.status === 'frozen')

  const syncContextFromServer = useCallback(
    async (fallbackVersion: number): Promise<{ version: number; synced: boolean }> => {
      if (!routeIdeaId) {
        return { version: fallbackVersion, synced: false }
      }
      const detail = await loadIdeaDetail(routeIdeaId)
      if (!detail) {
        return { version: fallbackVersion, synced: false }
      }
      replaceContext(detail.context)
      setIdeaVersion(routeIdeaId, detail.version)
      setLocalIdeaVersion(detail.version)
      return { version: detail.version, synced: true }
    },
    [loadIdeaDetail, replaceContext, routeIdeaId, setIdeaVersion]
  )

  const hydrateDraftIfEmpty = useCallback(
    async (
      ideaId: string,
      currentDraft: ScopeDraftResponse,
      startVersion: number
    ): Promise<{ draft: ScopeDraftResponse; version: number; versionChanged: boolean }> => {
      if (currentDraft.readonly || currentDraft.items.length > 0) {
        return { draft: currentDraft, version: startVersion, versionChanged: false }
      }

      let workingVersion = startVersion
      let sourceScope = scopeHasContent(context.scope) ? context.scope : undefined
      let versionChanged = false

      if (!sourceScope) {
        const payload = toScopeGenerationPayload(context, workingVersion)
        if (!payload) {
          return { draft: currentDraft, version: workingVersion, versionChanged }
        }

        try {
          const envelope = await postIdeaScopedAgent<ScopeInput & { version: number }, ScopeOutput>(
            ideaId,
            'scope',
            payload
          )
          sourceScope = envelope.data
          workingVersion = envelope.idea_version
          versionChanged = true
        } catch (error) {
          if (error instanceof ApiError && error.status === 409) {
            const synced = await syncContextFromServer(workingVersion)
            return {
              draft: currentDraft,
              version: synced.version,
              versionChanged: synced.version !== startVersion,
            }
          }
          throw error
        }
      }

      if (!sourceScope || !scopeHasContent(sourceScope)) {
        return { draft: currentDraft, version: workingVersion, versionChanged }
      }

      try {
        const envelope = await patchScopeDraft(ideaId, {
          version: workingVersion,
          items: toDraftItemsFromScopeOutput(sourceScope),
        })
        return {
          draft: envelope.data,
          version: envelope.idea_version,
          versionChanged: true,
        }
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          const synced = await syncContextFromServer(workingVersion)
          return {
            draft: currentDraft,
            version: synced.version,
            versionChanged: synced.version !== startVersion,
          }
        }
        throw error
      }
    },
    [context, syncContextFromServer]
  )

  useEffect(() => {
    if (!activeIdea) {
      setLocalIdeaVersion(null)
      return
    }
    setLocalIdeaVersion(activeIdea.version)
  }, [activeIdea])

  useEffect(() => {
    setLoadedIdeaId(null)
    setDraft(null)
    setErrorMessage(null)
    setLoading(true)
  }, [routeIdeaId])

  useEffect(() => {
    if (!canOpen || !routeIdeaId || !activeIdea) {
      setLoading(false)
      return
    }
    if (loadedIdeaId === routeIdeaId) {
      return
    }

    let cancelled = false
    const run = async () => {
      let loadedDraft: ScopeDraftResponse | null = null
      let workingVersion = activeIdea.version
      let versionChanged = false

      try {
        try {
          setLoading(true)
          setErrorMessage(null)
          loadedDraft = await getScopeDraft(routeIdeaId)
        } catch (error) {
          if (!isNotFoundError(error)) {
            if (!cancelled) {
              const message = error instanceof Error ? error.message : 'Failed to load scope draft.'
              setErrorMessage(message)
              toast.error(message)
            }
            return
          }

          // 404: no draft exists.
          // If scope is already frozen, show frozen baseline read-only instead of auto-bootstrapping.
          if (context.scope_frozen && context.current_scope_baseline_id && routeIdeaId) {
            try {
              const baseline = await getScopeBaseline(
                routeIdeaId,
                context.current_scope_baseline_id
              )
              if (!cancelled) {
                setDraft({
                  baseline: baseline.baseline,
                  items: baseline.items,
                  readonly: true,
                })
                setLoadedIdeaId(routeIdeaId)
                setLocalIdeaVersion(workingVersion)
              }
            } catch (baselineError) {
              if (!cancelled) {
                const message =
                  baselineError instanceof Error
                    ? baselineError.message
                    : 'Failed to load frozen baseline.'
                setErrorMessage(message)
                toast.error(message)
              }
            } finally {
              if (!cancelled) setLoading(false)
            }
            return
          }

          try {
            const envelope = await bootstrapScopeDraft(routeIdeaId, {
              version: activeIdea.version,
            })
            loadedDraft = envelope.data
            workingVersion = envelope.idea_version
            versionChanged = true
          } catch (bootstrapError) {
            if (bootstrapError instanceof ApiError && bootstrapError.status === 409) {
              try {
                loadedDraft = await getScopeDraft(routeIdeaId)
                const synced = await syncContextFromServer(workingVersion)
                workingVersion = synced.version
                versionChanged = versionChanged || synced.synced
              } catch (recoverError) {
                if (!cancelled) {
                  const message =
                    recoverError instanceof Error
                      ? recoverError.message
                      : 'Failed to recover scope draft after version conflict.'
                  setErrorMessage(message)
                  toast.error(message)
                }
                return
              }
            } else {
              if (!cancelled) {
                const message =
                  bootstrapError instanceof Error
                    ? bootstrapError.message
                    : 'Failed to bootstrap scope draft.'
                setErrorMessage(message)
                toast.error(message)
              }
              return
            }
          }
        }

        if (!loadedDraft) {
          return
        }

        try {
          const hydrated = await hydrateDraftIfEmpty(routeIdeaId, loadedDraft, workingVersion)
          loadedDraft = hydrated.draft
          workingVersion = hydrated.version
          versionChanged = versionChanged || hydrated.versionChanged
        } catch (hydrateError) {
          if (!cancelled) {
            const message =
              hydrateError instanceof Error
                ? hydrateError.message
                : 'Failed to initialize scope draft.'
            setErrorMessage(message)
            toast.error(message)
          }
        }

        if (!cancelled) {
          if (versionChanged) {
            setIdeaVersion(routeIdeaId, workingVersion)
          }
          setLocalIdeaVersion(workingVersion)
          setDraft(loadedDraft)
          setLoadedIdeaId(routeIdeaId)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [
    activeIdea,
    canOpen,
    context.scope_frozen,
    context.current_scope_baseline_id,
    hydrateDraftIfEmpty,
    loadedIdeaId,
    routeIdeaId,
    setIdeaVersion,
  ])

  const applyDraftItems = async (nextItems: ScopeBaselineItem[]) => {
    if (!routeIdeaId || !draft || draft.readonly) {
      return
    }
    const currentVersion = ideaVersion ?? activeIdea?.version
    if (!currentVersion) {
      setErrorMessage('Missing idea version for scope update.')
      return
    }

    setSaving(true)
    try {
      const envelope = await patchScopeDraft(routeIdeaId, {
        version: currentVersion,
        items: toDraftUpdateItems(normalizeDisplayOrder(nextItems)),
      })
      setDraft(envelope.data)
      setIdeaVersion(routeIdeaId, envelope.idea_version)
      setLocalIdeaVersion(envelope.idea_version)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update scope draft.'
      setErrorMessage(message)
      toast.error(message)
      if (error instanceof ApiError && error.status === 409) {
        await syncContextFromServer(currentVersion)
      }
    } finally {
      setSaving(false)
    }
  }

  const handleAddItem = async (lane: 'in' | 'out', content: string) => {
    if (!draft || draft.readonly) {
      return
    }
    const laneItems = draft.items
      .filter((item) => item.lane === lane)
      .sort((left, right) => left.display_order - right.display_order)
    const nextItems = normalizeDisplayOrder([
      ...draft.items,
      {
        id: `tmp-${Date.now()}`,
        baseline_id: draft.baseline.id,
        lane,
        content,
        display_order: laneItems.length,
        created_at: new Date().toISOString(),
      },
    ])
    await applyDraftItems(nextItems)
  }

  const handleDeleteItem = async (itemId: string) => {
    if (!draft || draft.readonly) {
      return
    }
    const nextItems = normalizeDisplayOrder(draft.items.filter((item) => item.id !== itemId))
    await applyDraftItems(nextItems)
  }

  const handleMoveItem = async (itemId: string, direction: 'up' | 'down') => {
    if (!draft || draft.readonly) {
      return
    }
    const movingItem = draft.items.find((item) => item.id === itemId)
    if (!movingItem) {
      return
    }

    const laneItems = draft.items
      .filter((item) => item.lane === movingItem.lane)
      .sort((left, right) => left.display_order - right.display_order)
    const oldIndex = laneItems.findIndex((item) => item.id === itemId)
    if (oldIndex < 0) {
      return
    }
    const targetIndex = direction === 'up' ? oldIndex - 1 : oldIndex + 1
    if (targetIndex < 0 || targetIndex >= laneItems.length) {
      return
    }

    const reorderedLane = [...laneItems]
    const [current] = reorderedLane.splice(oldIndex, 1)
    reorderedLane.splice(targetIndex, 0, current)
    const untouched = draft.items.filter((item) => item.lane !== movingItem.lane)
    const nextItems = normalizeDisplayOrder([...untouched, ...reorderedLane])
    await applyDraftItems(nextItems)
  }

  const handleFreeze = async () => {
    if (!routeIdeaId || !draft || draft.readonly) {
      return
    }
    const currentVersion = ideaVersion ?? activeIdea?.version
    if (!currentVersion) {
      setErrorMessage('Missing idea version for freeze.')
      return
    }

    setSaving(true)
    try {
      let versionToUse = currentVersion
      let envelope
      try {
        envelope = await freezeScope(routeIdeaId, { version: versionToUse })
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          // Version drifted (e.g. concurrent scope/agents call) — re-sync and retry once
          const synced = await syncContextFromServer(versionToUse)
          versionToUse = synced.version
          envelope = await freezeScope(routeIdeaId, { version: versionToUse })
        } else {
          throw error
        }
      }
      setDraft(envelope.data)
      setIdeaVersion(routeIdeaId, envelope.idea_version)
      setLocalIdeaVersion(envelope.idea_version)
      await syncContextFromServer(envelope.idea_version)
      toast.success('Baseline frozen')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to freeze baseline.'
      setErrorMessage(message)
      toast.error(message)
    } finally {
      setSaving(false)
    }
  }

  const handleCreateNewVersion = async () => {
    if (!routeIdeaId || !draft) {
      return
    }
    const currentVersion = ideaVersion ?? activeIdea?.version
    if (!currentVersion) {
      setErrorMessage('Missing idea version for new baseline version.')
      return
    }

    setSaving(true)
    try {
      let versionToUse = currentVersion
      let envelope
      try {
        envelope = await createScopeNewVersion(routeIdeaId, { version: versionToUse })
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          const synced = await syncContextFromServer(versionToUse)
          versionToUse = synced.version
          envelope = await createScopeNewVersion(routeIdeaId, { version: versionToUse })
        } else {
          throw error
        }
      }
      setDraft(envelope.data)
      setIdeaVersion(routeIdeaId, envelope.idea_version)
      setLocalIdeaVersion(envelope.idea_version)
      await syncContextFromServer(envelope.idea_version)
      toast.success('New scope baseline version created')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create new version.'
      setErrorMessage(message)
      toast.error(message)
    } finally {
      setSaving(false)
    }
  }

  const handleContinueToPrd = async () => {
    if (!routeIdeaId || !draft?.baseline.id || draft.baseline.status !== 'frozen') {
      return
    }
    const currentVersion = ideaVersion ?? activeIdea?.version
    if (!currentVersion) {
      setErrorMessage('Missing idea version for PRD navigation.')
      return
    }

    setSaving(true)
    try {
      const synced = await syncContextFromServer(currentVersion)
      if (!synced.synced) {
        const message = 'Failed to sync latest scope context before opening PRD.'
        setErrorMessage(message)
        toast.error(message)
        return
      }
      router.push(buildIdeaStepHref(routeIdeaId, 'prd', { baseline_id: draft.baseline.id }))
    } finally {
      setSaving(false)
    }
  }

  if (!canOpen) {
    return (
      <main className="p-6">
        <GuardPanel
          title="Missing context for Scope Freeze"
          description="Confirm one feasibility plan before entering Scope Freeze."
        />
      </main>
    )
  }

  return (
    <main>
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-6 pt-6">
        <h1 className="text-2xl font-bold">Scope Freeze</h1>
        <p className="text-sm text-black/70">
          Edit draft items in each lane, freeze a baseline snapshot, then continue to PRD.
        </p>
        {draft ? (
          <p className="text-xs text-black/60">
            Baseline v{draft.baseline.version} ({draft.baseline.status})
          </p>
        ) : null}
        <div className="flex gap-2">
          {readonly ? (
            <button
              type="button"
              onClick={handleCreateNewVersion}
              disabled={saving}
              className="rounded-md border border-black px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              Create New Version
            </button>
          ) : (
            <button
              type="button"
              onClick={handleFreeze}
              disabled={saving || loading || !draft}
              className="rounded-md border border-black px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              Freeze Baseline
            </button>
          )}
          <button
            type="button"
            onClick={handleContinueToPrd}
            disabled={!canEnterPrd || saving}
            className="rounded-md border border-[#b9eb10] bg-[#b9eb10] px-3 py-2 text-sm font-medium text-[#1e1e1e] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Continue to PRD
          </button>
          {loading ? <span className="text-xs text-black/60">Loading scope draft...</span> : null}
          {saving ? <span className="text-xs text-black/60">Saving...</span> : null}
          {errorMessage ? <span className="text-xs text-red-600">{errorMessage}</span> : null}
        </div>
      </section>

      {draft ? (
        <ScopeBoard
          items={draft.items}
          readonly={readonly || saving}
          onAddItem={handleAddItem}
          onDeleteItem={handleDeleteItem}
          onMoveItem={handleMoveItem}
          onReorderItems={applyDraftItems}
        />
      ) : null}
    </main>
  )
}
