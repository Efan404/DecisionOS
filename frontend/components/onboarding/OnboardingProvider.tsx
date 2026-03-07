'use client'

import { useEffect, useRef } from 'react'
import { OnbordaProvider as OnbordaContextProvider, Onborda, useOnborda } from 'onborda'
import type { Tour } from 'onborda'
import { OnboardingCard } from './OnboardingCard'
import { useOnboarding } from './useOnboarding'

const TOUR_NAME = 'main'

const steps: Tour[] = [
  {
    tour: TOUR_NAME,
    steps: [
      {
        selector: '#onboarding-ai-provider',
        title: 'Configure your AI Provider',
        content:
          'First, set up your AI provider — this powers all intelligent features in DecisionOS.',
        side: 'bottom',
        nextRoute: '/ideas',
        showControls: true,
        icon: null,
        pointerPadding: 8,
        pointerRadius: 12,
      },
      {
        selector: '#onboarding-ideas-list',
        title: 'Your Idea Workspace',
        content: 'Create and manage your product ideas here. Select an idea to start the workflow.',
        side: 'bottom',
        showControls: true,
        icon: null,
        pointerPadding: 8,
        pointerRadius: 12,
      },
      {
        selector: '#onboarding-new-idea-btn',
        title: 'Create a New Idea',
        content: 'Click here to add your first idea and begin the decision workflow.',
        side: 'bottom',
        showControls: true,
        icon: null,
        pointerPadding: 4,
        pointerRadius: 8,
      },
      {
        selector: '#onboarding-dag-canvas',
        title: 'Idea Canvas',
        content:
          'Explore your idea as a decision tree. Click nodes to expand branches and find the best direction.',
        side: 'right',
        showControls: true,
        icon: null,
        pointerPadding: 4,
        pointerRadius: 8,
      },
      {
        selector: '#onboarding-feasibility-cards',
        title: 'Feasibility Scorecards',
        content:
          'AI evaluates your idea across multiple dimensions. Review the plans and select the best fit.',
        side: 'top',
        showControls: true,
        icon: null,
        pointerPadding: 4,
        pointerRadius: 8,
      },
      {
        selector: '#onboarding-confirm-plan-btn',
        title: 'Confirm a Plan',
        content: 'Confirming a plan unlocks the Scope Freeze stage.',
        side: 'top',
        showControls: true,
        icon: null,
        pointerPadding: 4,
        pointerRadius: 8,
      },
      {
        selector: '#onboarding-scope-board',
        title: 'Scope Freeze',
        content: 'Drag features into IN or OUT scope to define clear boundaries for your product.',
        side: 'top',
        showControls: true,
        icon: null,
        pointerPadding: 4,
        pointerRadius: 8,
      },
      {
        selector: '#onboarding-freeze-btn',
        title: 'Freeze the Scope',
        content: 'Once satisfied, freeze the scope. This triggers AI to generate your PRD.',
        side: 'top',
        showControls: true,
        icon: null,
        pointerPadding: 8,
        pointerRadius: 8,
      },
      {
        selector: '#onboarding-prd-content',
        title: 'Your PRD',
        content:
          'The AI-generated PRD includes Requirements, Sections, and a Backlog. You can export it anytime.',
        side: 'top',
        showControls: true,
        icon: null,
        pointerPadding: 4,
        pointerRadius: 8,
      },
      {
        selector: '#onboarding-help-btn',
        title: "You're all set!",
        content: 'Click the ? button anytime to replay this tour.',
        side: 'bottom',
        showControls: true,
        icon: null,
        pointerPadding: 4,
        pointerRadius: 8,
      },
    ],
  },
]

/**
 * Inner component that has access to both OnbordaContext and useOnboarding.
 * Handles auto-start on mount and marks completion when the tour closes.
 */
function OnboardingAutoStart() {
  const { startOnborda, isOnbordaVisible } = useOnborda()
  const { shouldAutoStart, markCompleted } = useOnboarding()

  // Track whether we have ever started the tour in this session.
  const hasStartedRef = useRef(false)

  // Auto-start with a 600ms delay when shouldAutoStart is true.
  useEffect(() => {
    if (!shouldAutoStart) return
    const timer = setTimeout(() => {
      startOnborda(TOUR_NAME)
      hasStartedRef.current = true
    }, 600)
    return () => clearTimeout(timer)
  }, [shouldAutoStart, startOnborda])

  // Detect tour completion or dismissal: isOnbordaVisible flips to false
  // after we started the tour.
  useEffect(() => {
    if (hasStartedRef.current && !isOnbordaVisible) {
      markCompleted()
      hasStartedRef.current = false
    }
  }, [isOnbordaVisible, markCompleted])

  return null
}

/**
 * OnboardingProvider wraps the application in the onborda context and overlay,
 * and mounts the auto-start logic.
 */
export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  return (
    <OnbordaContextProvider>
      <Onborda steps={steps} shadowRgb="0,0,0" shadowOpacity="0.7" cardComponent={OnboardingCard}>
        {children}
      </Onborda>
      <OnboardingAutoStart />
    </OnbordaContextProvider>
  )
}
