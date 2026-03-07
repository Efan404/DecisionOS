'use client'

import { useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'

import { type ProgressStep, GenerationProgress } from '../common/GenerationProgress'
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

function buildFeasibilityProgressSteps(
  currentStep: string | null,
  steps: { key: string; label: string }[]
): ProgressStep[] {
  // plan_1/2/3 are sequential — map all three to a single "waiting" bucket while < plan_3
  const normalizedStep =
    currentStep === 'plan_1' || currentStep === 'plan_2' ? 'waiting' : currentStep
  const currentIndex = steps.findIndex((s) => s.key === normalizedStep)
  return steps.map((s, i) => ({
    key: s.key,
    label: s.label,
    status:
      currentStep === null
        ? 'pending'
        : i < currentIndex
          ? 'done'
          : i === currentIndex
            ? 'active'
            : 'pending',
  }))
}

export function FeasibilityPage() {
  const t = useTranslations('feasibility')
  const tCommon = useTranslations('common')

  const FEASIBILITY_STEPS: { key: string; label: string }[] = [
    { key: 'received_request', label: 'Received request' },
    { key: 'waiting', label: 'Generating 3 plans in parallel' },
    { key: 'plan_1', label: t('steps.plan_1') },
    { key: 'plan_2', label: t('steps.plan_2') },
    { key: 'plan_3', label: t('steps.plan_3') },
    { key: 'saving', label: 'Saving results' },
  ]

  const context = useDecisionStore((state) => state.context)
  const setFeasibility = useDecisionStore((state) => state.feasibility)
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const activeIdea = useIdeasStore(
    (state) => state.ideas.find((idea) => idea.id === state.activeIdeaId) ?? null
  )
  const setIdeaVersion = useIdeasStore((state) => state.setIdeaVersion)
  const [plans, setPlans] = useState<FeasibilityPlan[]>(context.feasibility?.plans ?? [])
  const [loading, setLoading] = useState(false)
  const [progressStep, setProgressStep] = useState<string | null>(null)
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
          throw new Error(t('errorNoPath'))
        }

        const next = buildConfirmedPathContext(latestPath)
        if (!next) {
          throw new Error(t('errorInvalidPath'))
        }

        if (!cancelled && mountedRef.current) {
          setConfirmedPathContext(next)
        }
      } catch (error) {
        if (!cancelled && mountedRef.current) {
          const message = error instanceof Error ? error.message : t('errorLoadPath')
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
      setErrorMessage(t('errorNoDagPath'))
      return
    }
    if (!activeIdeaId || !activeIdea) {
      setErrorMessage(t('errorMissingIdea'))
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
      setErrorMessage(t('errorMissingIdeaSeed'))
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
    setProgressStep(null)
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
                'step' in data
              ) {
                setProgressStep((data as { step: string }).step)
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
        <GuardPanel title={t('guardTitle')} description={t('guardDesc')} />
      </main>
    )
  }

  const showSkeletons = loading && plans.length < 3
  const showEmptyState = !loading && plans.length === 0

  return (
    <main className="mx-auto w-full max-w-6xl p-6">
      {/* Page header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#1e1e1e]">{t('title')}</h1>
          <p className="mt-0.5 text-sm text-[#1e1e1e]/50">{t('subtitle')}</p>
        </div>
        <button
          id="onboarding-confirm-plan-btn"
          type="button"
          onClick={() => {
            void handleGenerate()
          }}
          disabled={loading || !confirmedPathContext}
          className="shrink-0 rounded-xl bg-[#1e1e1e] px-4 py-2 text-sm font-bold text-[#b9eb10] transition hover:bg-[#333] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading
            ? tCommon('generating')
            : plans.length
              ? t('regeneratePlans')
              : t('generatePlans')}
        </button>
      </div>

      {/* Context card */}
      <div className="mt-4 rounded-xl border border-[#1e1e1e]/8 bg-[#f5f5f5] px-4 py-3">
        <p className="text-xs font-medium tracking-wide text-[#1e1e1e]/40 uppercase">
          {t('confirmedNode')}
        </p>
        <p className="mt-1 text-sm text-[#1e1e1e]/80">
          {confirmedPathContext?.confirmed_node_content ??
            context.confirmed_dag_node_content ??
            t('loadingNode')}
        </p>
      </div>

      {/* Generation progress */}
      {loading ? (
        <div className="mt-4">
          <GenerationProgress
            steps={buildFeasibilityProgressSteps(progressStep, FEASIBILITY_STEPS)}
            isActive={loading}
          />
        </div>
      ) : null}

      {errorMessage ? (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-700">{errorMessage}</p>
        </div>
      ) : null}
      {showEmptyState ? (
        <section className="mt-4 flex flex-col items-center justify-center rounded-xl border border-dashed border-[#1e1e1e]/15 p-10 text-center">
          <p className="text-sm text-[#1e1e1e]/40">{t('clickToGenerate')}</p>
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
