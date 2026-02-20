'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { usePathname, useRouter } from 'next/navigation'
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Bubble } from './Bubble'
import { PathCards } from './PathCards'
import { postIdeaScopedAgent } from '../../lib/api'
import { buildIdeaStepHref, resolveIdeaIdForRouting } from '../../lib/idea-routes'
import { useIdeasStore } from '../../lib/ideas-store'
import { isSseEventError, streamPost } from '../../lib/sse'
import {
  OPPORTUNITY_DEFAULT_COUNT,
  OPPORTUNITY_MAX_COUNT,
  OPPORTUNITY_MIN_COUNT,
  PATHS,
  agentEnvelopeSchema,
  opportunityOutputSchema,
  type Direction,
  type OpportunityOutput,
  type PathId,
} from '../../lib/schemas'
import { useDecisionStore } from '../../lib/store'

const isAbortError = (error: unknown): boolean => {
  return error instanceof DOMException && error.name === 'AbortError'
}

const BUBBLE_RADIUS = 220
const MIN_BUBBLE_RADIUS = 140
const DIRECTION_COUNT_OPTIONS = [1, 2, 3, 4, 5, 6] as const

const clampDirectionCount = (value: number): number => {
  return Math.min(OPPORTUNITY_MAX_COUNT, Math.max(OPPORTUNITY_MIN_COUNT, value))
}

export function IdeaCanvas() {
  const router = useRouter()
  const pathname = usePathname()
  const context = useDecisionStore((state) => state.context)
  const setIdea = useDecisionStore((state) => state.idea)
  const setOpportunity = useDecisionStore((state) => state.opportunity)
  const setDirection = useDecisionStore((state) => state.direction)
  const setPath = useDecisionStore((state) => state.path)
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const activeIdea = useIdeasStore(
    (state) => state.ideas.find((idea) => idea.id === state.activeIdeaId) ?? null
  )
  const setIdeaVersion = useIdeasStore((state) => state.setIdeaVersion)
  const [ideaSeedInput, setIdeaSeedInput] = useState(context.idea_seed ?? '')
  const [directions, setDirections] = useState<Direction[]>(context.opportunity?.directions ?? [])
  const [directionCount, setDirectionCount] = useState(() =>
    clampDirectionCount(context.opportunity?.directions.length ?? OPPORTUNITY_DEFAULT_COUNT)
  )
  const [progressPct, setProgressPct] = useState<number>(0)
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [bubbleRadius, setBubbleRadius] = useState(BUBBLE_RADIUS)
  const abortRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(false)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      abortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (context.opportunity?.directions) {
      setDirections(context.opportunity.directions)
      setDirectionCount(clampDirectionCount(context.opportunity.directions.length))
    }
  }, [context.opportunity])

  useEffect(() => {
    const syncRadius = () => {
      const responsiveRadius = Math.floor(window.innerWidth * 0.3)
      setBubbleRadius(Math.max(MIN_BUBBLE_RADIUS, Math.min(BUBBLE_RADIUS, responsiveRadius)))
    }

    syncRadius()
    window.addEventListener('resize', syncRadius)
    return () => {
      window.removeEventListener('resize', syncRadius)
    }
  }, [])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const ideaSeed = ideaSeedInput.trim()
    if (!ideaSeed) {
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setErrorMessage(null)
    setProgressPct(0)
    setDirections([])
    setIdea(ideaSeed)

    if (!activeIdeaId || !activeIdea) {
      const message = 'Missing active idea context'
      setLoading(false)
      setErrorMessage(message)
      toast.error(message)
      return
    }

    let streamedDonePayload: unknown = null
    try {
      let shouldFallback = false

      try {
        await streamPost(
          `/ideas/${activeIdeaId}/agents/opportunity/stream`,
          { idea_seed: ideaSeed, count: directionCount, version: activeIdea.version },
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
                !('direction' in data)
              ) {
                return
              }

              const parsed = opportunityOutputSchema.shape.directions.element.safeParse(
                (data as { direction: unknown }).direction
              )
              if (!parsed.success) {
                return
              }

              setDirections((prev) => {
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

        const parsedData = opportunityOutputSchema.safeParse(envelope.data.data)
        if (!parsedData.success) {
          throw new Error('Opportunity payload shape mismatch.')
        }
        const streamedOutput: OpportunityOutput = parsedData.data
        setIdeaVersion(activeIdeaId, envelope.data.idea_version)

        if (mountedRef.current) {
          setDirections(streamedOutput.directions)
        }
        setOpportunity(streamedOutput)
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
          { idea_seed: string; count: number; version: number },
          OpportunityOutput
        >(activeIdeaId, 'opportunity', {
          idea_seed: ideaSeed,
          count: directionCount,
          version: activeIdea.version,
        })
        setIdeaVersion(activeIdeaId, envelope.idea_version)
        const parsed = opportunityOutputSchema.safeParse(envelope.data)

        if (!parsed.success) {
          throw new Error('Opportunity payload shape mismatch.')
        }

        if (mountedRef.current) {
          setDirections(parsed.data.directions)
        }
        setOpportunity(parsed.data)
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

  const handleSelectDirection = (directionId: Direction['id']) => {
    setDirection(directionId)
    toast.success(`Direction ${directionId} selected`)
  }

  const handleSelectPath = (pathId: PathId) => {
    setPath(pathId)
    toast.success('Path selected, moving to feasibility')
    const routeIdeaId = resolveIdeaIdForRouting(pathname, activeIdeaId)
    router.push(routeIdeaId ? buildIdeaStepHref(routeIdeaId, 'feasibility') : '/ideas')
  }

  const visibleDirections = useMemo(() => directions, [directions])

  const selectedDirectionId = context.selected_direction_id
  const hasDirections = visibleDirections.length > 0
  const bubbleCenterClass = hasDirections ? 'top-[56%]' : 'top-1/2'

  const bubbleLayout = useMemo(() => {
    const total = visibleDirections.length
    if (!total) {
      return []
    }

    return visibleDirections.map((direction, index) => {
      const angleDeg = -90 + (index * 360) / total
      const angle = (angleDeg * Math.PI) / 180

      return {
        direction,
        x: Math.cos(angle) * bubbleRadius,
        y: Math.sin(angle) * bubbleRadius,
      }
    })
  }, [visibleDirections, bubbleRadius])

  return (
    <section className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">Idea Canvas</h1>
        <p className="mt-2 text-sm text-black/70">
          Enter an idea seed, generate directions, then choose a path for Feasibility.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="w-full rounded-3xl border border-black/15 bg-white/95 p-5 shadow-lg backdrop-blur"
      >
        <label htmlFor="idea-seed" className="text-sm font-medium">
          Idea Seed
        </label>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <input
            id="idea-seed"
            value={ideaSeedInput}
            onChange={(event) => setIdeaSeedInput(event.currentTarget.value)}
            placeholder="e.g. A 7-day delivery decision assistant for indie developers"
            className="w-full rounded-md border border-black/20 px-3 py-2 text-sm outline-none focus:border-black"
          />
          <button
            type="submit"
            disabled={loading || !ideaSeedInput.trim()}
            className="rounded-md border border-black px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Generating...' : 'Generate Directions'}
          </button>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <label htmlFor="direction-count" className="text-xs text-black/70">
            Direction count
          </label>
          <select
            id="direction-count"
            value={directionCount}
            onChange={(event) =>
              setDirectionCount(clampDirectionCount(Number(event.currentTarget.value)))
            }
            className="rounded-md border border-black/20 px-2 py-1 text-xs outline-none focus:border-black"
          >
            {DIRECTION_COUNT_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
        {loading ? <p className="mt-2 text-xs text-black/60">Streaming {progressPct}%</p> : null}
        {errorMessage ? <p className="mt-2 text-xs text-red-600">{errorMessage}</p> : null}
      </form>

      <div className="relative isolate h-[620px] overflow-hidden rounded-[32px] border border-black/10 bg-[radial-gradient(circle_at_20%_20%,rgba(0,0,0,0.06),transparent_35%),radial-gradient(circle_at_80%_80%,rgba(0,0,0,0.05),transparent_40%),linear-gradient(180deg,#ffffff_0%,#f8fafc_100%)]">
        <div
          className={`pointer-events-none absolute ${bubbleCenterClass} left-1/2 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-black/5`}
        />

        {bubbleLayout.map(({ direction, x, y }) => {
          const selected = selectedDirectionId === direction.id
          const hasSelected = Boolean(selectedDirectionId)

          return (
            <motion.div
              key={direction.id}
              className={`absolute ${bubbleCenterClass} left-1/2 z-20 -translate-x-1/2 -translate-y-1/2`}
              initial={{ opacity: 0, scale: 0.7, x: 0, y: 0 }}
              animate={
                hasSelected
                  ? selected
                    ? { x: 0, y: 0, opacity: 1, scale: 1.06 }
                    : { x, y, opacity: 0.2, scale: 0.9 }
                  : { x, y, opacity: 1, scale: 1 }
              }
              transition={{
                type: 'spring',
                stiffness: 280,
                damping: 24,
                mass: 0.8,
              }}
            >
              <Bubble
                direction={direction}
                selected={selected}
                subdued={hasSelected && !selected}
                onClick={() => handleSelectDirection(direction.id)}
              />
            </motion.div>
          )
        })}

        <AnimatePresence>
          {!loading && bubbleLayout.length === 0 ? (
            <motion.div
              key="empty-hint"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full border border-dashed border-black/20 bg-white/75 px-4 py-2 text-xs text-black/60"
            >
              After submitting an idea seed, {directionCount} direction bubbles will appear here.
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>

      <AnimatePresence mode="wait">
        {context.selected_direction_id ? (
          <motion.div
            key="paths"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            <PathCards
              paths={PATHS}
              selectedPathId={context.path_id}
              onSelect={(pathId) => handleSelectPath(pathId)}
            />
          </motion.div>
        ) : (
          <motion.div
            key="path-hint"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="rounded-lg border border-dashed border-black/30 p-4 text-sm text-black/70"
          >
            Select a direction first, then choose a path.
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
