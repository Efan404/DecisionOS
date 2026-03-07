'use client'

import { useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { GuardPanel } from '../common/GuardPanel'
import { PlanDetail } from './PlanDetail'
import { ApiError, patchIdeaContext } from '../../lib/api'
import { buildIdeaStepHref, resolveIdeaIdForRouting } from '../../lib/idea-routes'
import { useIdeasStore } from '../../lib/ideas-store'
import { useDecisionStore } from '../../lib/store'

type FeasibilityDetailClientProps = {
  planId: string
}

export function FeasibilityDetailClient({ planId }: FeasibilityDetailClientProps) {
  const router = useRouter()
  const pathname = usePathname()
  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const activeIdea = useIdeasStore(
    (state) => state.ideas.find((idea) => idea.id === state.activeIdeaId) ?? null
  )
  const setIdeaVersion = useIdeasStore((state) => state.setIdeaVersion)
  const loadIdeaDetail = useIdeasStore((state) => state.loadIdeaDetail)
  const context = useDecisionStore((state) => state.context)
  const setPlan = useDecisionStore((state) => state.plan)
  const replaceContext = useDecisionStore((state) => state.replaceContext)
  const plan = context.feasibility?.plans.find((item) => item.id === planId) ?? null
  const [confirming, setConfirming] = useState(false)

  if (!context.feasibility) {
    return (
      <GuardPanel
        title="No feasibility context"
        description="Generate and select a feasibility plan before opening this page."
      />
    )
  }

  if (!plan) {
    return (
      <GuardPanel
        title="Plan not found"
        description="This plan is not in the current feasibility result. Return to the list and choose again."
      />
    )
  }

  const handleConfirm = async () => {
    setConfirming(true)
    const routeIdeaId = resolveIdeaIdForRouting(pathname, activeIdeaId)
    try {
      setPlan(plan.id)
      if (!routeIdeaId) {
        router.push('/ideas')
        return
      }
      if (!activeIdea) {
        toast.error('Missing active idea context')
        return
      }

      const detail = await patchIdeaContext(routeIdeaId, {
        version: activeIdea.version,
        context: {
          ...context,
          selected_plan_id: plan.id,
        },
      })
      setIdeaVersion(routeIdeaId, detail.version)
      replaceContext(detail.context)
      toast.success('Plan confirmed')
      router.push(buildIdeaStepHref(routeIdeaId, 'scope-freeze'))
    } catch (error) {
      if (
        routeIdeaId &&
        error instanceof ApiError &&
        error.status === 409 &&
        error.code === 'IDEA_VERSION_CONFLICT'
      ) {
        const latest = await loadIdeaDetail(routeIdeaId)
        if (latest) {
          replaceContext(latest.context)
          setIdeaVersion(routeIdeaId, latest.version)
        }
        toast.error('Idea changed in another session. Reloaded latest data.')
        return
      }

      const message =
        error instanceof Error ? error.message : 'Failed to confirm this plan.'
      toast.error(message)
    } finally {
      setConfirming(false)
    }
  }

  return <PlanDetail plan={plan} onConfirm={() => void handleConfirm()} confirming={confirming} />
}
