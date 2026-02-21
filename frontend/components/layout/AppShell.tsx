'use client'

import { useEffect, useState, useSyncExternalStore } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'

import { canOpenPrd, canOpenScope, canRunFeasibility } from '../../lib/guards'
import { buildIdeaStepHref, resolveIdeaIdForRouting, type IdeaStep } from '../../lib/idea-routes'
import { useIdeasStore } from '../../lib/ideas-store'
import { useDecisionStore } from '../../lib/store'
import {
  clearAuthSession,
  getAuthSessionSnapshot,
  getAuthSessionServerSnapshot,
  subscribeAuthSession,
} from '../../lib/auth'

type StepItem = {
  step: 'ideas' | IdeaStep
  label: string
  description: string
  locked: boolean
  done: boolean
}

type AppShellProps = Readonly<{
  children: React.ReactNode
}>

const getIsActive = (pathname: string, step: StepItem['step']): boolean => {
  if (step === 'ideas') {
    return pathname === '/' || pathname === '/ideas'
  }

  const segment = `/${step}`

  if (pathname.startsWith('/ideas/')) {
    return pathname.includes(segment)
  }

  return pathname.startsWith(segment)
}

const getBadgeLabel = (
  item: StepItem,
  isHydrated: boolean
): 'Done' | 'Locked' | 'Open' | 'Syncing' => {
  if (!isHydrated) {
    return 'Syncing'
  }

  if (item.done) {
    return 'Done'
  }

  return item.locked ? 'Locked' : 'Open'
}

const getBadgeClassName = (item: StepItem, isHydrated: boolean): string => {
  if (!isHydrated) {
    return 'border-slate-300 bg-slate-100 text-slate-500'
  }

  if (item.done) {
    return 'border-emerald-300 bg-emerald-50 text-emerald-700'
  }

  if (item.locked) {
    return 'border-slate-300 bg-slate-100 text-slate-500'
  }

  return 'border-blue-200 bg-blue-50 text-blue-700'
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname()
  const router = useRouter()
  const isLoginRoute = pathname === '/login'
  const [mounted, setMounted] = useState(false)
  const authSession = useSyncExternalStore(
    subscribeAuthSession,
    getAuthSessionSnapshot,
    getAuthSessionServerSnapshot
  )

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!mounted) return
    if (!authSession && !isLoginRoute) {
      router.replace('/login')
      return
    }
    if (authSession && isLoginRoute) {
      router.replace('/ideas')
    }
  }, [mounted, authSession, isLoginRoute, pathname, router])

  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const setActiveIdeaId = useIdeasStore((state) => state.setActiveIdeaId)
  useEffect(() => {
    const match = pathname.match(/^\/ideas\/([^/]+)/)
    if (match?.[1]) {
      setActiveIdeaId(match[1])
    }
  }, [pathname, setActiveIdeaId])
  const isHydrated = useSyncExternalStore(
    (onStoreChange) => {
      const unsubscribeHydrate = useDecisionStore.persist.onHydrate(onStoreChange)
      const unsubscribeFinishHydration = useDecisionStore.persist.onFinishHydration(onStoreChange)

      return () => {
        unsubscribeHydrate()
        unsubscribeFinishHydration()
      }
    },
    () => useDecisionStore.persist.hasHydrated(),
    () => false
  )
  const context = useDecisionStore((state) => state.context)
  const hydratedContext = isHydrated ? context : null

  const feasibilityOpen = hydratedContext ? canRunFeasibility(hydratedContext) : false
  const scopeOpen = hydratedContext ? canOpenScope(hydratedContext) : false
  const prdOpen = hydratedContext ? canOpenPrd(hydratedContext) : false

  const steps: StepItem[] = [
    {
      step: 'ideas',
      label: 'Ideas',
      description: 'Workspace ideas',
      locked: false,
      done: Boolean(hydratedContext?.idea_seed),
    },
    {
      step: 'idea-canvas',
      label: 'Idea Canvas',
      description: 'DAG path confirm',
      locked: false,
      done: Boolean(hydratedContext?.confirmed_dag_path_id),
    },
    {
      step: 'feasibility',
      label: 'Feasibility',
      description: 'Plan generation',
      locked: !feasibilityOpen,
      done: Boolean(hydratedContext?.selected_plan_id),
    },
    {
      step: 'scope-freeze',
      label: 'Scope Freeze',
      description: 'Boundaries',
      locked: !scopeOpen,
      done: Boolean(
        hydratedContext?.current_scope_baseline_id ||
        hydratedContext?.scope_frozen ||
        hydratedContext?.scope
      ),
    },
    {
      step: 'prd',
      label: 'PRD',
      description: 'Output document',
      locked: !prdOpen,
      done: Boolean(hydratedContext?.prd),
    },
  ]

  const routeIdeaId = resolveIdeaIdForRouting(pathname, activeIdeaId)
  const getStepHref = (step: StepItem['step']): string => {
    if (step === 'ideas') {
      return '/ideas'
    }

    if (step === 'prd' && routeIdeaId && hydratedContext?.current_scope_baseline_id) {
      return buildIdeaStepHref(routeIdeaId, step, {
        baseline_id: hydratedContext.current_scope_baseline_id,
      })
    }

    return routeIdeaId ? buildIdeaStepHref(routeIdeaId, step) : '/ideas'
  }

  if (isLoginRoute) {
    return <>{children}</>
  }

  if (!mounted || !authSession) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-xl items-center justify-center px-6 text-sm text-slate-600">
        Verifying session...
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-slate-900 focus:shadow-md focus:ring-2 focus:ring-blue-500 focus:outline-none"
      >
        Skip to main content
      </a>
      <header className="fixed top-0 right-0 left-0 z-30 border-b border-slate-200/90 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/75">
        <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold tracking-[0.22em] text-slate-500 uppercase">
                DecisionOS
              </p>
              <h1 className="text-lg font-semibold text-slate-900">Command Center</h1>
            </div>
            <div className="flex items-center gap-4">
              <p className="text-xs text-slate-500">
                Session: {hydratedContext ? hydratedContext.session_id.slice(0, 8) : 'Syncing...'}
              </p>
              <p className="text-xs text-slate-500">
                User: {authSession.username} ({authSession.role})
              </p>
              <Link
                href="/settings"
                className="cursor-pointer rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400"
              >
                Settings
              </Link>
              <button
                type="button"
                onClick={() => {
                  clearAuthSession()
                  router.replace('/login')
                }}
                className="cursor-pointer rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400"
              >
                Logout
              </button>
            </div>
          </div>
          <nav aria-label="Workflow steps">
            <ul className="grid gap-2 md:grid-cols-5">
              {steps.map((item, index) => {
                const isActive = getIsActive(pathname, item.step)
                const badgeLabel = getBadgeLabel(item, isHydrated)
                const sharedClassName =
                  'group flex min-h-16 flex-col rounded-xl border px-3 py-2 text-left transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400'
                const stateClassName = isActive
                  ? 'border-blue-400 bg-blue-50/90 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-blue-200 hover:bg-blue-50/60'

                const content = (
                  <>
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-semibold text-slate-500">Step {index + 1}</span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${getBadgeClassName(item, isHydrated)}`}
                      >
                        {badgeLabel}
                      </span>
                    </div>
                    <span className="mt-0.5 text-sm font-semibold text-slate-900">
                      {item.label}
                    </span>
                    <span className="text-xs text-slate-500">{item.description}</span>
                  </>
                )

                const noIdeaSelected = item.step !== 'ideas' && !routeIdeaId
                if (item.locked || noIdeaSelected) {
                  return (
                    <li key={item.step}>
                      <span
                        aria-current={isActive ? 'step' : undefined}
                        aria-disabled="true"
                        className={`${sharedClassName} ${stateClassName} cursor-not-allowed opacity-75`}
                      >
                        {content}
                      </span>
                    </li>
                  )
                }

                return (
                  <li key={item.step}>
                    <Link
                      href={getStepHref(item.step)}
                      aria-current={isActive ? 'step' : undefined}
                      className={`${sharedClassName} ${stateClassName}`}
                    >
                      {content}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </nav>
        </div>
      </header>

      <div className="mx-auto w-full max-w-[1480px] px-4 pt-44 pb-8 sm:px-6 lg:px-8">
        <section
          id="main-content"
          tabIndex={-1}
          className="min-w-0 rounded-2xl border border-slate-200 bg-white/90 shadow-[0_12px_38px_-28px_rgba(15,23,42,0.45)] transition-shadow duration-300 motion-reduce:transition-none"
        >
          {children}
        </section>
      </div>
    </div>
  )
}
