'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { toast } from 'sonner'

import { AgentThoughtStream, useAgentThoughts } from '../agent/AgentThoughtStream'
import { type ProgressStep } from '../common/GenerationProgress'
import { GuardPanel } from '../common/GuardPanel'
import { PrdView } from './PrdView'
import { ApiError, downloadPrdBacklogExport, postPrdFeedback } from '../../lib/api'
import { streamPost } from '../../lib/sse'
import { canOpenPrd } from '../../lib/guards'
import { useIdeasStore } from '../../lib/ideas-store'
import { type PrdFeedbackDimensions } from '../../lib/schemas'
import { useDecisionStore } from '../../lib/store'

const globalPrdGenerationRequests = new Set<string>()

const PRD_STEPS: { key: string; label: string }[] = [
  { key: 'validating', label: 'Validating idea context' },
  { key: 'building_context', label: 'Building PRD context pack' },
  { key: 'generating', label: 'Generating PRD…' },
  { key: 'requirements_done', label: 'Requirements ready' },
  { key: 'backlog_done', label: 'Backlog ready' },
  { key: 'saving', label: 'Saving to database' },
]

function buildPrdProgressSteps(currentStep: string | null): ProgressStep[] {
  const currentIndex = PRD_STEPS.findIndex((s) => s.key === currentStep)
  return PRD_STEPS.map((s, i) => ({
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

type PrdPageProps = {
  baselineId?: string | null
}

export function PrdPage({ baselineId: baselineIdProp = null }: PrdPageProps) {
  const searchParams = useSearchParams()
  const context = useDecisionStore((state) => state.context)
  const replaceContextRef = useRef(useDecisionStore.getState().replaceContext)
  const canOpen = canOpenPrd(context)
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const activeIdea = useIdeasStore(
    (state) => state.ideas.find((idea) => idea.id === state.activeIdeaId) ?? null
  )
  const setIdeaVersionRef = useRef(useIdeasStore.getState().setIdeaVersion)
  const loadIdeaDetailRef = useRef(useIdeasStore.getState().loadIdeaDetail)
  // Keep refs in sync with store state
  replaceContextRef.current = useDecisionStore((state) => state.replaceContext)
  setIdeaVersionRef.current = useIdeasStore((state) => state.setIdeaVersion)
  loadIdeaDetailRef.current = useIdeasStore((state) => state.loadIdeaDetail)
  const [loading, setLoading] = useState(false)
  const [progressStep, setProgressStep] = useState<string | null>(null)
  const [progressPct, setProgressPct] = useState<number>(0)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false)
  const [retryNonce, setRetryNonce] = useState(0)
  const [exporting, setExporting] = useState(false)
  const inFlightGenerationKeyRef = useRef<string | null>(null)
  const { thoughts, addThought, reset } = useAgentThoughts()
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
    setProgressStep(null)
    setProgressPct(0)
    setErrorMessage(null)
    reset()
    // Clear stale PRD so PrdView shows the loading progress instead of old content
    replaceContextRef.current({
      ...useDecisionStore.getState().context,
      prd: undefined,
      prd_bundle: undefined,
    })

    const run = async () => {
      console.log(
        '[PrdPage] stream start ideaId=%s baselineId=%s version=%s',
        activeIdeaId,
        baselineId,
        activeIdea.version
      )
      try {
        let donePayload: { idea_id: string; idea_version: number } | null = null
        await streamPost(
          `/ideas/${activeIdeaId}/agents/prd/stream`,
          {
            baseline_id: baselineId,
            version: activeIdea.version,
          },
          {
            onEvent: (_event) => {
              // SSE events (requirements, backlog) are incorporated via loadIdeaDetail on done
            },
            onProgress: (data) => {
              if (!cancelled && typeof data === 'object' && data !== null && 'step' in data) {
                const d = data as { step: string; pct?: number }
                setProgressStep(d.step)
                if (typeof d.pct === 'number') setProgressPct(d.pct)
              }
            },
            onDone: (data) => {
              if (!cancelled) {
                donePayload = data as { idea_id: string; idea_version: number }
                console.log('[PrdPage] stream done', donePayload)
              }
            },
            onAgentThought: (data) => {
              if (!cancelled) addThought(data)
            },
          }
        )
        if (!cancelled && donePayload) {
          const envelope = donePayload
          setIdeaVersionRef.current(activeIdeaId, envelope.idea_version)
          // Load and apply context BEFORE turning off loading,
          // so PrdView sees prd_bundle populated when it re-renders.
          const detail = await loadIdeaDetailRef.current(activeIdeaId)
          console.log(
            '[PrdPage] loadIdeaDetail result hasPrdBundle=%s',
            Boolean(detail?.context?.prd_bundle)
          )
          if (!cancelled) {
            if (detail) {
              replaceContextRef.current(detail.context)
            }
            setRetryNonce(0)
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
          console.error('[PrdPage] stream error', error)
          setErrorMessage(message)
          toast.error(message)
        }
      } finally {
        if (inFlightGenerationKeyRef.current === requestKey) {
          inFlightGenerationKeyRef.current = null
        }
        globalPrdGenerationRequests.delete(requestKey)
        setLoading(false)
        setProgressStep(null)
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
  }, [activeIdea, activeIdeaId, baselineId, canOpen, generationKey, retryNonce])

  const handleRetry = () => {
    setRetryNonce((previous) => previous + 1)
  }

  const handleSubmitFeedback = async (payload: {
    rating_overall: number
    rating_dimensions: PrdFeedbackDimensions
  }) => {
    if (!activeIdeaId || !activeIdea || !baselineId) {
      return
    }
    setFeedbackSubmitting(true)
    try {
      const response = await postPrdFeedback(activeIdeaId, {
        version: activeIdea.version,
        baseline_id: baselineId,
        rating_overall: payload.rating_overall,
        rating_dimensions: payload.rating_dimensions,
      })
      setIdeaVersionRef.current(activeIdeaId, response.idea_version)
      const detail = await loadIdeaDetailRef.current(activeIdeaId)
      if (detail) {
        replaceContextRef.current(detail.context)
      }
    } catch (error) {
      const message =
        error instanceof ApiError
          ? `${error.code ?? 'REQUEST_FAILED'}: ${error.message}`
          : error instanceof Error
            ? error.message
            : 'Failed to submit feedback.'
      toast.error(message)
      throw error
    } finally {
      setFeedbackSubmitting(false)
    }
  }

  const handleExport = async (format: 'json' | 'csv') => {
    if (!activeIdeaId) {
      return
    }
    setExporting(true)
    try {
      await downloadPrdBacklogExport(activeIdeaId, format)
      toast.success(`Backlog exported as ${format.toUpperCase()}`)
    } catch (error) {
      const message =
        error instanceof ApiError
          ? `${error.code ?? 'EXPORT_FAILED'}: ${error.message}`
          : error instanceof Error
            ? error.message
            : 'Export failed. Please try again.'
      toast.error(message)
    } finally {
      setExporting(false)
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
      {thoughts.length > 0 && (
        <div className="mx-auto w-full max-w-7xl px-6 pt-3">
          <AgentThoughtStream thoughts={thoughts} isActive={loading} />
        </div>
      )}
      <PrdView
        prd={context.prd_bundle?.output ?? context.prd}
        bundle={context.prd_bundle}
        progressSteps={loading ? buildPrdProgressSteps(progressStep) : undefined}
        progressPct={loading ? progressPct : undefined}
        context={context}
        loading={loading}
        errorMessage={errorMessage}
        baselineId={baselineId}
        onRetry={handleRetry}
        feedbackLatest={context.prd_feedback_latest}
        onSubmitFeedback={handleSubmitFeedback}
        feedbackSubmitting={feedbackSubmitting}
        onExportJson={() => handleExport('json')}
        onExportCsv={() => handleExport('csv')}
        exporting={exporting}
      />
    </main>
  )
}
