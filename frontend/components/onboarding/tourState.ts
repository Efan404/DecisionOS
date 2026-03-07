import { useEffect, useState } from 'react'

// ── Step definitions ──────────────────────────────────────────────────────────

export interface TourStep {
  selector: string
  title: string
  content: string
  side?: 'top' | 'bottom' | 'left' | 'right'
  nextRoute?: string
  padding?: number
  radius?: number
}

export const STEPS: TourStep[] = [
  {
    selector: '#onboarding-help-btn',
    title: 'Welcome to DecisionOS',
    content:
      'This quick tour will walk you through the core workflow. Click Next to begin, or Skip to dismiss.',
    side: 'bottom',
    nextRoute: '/ideas',
    padding: 8,
    radius: 12,
  },
  {
    selector: '#onboarding-ideas-list',
    title: 'Your Idea Workspace',
    content: 'Create and manage your product ideas here. Select an idea to start the workflow.',
    side: 'bottom',
    padding: 8,
    radius: 12,
  },
  {
    selector: '#onboarding-new-idea-btn',
    title: 'Create a New Idea',
    content: 'Click here to add your first idea and begin the decision workflow.',
    side: 'bottom',
    padding: 4,
    radius: 8,
  },
  {
    selector: '#onboarding-dag-canvas',
    title: 'Idea Canvas',
    content:
      'Explore your idea as a decision tree. Click nodes to expand branches and find the best direction.',
    side: 'right',
    padding: 4,
    radius: 8,
  },
  {
    selector: '#onboarding-feasibility-cards',
    title: 'Feasibility Scorecards',
    content:
      'AI evaluates your idea across multiple dimensions. Review the plans and select the best fit.',
    side: 'top',
    padding: 4,
    radius: 8,
  },
  {
    selector: '#onboarding-confirm-plan-btn',
    title: 'Confirm a Plan',
    content: 'Confirming a plan unlocks the Scope Freeze stage.',
    side: 'top',
    padding: 4,
    radius: 8,
  },
  {
    selector: '#onboarding-scope-board',
    title: 'Scope Freeze',
    content: 'Drag features into IN or OUT scope, then freeze the baseline and continue to PRD.',
    side: 'top',
    padding: 4,
    radius: 8,
  },
  {
    selector: '#onboarding-prd-content',
    title: 'Your PRD',
    content:
      'The AI-generated PRD includes Requirements, Sections, and a Backlog. You can export it anytime.',
    side: 'top',
    padding: 4,
    radius: 8,
  },
  {
    selector: '#onboarding-help-btn',
    title: "You're all set!",
    content: 'Click the ? button anytime to replay this tour.',
    side: 'bottom',
    padding: 4,
    radius: 8,
  },
]

// ── Step routes ───────────────────────────────────────────────────────────────

export const STEP_ROUTES: Record<number, (ideaId: string | null) => string | null> = {
  2: (id) => (id ? `/ideas/${id}/idea-canvas` : null),
  3: (id) => (id ? `/ideas/${id}/feasibility` : null),
  5: (id) => (id ? `/ideas/${id}/scope-freeze` : null),
  6: (id) => (id ? `/ideas/${id}/prd` : null),
}

// ── Module-level state (avoids React context instance issues) ─────────────────

export type TourState = { active: boolean; stepIndex: number }
type TourListener = (s: TourState) => void

let _state: TourState = { active: false, stepIndex: 0 }
const _listeners = new Set<TourListener>()

export function _setState(next: Partial<TourState>) {
  _state = { ..._state, ...next }
  _listeners.forEach((fn) => fn(_state))
}

export function _useTourState(): TourState {
  const [s, setS] = useState(_state)
  useEffect(() => {
    setS(_state)
    _listeners.add(setS)
    return () => {
      _listeners.delete(setS)
    }
  }, [])
  return s
}
