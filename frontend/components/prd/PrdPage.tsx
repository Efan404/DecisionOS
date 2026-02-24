'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { toast } from 'sonner'

import { GuardPanel } from '../common/GuardPanel'
import { PrdView } from './PrdView'
import { ApiError, postPrdFeedback } from '../../lib/api'
import { streamPost } from '../../lib/sse'
import { canOpenPrd } from '../../lib/guards'
import { useIdeasStore } from '../../lib/ideas-store'
import { type PrdFeedbackDimensions, type PrdOutput } from '../../lib/schemas'
import { useDecisionStore } from '../../lib/store'

type PrdStreamPartials = {
  requirements: PrdOutput['requirements'] | null
  backlog: PrdOutput['backlog'] | null
}

const globalPrdGenerationRequests = new Set<string>()

type PrdPageProps = {
  baselineId?: string | null
}

export function PrdPage({ baselineId: baselineIdProp = null }: PrdPageProps) {
  const searchParams = useSearchParams()
  const context = useDecisionStore((state) => state.context)
  const replaceContext = useDecisionStore((state) => state.replaceContext)
  const canOpen = canOpenPrd(context)
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const activeIdea = useIdeasStore(
    (state) => state.ideas.find((idea) => idea.id === state.activeIdeaId) ?? null
  )
  const setIdeaVersion = useIdeasStore((state) => state.setIdeaVersion)
  const loadIdeaDetail = useIdeasStore((state) => state.loadIdeaDetail)
  const [loading, setLoading] = useState(false)
  const [isRegenerate, setIsRegenerate] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const [retryNonce, setRetryNonce] = useState(0)
  const [streamPartials, setStreamPartials] = useState<PrdStreamPartials>({
    requirements: null,
    backlog: null,
  })
  const inFlightGenerationKeyRef = useRef<string | null>(null)
  // Resolve baseline_id: explicit prop > URL param > current scope baseline from context.
  // This prevents a spurious "Select a frozen baseline" error when navigating via the
  // sidebar (which omits the query param) but a frozen baseline already exists.
  const baselineId =
    baselineIdProp ?? searchParams.get('baseline_id') ?? context.current_scope_baseline_id ?? null

  const generationKey = useMemo(
    () =>
      JSON.stringify({
        baseline_id: baselineId ?? null,
        selected_plan_id: context.selected_plan_id ?? null,
        confirmed_path_id: context.confirmed_dag_path_id ?? null,
      }),
    [baselineId, context.confirmed_dag_path_id, context.selected_plan_id]
  )

  const isFreshBundleRef = useRef(false)
  isFreshBundleRef.current = useMemo(() => {
    const meta = context.prd_bundle?.generation_meta
    if (!meta || !baselineId) {
      return false
    }
    return (
      meta.baseline_id === baselineId &&
      meta.selected_plan_id === context.selected_plan_id &&
      meta.confirmed_path_id === context.confirmed_dag_path_id
    )
  }, [baselineId, context.confirmed_dag_path_id, context.prd_bundle, context.selected_plan_id])

  useEffect(() => {
    if (!canOpen || !activeIdeaId || !activeIdea) {
      return
    }
    if (!baselineId) {
      setErrorMessage('Select a frozen baseline to generate PRD and backlog.')
      return
    }
    const hasLocalOutput = Boolean(context.prd || context.prd_bundle?.output)
    const shouldGenerate =
      retryNonce > 0 || (context.prd_bundle ? !isFreshBundleRef.current : !hasLocalOutput)
    if (!shouldGenerate) {
      return
    }
    const requestKey = `${generationKey}:${retryNonce}`
    if (inFlightGenerationKeyRef.current === requestKey) {
      return
    }
    if (globalPrdGenerationRequests.has(requestKey)) {
      return
    }
    inFlightGenerationKeyRef.current = requestKey
    globalPrdGenerationRequests.add(requestKey)

    let cancelled = false
    setLoading(true)
    setIsRegenerate(hasLocalOutput)
    setErrorMessage(null)

    const run = async () => {
      setStreamPartials({ requirements: null, backlog: null })
      try {
        let donePayload: { idea_id: string; idea_version: number } | null = null
        await streamPost(
          `/ideas/${activeIdeaId}/agents/prd/stream`,
          {
            baseline_id: baselineId,
            version: activeIdea.version,
          },
          {
            onEvent: (event) => {
              if (cancelled) return
              if (event.event === 'requirements') {
                const data = event.data as { requirements: PrdOutput['requirements'] }
                setStreamPartials((prev) => ({ ...prev, requirements: data.requirements }))
              } else if (event.event === 'backlog') {
                const data = event.data as { items: PrdOutput['backlog']['items'] }
                setStreamPartials((prev) => ({ ...prev, backlog: { items: data.items } }))
              } else if (event.event === 'done') {
                donePayload = event.data as { idea_id: string; idea_version: number }
              }
            },
          }
        )
        if (!cancelled && donePayload) {
          const envelope = donePayload
          setIdeaVersion(activeIdeaId, envelope.idea_version)
          // Load and apply context BEFORE turning off loading,
          // so PrdView sees prd_bundle populated when it re-renders.
          const detail = await loadIdeaDetail(activeIdeaId)
          if (!cancelled) {
            if (detail) {
              replaceContext(detail.context)
            }
            setRetryNonce(0)
            setStreamPartials({ requirements: null, backlog: null })
            setLoading(false)
          }
        }
      } catch (error) {
        if (inFlightGenerationKeyRef.current === requestKey) {
          inFlightGenerationKeyRef.current = null
        }
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : 'Request failed. Please try again.'
          setErrorMessage(message)
          toast.error(message)
        }
      } finally {
        if (inFlightGenerationKeyRef.current === requestKey) {
          inFlightGenerationKeyRef.current = null
        }
        globalPrdGenerationRequests.delete(requestKey)
        setLoading(false)
      }
    }

    void run()

    return () => {
      cancelled = true
      if (inFlightGenerationKeyRef.current === requestKey) {
        inFlightGenerationKeyRef.current = null
      }
      // Do NOT delete from globalPrdGenerationRequests here.
      // The set is cleaned up in the finally block of run().
      // Deleting here would allow a second effect (e.g. StrictMode) to bypass the guard.
    }
  }, [
    activeIdea,
    activeIdeaId,
    baselineId,
    canOpen,
    generationKey,
    loadIdeaDetail,
    replaceContext,
    retryNonce,
    setIdeaVersion,
  ])

  const handleRetry = () => {
    setRetryNonce((previous) => previous + 1)
  }

  const handleSubmitFeedback = async (payload: {
    rating_overall: number
    rating_dimensions: PrdFeedbackDimensions
    comment?: string
  }) => {
    if (!activeIdeaId || !activeIdea || !baselineId) {
      return
    }
    setFeedbackSubmitting(true)
    setFeedbackError(null)
    try {
      const response = await postPrdFeedback(activeIdeaId, {
        version: activeIdea.version,
        baseline_id: baselineId,
        rating_overall: payload.rating_overall,
        rating_dimensions: payload.rating_dimensions,
        comment: payload.comment,
      })
      setIdeaVersion(activeIdeaId, response.idea_version)
      const detail = await loadIdeaDetail(activeIdeaId)
      if (detail) {
        replaceContext(detail.context)
      }
      toast.success('Feedback saved')
    } catch (error) {
      const message =
        error instanceof ApiError
          ? `${error.code ?? 'REQUEST_FAILED'}: ${error.message}`
          : error instanceof Error
            ? error.message
            : 'Failed to submit feedback.'
      setFeedbackError(message)
      toast.error(message)
      throw error
    } finally {
      setFeedbackSubmitting(false)
    }
  }

  if (!canOpen) {
    return (
      <main>
        <section className="mx-auto mt-6 w-full max-w-4xl px-6">
          <GuardPanel
            title="PRD context not ready"
            description="Complete Scope Freeze before opening the PRD page."
          />
        </section>
      </main>
    )
  }

  return (
    <main>
      <PrdView
        prd={context.prd_bundle?.output ?? context.prd}
        bundle={context.prd_bundle}
        context={context}
        loading={loading}
        isRegenerate={isRegenerate}
        errorMessage={errorMessage}
        baselineId={baselineId}
        onRetry={handleRetry}
        feedbackLatest={context.prd_feedback_latest}
        onSubmitFeedback={handleSubmitFeedback}
        feedbackSubmitting={feedbackSubmitting}
        feedbackError={feedbackError}
        streamPartials={loading ? streamPartials : null}
      />
    </main>
  )
}
