'use client'

import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { GuardPanel } from '../common/GuardPanel'
import { PlanCards } from './PlanCards'
import { getIdea, postIdeaScopedAgent } from '../../lib/api'
import { buildConfirmedPathContext, getLatestPath } from '../../lib/dag-api'
import { canRunFeasibility } from '../../lib/guards'
import { useIdeasStore } from '../../lib/ideas-store'
import { isSseEventError, streamPost } from '../../lib/sse'
import {
  agentEnvelopeSchema,
  feasibilityOutputSchema,
  type ConfirmedPathContext,
  type FeasibilityInput,
  type FeasibilityOutput,
  type FeasibilityPlan,
} from '../../lib/schemas'
import { useDecisionStore } from '../../lib/store'

const isAbortError = (error: unknown): boolean => {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function FeasibilityPage() {
  const context = useDecisionStore((state) => state.context)
  const setFeasibility = useDecisionStore((state) => state.feasibility)
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const activeIdea = useIdeasStore(
    (state) => state.ideas.find((idea) => idea.id === state.activeIdeaId) ?? null
  )
  const setIdeaVersion = useIdeasStore((state) => state.setIdeaVersion)
  const [plans, setPlans] = useState<FeasibilityPlan[]>(context.feasibility?.plans ?? [])
  const [loading, setLoading] = useState(false)
  const [progressPct, setProgressPct] = useState<number>(0)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [confirmedPathContext, setConfirmedPathContext] = useState<ConfirmedPathContext | null>(
    null
  )
  const abortRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(false)
  const canOpen = canRunFeasibility(context)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      abortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (context.feasibility?.plans) {
      setPlans(context.feasibility.plans)
    }
  }, [context.feasibility])

  useEffect(() => {
    if (!canOpen || !activeIdeaId) {
      setConfirmedPathContext(null)
      return
    }

    let cancelled = false

    const run = async () => {
      try {
        // Fetch fresh idea version and DAG path in parallel.
        // confirm-path and its background summary task each bump the version, so the
        // store is stale by the time the user arrives here from IdeaCanvas.
        const [latestPath, freshIdea] = await Promise.all([
          getLatestPath(activeIdeaId),
          getIdea(activeIdeaId).catch(() => null),
        ])
        if (freshIdea && !cancelled) {
          setIdeaVersion(activeIdeaId, freshIdea.version)
        }
        if (!latestPath) {
          throw new Error('No confirmed DAG path found. Please confirm a path in Idea Canvas.')
        }

        const next = buildConfirmedPathContext(latestPath)
        if (!next) {
          throw new Error('Confirmed path payload is invalid. Re-confirm the DAG path.')
        }

        if (!cancelled && mountedRef.current) {
          setConfirmedPathContext(next)
        }
      } catch (error) {
        if (!cancelled && mountedRef.current) {
          const message =
            error instanceof Error ? error.message : 'Failed to load confirmed DAG path.'
          setErrorMessage(message)
          setConfirmedPathContext(null)
        }
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [activeIdeaId, canOpen, context.confirmed_dag_path_id, setIdeaVersion])

  const handleGenerate = async () => {
    if (!canOpen || !confirmedPathContext) {
      setErrorMessage('Confirm one DAG path in Idea Canvas before generating Feasibility.')
      return
    }
    if (!activeIdeaId || !activeIdea) {
      setErrorMessage('Missing active idea context')
      return
    }
    if (loading) {
      return
    }

    const resolvedIdeaSeed =
      context.idea_seed?.trim() ||
      activeIdea.idea_seed?.trim() ||
      activeIdea.title?.trim() ||
      confirmedPathContext.confirmed_node_content.trim()
    if (!resolvedIdeaSeed) {
      setErrorMessage('Missing idea seed context')
      return
    }

    const payload: FeasibilityInput = {
      idea_seed: resolvedIdeaSeed,
      ...confirmedPathContext,
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setErrorMessage(null)
    setPlans([])
    setProgressPct(0)
    setLoading(true)

    let streamedDonePayload: unknown = null

    try {
      let shouldFallback = false

      try {
        await streamPost(
          `/ideas/${activeIdeaId}/agents/feasibility/stream`,
          { ...payload, version: activeIdea.version },
          {
            onProgress: (data) => {
              if (
                mountedRef.current &&
                typeof data === 'object' &&
                data !== null &&
                'pct' in data
              ) {
                const pct = Number((data as { pct: number }).pct)
                setProgressPct(Number.isFinite(pct) ? pct : 0)
              }
            },
            onPartial: (data) => {
              if (
                !mountedRef.current ||
                typeof data !== 'object' ||
                data === null ||
                !('plan' in data)
              ) {
                return
              }

              const parsed = feasibilityOutputSchema.shape.plans.element.safeParse(
                (data as { plan: unknown }).plan
              )
              if (!parsed.success) {
                return
              }

              setPlans((prev) => {
                if (prev.some((item) => item.id === parsed.data.id)) {
                  return prev
                }
                return [...prev, parsed.data]
              })
            },
            onDone: (data) => {
              streamedDonePayload = data
            },
          },
          controller.signal
        )

        const envelope = agentEnvelopeSchema.safeParse(streamedDonePayload)
        if (!envelope.success) {
          throw new Error('SSE ended without done payload.')
        }

        const parsedData = feasibilityOutputSchema.safeParse(envelope.data.data)
        if (!parsedData.success) {
          throw new Error('Feasibility payload shape mismatch.')
        }

        const streamedOutput: FeasibilityOutput = parsedData.data
        setIdeaVersion(activeIdeaId, envelope.data.idea_version)

        if (mountedRef.current) {
          setPlans(streamedOutput.plans)
        }
        setFeasibility(streamedOutput)
      } catch (streamError) {
        if (isAbortError(streamError)) {
          return
        }
        if (isSseEventError(streamError)) {
          throw streamError
        }
        shouldFallback = true
      }

      if (shouldFallback) {
        toast.message('SSE unavailable, fallback to JSON')
        const envelope = await postIdeaScopedAgent<
          FeasibilityInput & { version: number },
          FeasibilityOutput
        >(activeIdeaId, 'feasibility', {
          ...payload,
          version: activeIdea.version,
        })
        setIdeaVersion(activeIdeaId, envelope.idea_version)
        const parsed = feasibilityOutputSchema.safeParse(envelope.data)

        if (!parsed.success) {
          throw new Error('Feasibility payload shape mismatch.')
        }

        if (mountedRef.current) {
          setPlans(parsed.data.plans)
        }
        setFeasibility(parsed.data)
      }
    } catch (error) {
      if (!isAbortError(error) && mountedRef.current) {
        const message = error instanceof Error ? error.message : 'Request failed. Please try again.'
        setErrorMessage(message)
        toast.error(message)
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
      if (mountedRef.current) {
        setLoading(false)
      }
    }
  }

  if (!canOpen) {
    return (
      <main className="p-6">
        <GuardPanel
          title="Missing context for Feasibility"
          description="Confirm one DAG path in Idea Canvas before entering Feasibility."
        />
      </main>
    )
  }

  const showSkeletons = loading && plans.length < 3
  const showEmptyState = !loading && plans.length === 0

  return (
    <main className="mx-auto w-full max-w-6xl p-6">
      <h1 className="text-2xl font-bold">Feasibility</h1>
      <p className="mt-2 text-sm text-black/70">
        Confirmed Node:{' '}
        {confirmedPathContext?.confirmed_node_content ??
          context.confirmed_dag_node_content ??
          'Loading...'}
      </p>
      <div className="mt-3">
        <button
          type="button"
          onClick={() => {
            void handleGenerate()
          }}
          disabled={loading || !confirmedPathContext}
          className="rounded-md border border-black px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Generating...' : plans.length ? 'Regenerate Plans' : 'Generate Plans'}
        </button>
      </div>
      {loading ? (
        <p className="mt-2 text-xs text-black/60">
          {plans.length > 0 ? `${plans.length}/3 plans ready · ` : ''}Streaming {progressPct}%
        </p>
      ) : null}
      {errorMessage ? <p className="mt-2 text-xs text-red-600">{errorMessage}</p> : null}
      {showEmptyState ? (
        <section className="mt-4 rounded-xl border border-dashed border-black/30 p-6 text-sm text-black/60">
          Click &quot;Generate Plans&quot; to start.
        </section>
      ) : (
        <div className="mt-4">
          <PlanCards
            plans={plans}
            selectedPlanId={context.selected_plan_id}
            loadingSlots={showSkeletons ? 3 : 0}
          />
        </div>
      )}
    </main>
  )
}
