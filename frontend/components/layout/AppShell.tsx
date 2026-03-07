'use client'

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useTranslations } from 'next-intl'
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
import { CircleHelp, Ghost, LogOut, Settings, TrendingUp } from 'lucide-react'
import { useTour } from '../onboarding/OnboardingProvider'
import { NotificationBell } from '../notifications/NotificationBell'

type NavKey = 'ideas' | 'ideaCanvas' | 'feasibility' | 'scopeFreeze' | 'prd'

type StepItem = {
  step: 'ideas' | IdeaStep
  navKey: NavKey
  descKey: NavKey
  locked: boolean
  done: boolean
}

type AppShellProps = Readonly<{
  children: React.ReactNode
}>

// Step nav keys — labels resolved via useTranslations('nav') at render time
const NAV_STEPS = [
  { step: 'ideas' as const, navKey: 'ideas' as const, descKey: 'ideas' as const },
  { step: 'idea-canvas' as const, navKey: 'ideaCanvas' as const, descKey: 'ideaCanvas' as const },
  { step: 'feasibility' as const, navKey: 'feasibility' as const, descKey: 'feasibility' as const },
  {
    step: 'scope-freeze' as const,
    navKey: 'scopeFreeze' as const,
    descKey: 'scopeFreeze' as const,
  },
  { step: 'prd' as const, navKey: 'prd' as const, descKey: 'prd' as const },
]

const getIsActive = (pathname: string, step: StepItem['step']): boolean => {
  if (step === 'ideas') return pathname === '/' || pathname === '/ideas'
  const segment = `/${step}`
  if (pathname.startsWith('/ideas/')) return pathname.includes(segment)
  return pathname.startsWith(segment)
}

const getBadgeLabel = (
  item: StepItem,
  isHydrated: boolean,
  tCommon: ReturnType<typeof useTranslations<'common'>>
) => {
  if (!isHydrated) return tCommon('syncing')
  if (item.done) return tCommon('done')
  return item.locked ? tCommon('locked') : tCommon('open')
}

export function AppShell({ children }: AppShellProps) {
  const tNav = useTranslations('nav')
  const tCommon = useTranslations('common')
  const pathname = usePathname()
  const router = useRouter()
  const { startTour } = useTour()

  const handleStartTour = () => {
    startTour()
  }
  const isLoginRoute = pathname === '/login'
  const [mounted, setMounted] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const navRef = useRef<HTMLDivElement>(null)

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
    if (authSession && isLoginRoute) router.replace('/ideas')
  }, [mounted, authSession, isLoginRoute, pathname, router])

  // Close mobile nav on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setMobileNavOpen(false)
      }
    }
    if (mobileNavOpen) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [mobileNavOpen])

  const activeIdeaId = useIdeasStore((state) => state.activeIdeaId)
  const setActiveIdeaId = useIdeasStore((state) => state.setActiveIdeaId)
  useEffect(() => {
    const match = pathname.match(/^\/ideas\/([^/]+)/)
    if (match?.[1]) setActiveIdeaId(match[1])
  }, [pathname, setActiveIdeaId])

  const isHydrated = useSyncExternalStore(
    (onStoreChange) => {
      const u1 = useDecisionStore.persist.onHydrate(onStoreChange)
      const u2 = useDecisionStore.persist.onFinishHydration(onStoreChange)
      return () => {
        u1()
        u2()
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

  const lockedByStep: Record<string, boolean> = {
    ideas: false,
    'idea-canvas': false,
    feasibility: !feasibilityOpen,
    'scope-freeze': !scopeOpen,
    prd: !prdOpen,
  }
  const doneByStep: Record<string, boolean> = {
    ideas: Boolean(hydratedContext?.idea_seed),
    'idea-canvas': Boolean(hydratedContext?.confirmed_dag_path_id),
    feasibility: Boolean(hydratedContext?.selected_plan_id),
    'scope-freeze': Boolean(hydratedContext?.scope_frozen),
    prd: Boolean(hydratedContext?.scope_frozen && hydratedContext?.prd),
  }

  const steps: StepItem[] = NAV_STEPS.map(({ step, navKey, descKey }) => ({
    step,
    navKey,
    descKey,
    locked: lockedByStep[step],
    done: doneByStep[step],
  }))

  const routeIdeaId = resolveIdeaIdForRouting(pathname, activeIdeaId)
  const getStepHref = (step: StepItem['step']): string => {
    if (step === 'ideas') return '/ideas'
    if (step === 'prd' && routeIdeaId && hydratedContext?.current_scope_baseline_id)
      return buildIdeaStepHref(routeIdeaId, step, {
        baseline_id: hydratedContext.current_scope_baseline_id,
      })
    return routeIdeaId ? buildIdeaStepHref(routeIdeaId, step) : '/ideas'
  }

  if (isLoginRoute) return <>{children}</>

  if (!mounted || !authSession) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white text-sm text-[#1e1e1e]/40">
        Verifying session…
      </div>
    )
  }

  // ── Step card renderer ──────────────────────────────────────────────────────
  const renderStepCard = (item: StepItem, index: number) => {
    const isActive = getIsActive(pathname, item.step)
    const badgeLabel = getBadgeLabel(item, isHydrated, tCommon)
    const noIdeaSelected = item.step !== 'ideas' && !routeIdeaId
    const disabled = item.locked || noIdeaSelected

    // Three-state color logic:
    // active  → #1e1e1e bg, #b9eb10 accents, white text
    // done    → white bg, #1e1e1e border + text, #b9eb10 done badge
    // default → light gray bg, muted text
    const cardBg = isActive ? '#1e1e1e' : '#f0f0f0'
    const cardBorder = isActive ? '#b9eb10' : item.done ? '#1e1e1e33' : '#e0e0e0'
    const cardShadow = isActive
      ? '0 0 0 3px #b9eb1033, 0 4px 16px 0 #b9eb1022'
      : '0 1px 4px 0 rgba(0,0,0,0.06)'
    const labelColor = isActive ? '#b9eb10' : '#1e1e1e99'
    const titleColor = isActive ? '#ffffff' : item.done ? '#1e1e1e' : '#1e1e1e66'
    const descColor = isActive ? '#ffffff88' : '#1e1e1e44'

    const card = (
      <div
        className="relative flex min-h-[88px] flex-col justify-between overflow-hidden rounded-2xl p-3.5 transition-all duration-200"
        style={{
          background: cardBg,
          border: `1.5px solid ${cardBorder}`,
          boxShadow: cardShadow,
          opacity: disabled && !isActive ? 0.45 : 1,
          cursor: disabled ? 'not-allowed' : 'pointer',
        }}
      >
        {/* Top row: step number + badge */}
        <div className="flex items-center justify-between gap-2">
          <span
            className="text-[11px] font-bold tracking-widest uppercase"
            style={{ color: labelColor }}
          >
            Step {index + 1}
          </span>
          <span
            className="rounded-full px-2 py-0.5 text-[10px] font-bold"
            style={{
              background: item.done ? '#b9eb10' : isActive ? '#b9eb1022' : 'rgba(0,0,0,0.06)',
              color: item.done ? '#1e1e1e' : isActive ? '#b9eb10' : '#1e1e1e66',
              border: `1px solid ${item.done ? '#b9eb10' : isActive ? '#b9eb1055' : '#1e1e1e18'}`,
            }}
          >
            {badgeLabel}
          </span>
        </div>

        {/* Label + description */}
        <div className="mt-2">
          <p className="text-sm leading-tight font-bold" style={{ color: titleColor }}>
            {tNav(item.navKey)}
          </p>
          <p className="mt-0.5 text-[11px]" style={{ color: descColor }}>
            {tNav(`descriptions.${item.descKey}`)}
          </p>
        </div>

        {/* Active indicator dot */}
        {isActive && (
          <span
            className="absolute right-3 bottom-3 h-2 w-2 rounded-full"
            style={{ background: '#b9eb10', boxShadow: '0 0 6px 2px #b9eb1088' }}
          />
        )}
      </div>
    )

    return (
      <li key={item.step}>
        {disabled ? (
          <span aria-current={isActive ? 'step' : undefined} aria-disabled="true">
            {card}
          </span>
        ) : (
          <Link
            href={getStepHref(item.step)}
            aria-current={isActive ? 'step' : undefined}
            className="block rounded-2xl focus-visible:ring-2 focus-visible:ring-[#1e1e1e]/30 focus-visible:outline-none"
            onClick={() => setMobileNavOpen(false)}
          >
            {card}
          </Link>
        )}
      </li>
    )
  }

  return (
    <div className="min-h-screen bg-[#f5f5f5]">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:shadow-md focus:ring-2 focus:ring-[#1e1e1e]/30 focus:outline-none"
      >
        Skip to main content
      </a>

      {/* ── Top navbar ─────────────────────────────────────────────────────── */}
      <header className="border-b border-[#1e1e1e]/8 bg-white shadow-sm">
        <div className="mx-auto flex w-full max-w-[1480px] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <svg
              viewBox="0 0 544.24 544.24"
              className="h-8 w-8 shrink-0"
              xmlns="http://www.w3.org/2000/svg"
            >
              <circle fill="#1e1e1e" cx="272.12" cy="272.12" r="272.12" />
              <path
                fill="#b9eb10"
                d="M110.49,444.14l95.71-130.92h38.18l-70.41,99.18,140.38.05c25.17-1.11,44.55-6.16,61.46-25.82l75.49-104.13-.1-1.96-79.85-108.68c-9.44-9.79-31.52-21.3-45.16-21.3h-169.1l73.39,101.16h-40.66L94.63,118.84l230.64-.05c33.58,2.41,58.79,16.74,79.19,42.8,29.8,38.08,55.9,79.5,85.77,117.59l.92,2.65-93,128.12c-13.55,15.43-45.17,34.19-65.98,34.19H110.49Z"
              />
              <path
                fill="#b9eb10"
                d="M218.6,387.61l63.48-89.26h-124.47c-15.49,28.8-60.79,21-63.02-12.35-2.5-37.3,43.77-50.16,63.02-19.38h123.48l-28.75-28.28c-.34-2.1.33-1.17,1.36-1.57,4.46-1.75,8.23-2.75,12.44-5.44,4.46-2.85,7-6.62,11.35-9.27l67.01,61.78c-11.74,12.69-27.95,23.34-39.12,36.32-9.28,10.79-16.9,24.78-26.27,35.72h46.12c1.21,0,6.24-3.34,7.42-4.48l50.13-68.91c.55-1.25-1.92-4.1-2.69-5.28-11.76-17.91-32.5-48.3-46.46-63.62-3.55-3.89-5.82-6-11.32-6.53-18.1-1.74-38.96,1.41-57.37.03-18.21,27.35-61.19,7.8-50.33-24.32,7.82-23.11,35.85-23.95,51.14-7.42,31.2,2.73,69.42-9.47,92.69,17.4l64.01,87.81v2.87s-64.47,87.34-64.47,87.34c-6.11,7.27-21.25,16.85-30.76,16.85h-108.6ZM238.15,181.52c-11.38,2.58-9.74,21.43,3.72,20.66,15.48-.88,10.74-23.94-3.72-20.66ZM125.12,269.79c-13.38,2.57-13.89,23.99-.27,25.6,22.68,2.68,18.53-29.11.27-25.6Z"
              />
            </svg>
            <div>
              <p className="text-[10px] leading-none font-bold tracking-[0.2em] text-[#1e1e1e]/35 uppercase">
                DecisionOS
              </p>
              <p className="text-sm leading-tight font-bold text-[#1e1e1e]">Command Center</p>
            </div>
          </div>

          {/* Right controls */}
          <div className="flex items-center gap-2">
            {/* Group 1: Insights + Notifications (related intel) */}
            <div className="hidden items-center gap-1 sm:flex">
              <Link
                href="/insights"
                aria-label="Market Insights"
                title="Market Insights"
                className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border border-[#1e1e1e]/12 bg-white text-[#1e1e1e]/45 transition-colors duration-150 hover:bg-[#f5f5f5] hover:text-[#1e1e1e]/80"
              >
                <TrendingUp size={14} />
              </Link>
              <NotificationBell />
            </div>
            {/* Mobile: bell only */}
            <div className="sm:hidden">
              <NotificationBell />
            </div>

            {/* Group 2: Help / tour trigger — standalone */}
            <button
              id="onboarding-help-btn"
              type="button"
              onClick={handleStartTour}
              aria-label="Start guided tour"
              title="Guided tour"
              className="relative flex h-8 w-8 items-center justify-center rounded-lg border border-[#1e1e1e]/12 bg-white text-[#1e1e1e]/45 transition hover:bg-[#f5f5f5] hover:text-[#1e1e1e]/80"
            >
              <CircleHelp size={14} />
            </button>

            {/* Group 3: Settings | Profile | Logout */}
            <div className="hidden items-center divide-x divide-[#1e1e1e]/10 overflow-hidden rounded-lg border border-[#1e1e1e]/12 bg-white sm:flex">
              <Link
                href="/settings"
                aria-label="Settings"
                title="Settings"
                className="flex h-8 w-8 cursor-pointer items-center justify-center text-[#1e1e1e]/45 transition-colors duration-150 hover:bg-[#f5f5f5] hover:text-[#1e1e1e]/80"
              >
                <Settings size={14} />
              </Link>
              <Link
                href="/profile"
                aria-label={`Profile: ${authSession.username}`}
                title={authSession.username}
                className="flex h-8 w-8 cursor-pointer items-center justify-center text-[#1e1e1e]/45 transition-colors duration-150 hover:bg-[#f5f5f5] hover:text-[#1e1e1e]/80"
              >
                <Ghost size={14} />
              </Link>
              <button
                type="button"
                aria-label="Logout"
                title="Logout"
                onClick={() => {
                  clearAuthSession()
                  router.replace('/login')
                }}
                className="flex h-8 w-8 cursor-pointer items-center justify-center text-[#1e1e1e]/45 transition-colors duration-150 hover:bg-red-50 hover:text-red-500"
              >
                <LogOut size={14} />
              </button>
            </div>

            {/* Mobile hamburger */}
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#1e1e1e]/12 bg-white md:hidden"
              onClick={() => setMobileNavOpen((v) => !v)}
              aria-label="Toggle navigation"
            >
              <svg viewBox="0 0 16 16" fill="none" className="h-4 w-4">
                <path
                  d={mobileNavOpen ? 'M3 3l10 10M13 3L3 13' : 'M2 4h12M2 8h12M2 12h12'}
                  stroke="#1e1e1e"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Step nav (desktop: card grid; mobile: horizontal strip) ─────── */}
        {/* Desktop */}
        <nav aria-label="Workflow steps" className="hidden border-t border-[#1e1e1e]/6 md:block">
          <ul className="mx-auto grid w-full max-w-[1480px] grid-cols-5 gap-2.5 px-4 py-2.5 sm:px-6 lg:px-8">
            {steps.map((item, index) => renderStepCard(item, index))}
          </ul>
        </nav>

        {/* Mobile horizontal scrollable step strip */}
        <nav
          aria-label="Workflow steps"
          className="flex overflow-x-auto border-t border-[#1e1e1e]/6 bg-white px-3 py-2 md:hidden"
        >
          {steps.map((item) => {
            const isActive = getIsActive(pathname, item.step)
            const noIdeaSelected =
              item.step !== 'ideas' && !resolveIdeaIdForRouting(pathname, activeIdeaId)
            const disabled = item.locked || noIdeaSelected
            return (
              <span key={item.step} className="shrink-0 px-0.5">
                {disabled ? (
                  <span
                    className={`block rounded-full px-3 py-1.5 text-xs font-medium whitespace-nowrap ${
                      isActive ? 'bg-[#1e1e1e] text-[#b9eb10]' : 'text-[#1e1e1e]/30'
                    }`}
                  >
                    {tNav(item.navKey)}
                  </span>
                ) : (
                  <Link
                    href={getStepHref(item.step)}
                    aria-current={isActive ? 'step' : undefined}
                    onClick={() => setMobileNavOpen(false)}
                    className={`block rounded-full px-3 py-1.5 text-xs font-medium whitespace-nowrap transition ${
                      isActive
                        ? 'bg-[#1e1e1e] text-[#b9eb10]'
                        : 'text-[#1e1e1e]/60 hover:bg-[#f5f5f5]'
                    }`}
                  >
                    {tNav(item.navKey)}
                  </Link>
                )}
              </span>
            )
          })}
        </nav>

        {/* Mobile drawer (hamburger) — step cards + Settings/Logout */}
        {mobileNavOpen && (
          <nav
            ref={navRef}
            aria-label="Workflow steps"
            className="border-t border-[#1e1e1e]/6 bg-white md:hidden"
          >
            <ul className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3">
              {steps.map((item, index) => renderStepCard(item, index))}
            </ul>
            <div className="flex items-center gap-2 border-t border-[#1e1e1e]/8 px-4 py-3">
              <Link
                href="/profile"
                onClick={() => setMobileNavOpen(false)}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-[#1e1e1e]/12 bg-[#f5f5f5] px-3 py-2 text-xs font-medium text-[#1e1e1e]/70 transition hover:bg-[#ebebeb]"
              >
                <Ghost size={13} />
                {authSession.username}
              </Link>
              <Link
                href="/insights"
                onClick={() => setMobileNavOpen(false)}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-[#1e1e1e]/12 bg-[#f5f5f5] px-3 py-2 text-xs font-medium text-[#1e1e1e]/70 transition hover:bg-[#ebebeb]"
              >
                <TrendingUp size={13} />
                Insights
              </Link>
              <Link
                href="/settings"
                onClick={() => setMobileNavOpen(false)}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-[#1e1e1e]/12 bg-[#f5f5f5] px-3 py-2 text-xs font-medium text-[#1e1e1e]/70 transition hover:bg-[#ebebeb]"
              >
                <Settings size={13} />
                Settings
              </Link>
              <button
                type="button"
                onClick={() => {
                  setMobileNavOpen(false)
                  clearAuthSession()
                  router.replace('/login')
                }}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-[#1e1e1e]/12 bg-[#f5f5f5] px-3 py-2 text-xs font-medium text-[#1e1e1e]/70 transition hover:bg-[#ebebeb]"
              >
                <LogOut size={13} />
                Logout
              </button>
            </div>
          </nav>
        )}
      </header>

      {/* ── Main content ───────────────────────────────────────────────────── */}
      <div className="mx-auto w-full max-w-[1480px] px-4 pt-6 pb-8 sm:px-6 lg:px-8">
        <section
          id="main-content"
          tabIndex={-1}
          className="min-w-0 rounded-2xl border border-[#1e1e1e]/8 bg-white shadow-[0_4px_32px_0_rgba(0,0,0,0.07)]"
        >
          {children}
        </section>
      </div>
    </div>
  )
}
