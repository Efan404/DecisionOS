# Onboarding Guided Tour Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a first-time onboarding tour using Onborda that guides users through all 5 workflow steps, with a `?` help button in the header for re-triggering.

**Architecture:** Install `onborda` (Next.js-native, Framer Motion-powered), wrap `layout.tsx` with `OnbordaProvider`, define 10 cross-page steps with `nextRoute` for page transitions. A `useOnboarding` hook manages localStorage state. A custom `OnboardingCard` matches the `#b9eb10` / `#1e1e1e` design system.

**Tech Stack:** Next.js 14 App Router, TypeScript, Tailwind CSS, `onborda` (new), `framer-motion` (already installed), `lucide-react` (already used)

---

## Task 1: Create the worktree and install Onborda

**Files:**

- No code files — setup only

**Step 1: Create git worktree for this feature**

```bash
git worktree add ../pm-cursor-onboarding -b feat/onboarding-tour
cd ../pm-cursor-onboarding
```

**Step 2: Install onborda**

```bash
npm install onborda
```

Expected: `onborda` added to `package.json` dependencies.

**Step 3: Add onborda to Tailwind content scan**

Modify `tailwind.config.ts` (or `tailwind.config.js`) — find the `content` array and add:

```ts
'./node_modules/onborda/dist/**/*.{js,ts,jsx,tsx}'
```

**Step 4: Commit**

```bash
git add package.json package-lock.json tailwind.config.ts
git commit -m "chore: install onborda for guided tour"
```

---

## Task 2: Create the custom OnboardingCard component

**Files:**

- Create: `frontend/components/onboarding/OnboardingCard.tsx`

**Step 1: Create the file**

```tsx
'use client'

import type { CardComponentProps } from 'onborda'

export function OnboardingCard({
  step,
  currentStep,
  totalSteps,
  nextStep,
  prevStep,
  arrow,
  skipTour,
}: CardComponentProps) {
  const progress = ((currentStep + 1) / totalSteps) * 100

  return (
    <div
      className="relative w-72 rounded-2xl p-5 shadow-2xl"
      style={{ background: '#1e1e1e', border: '1.5px solid #b9eb1044' }}
    >
      {/* Arrow pointer rendered by onborda */}
      {arrow}

      {/* Step counter */}
      <div className="mb-3 flex items-center justify-between">
        <span
          className="text-[10px] font-bold uppercase tracking-widest"
          style={{ color: '#b9eb10' }}
        >
          Step {currentStep + 1} / {totalSteps}
        </span>
        <button
          type="button"
          onClick={skipTour}
          className="text-[11px] text-white/30 transition hover:text-white/60"
        >
          Skip
        </button>
      </div>

      {/* Progress bar */}
      <div className="mb-4 h-0.5 w-full rounded-full bg-white/10">
        <div
          className="h-0.5 rounded-full transition-all duration-300"
          style={{ width: `${progress}%`, background: '#b9eb10' }}
        />
      </div>

      {/* Title */}
      {step.title && <p className="mb-1.5 text-sm font-bold text-white">{step.title}</p>}

      {/* Content */}
      <div className="text-[13px] leading-relaxed text-white/70">{step.content}</div>

      {/* Nav buttons */}
      <div className="mt-5 flex items-center justify-between gap-2">
        {currentStep > 0 ? (
          <button
            type="button"
            onClick={prevStep}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-[12px] font-medium text-white/60 transition hover:border-white/30 hover:text-white"
          >
            Back
          </button>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={nextStep}
          className="rounded-lg px-4 py-1.5 text-[12px] font-bold text-[#1e1e1e] transition hover:brightness-110"
          style={{ background: '#b9eb10' }}
        >
          {currentStep + 1 === totalSteps ? 'Done' : 'Next'}
        </button>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/components/onboarding/OnboardingCard.tsx
git commit -m "feat(onboarding): add custom OnboardingCard component"
```

---

## Task 3: Create the useOnboarding hook

**Files:**

- Create: `frontend/components/onboarding/useOnboarding.ts`

**Step 1: Create the file**

```ts
'use client'

import { useCallback, useEffect, useState } from 'react'

const TOUR_KEY = 'decisionos_tour_completed'

export function useOnboarding() {
  const [shouldAutoStart, setShouldAutoStart] = useState(false)

  useEffect(() => {
    const completed = localStorage.getItem(TOUR_KEY)
    if (!completed) {
      setShouldAutoStart(true)
    }
  }, [])

  const markCompleted = useCallback(() => {
    localStorage.setItem(TOUR_KEY, 'true')
    setShouldAutoStart(false)
  }, [])

  const resetTour = useCallback(() => {
    localStorage.removeItem(TOUR_KEY)
  }, [])

  return { shouldAutoStart, markCompleted, resetTour }
}
```

**Step 2: Commit**

```bash
git add frontend/components/onboarding/useOnboarding.ts
git commit -m "feat(onboarding): add useOnboarding localStorage hook"
```

---

## Task 4: Create the OnboardingProvider with steps config

**Files:**

- Create: `frontend/components/onboarding/OnboardingProvider.tsx`

**Step 1: Create the file**

Note: Steps use `selector` (CSS selector for target element), `side` (tooltip position), `nextRoute`/`prevRoute` for cross-page navigation. Steps 1, 2, 8 use overlay (default Onborda behavior with dark backdrop). Others use `pointerPadding: 0` with no overlay for lighter feel — controlled via `showControls`.

```tsx
'use client'

import { useEffect } from 'react'
import { Onborda, OnbordaProvider as OnbordaProviderBase, useOnborda } from 'onborda'
import type { Step } from 'onborda'

import { OnboardingCard } from './OnboardingCard'
import { useOnboarding } from './useOnboarding'

const STEPS: Step[] = [
  // Step 1 — AI Provider (overlay, /settings)
  {
    icon: null,
    title: 'Configure your AI Provider',
    content: 'First, set up your AI provider — this powers all intelligent features in DecisionOS.',
    selector: '#onboarding-ai-provider',
    side: 'bottom',
    showControls: true,
    pointerPadding: 8,
    pointerRadius: 12,
    nextRoute: '/ideas',
  },
  // Step 2 — Ideas list (overlay, /ideas)
  {
    icon: null,
    title: 'Your Idea Workspace',
    content: 'Create and manage your product ideas here. Select an idea to start the workflow.',
    selector: '#onboarding-ideas-list',
    side: 'bottom',
    showControls: true,
    pointerPadding: 8,
    pointerRadius: 12,
  },
  // Step 3 — New idea button
  {
    icon: null,
    title: 'Create a New Idea',
    content: 'Click here to add your first idea and begin the decision workflow.',
    selector: '#onboarding-new-idea-btn',
    side: 'bottom',
    showControls: true,
    pointerPadding: 4,
    pointerRadius: 8,
    nextRoute: '/ideas',
  },
  // Step 4 — Idea Canvas DAG (tooltip, /ideas/[id]/idea-canvas)
  {
    icon: null,
    title: 'Idea Canvas',
    content:
      'Explore your idea as a decision tree. Click nodes to expand branches and find the best direction.',
    selector: '#onboarding-dag-canvas',
    side: 'right',
    showControls: true,
    pointerPadding: 4,
    pointerRadius: 8,
  },
  // Step 5 — Feasibility scorecards (tooltip)
  {
    icon: null,
    title: 'Feasibility Scorecards',
    content:
      'AI evaluates your idea across multiple dimensions. Review the plans and select the best fit.',
    selector: '#onboarding-feasibility-cards',
    side: 'top',
    showControls: true,
    pointerPadding: 4,
    pointerRadius: 8,
  },
  // Step 6 — Confirm plan button (tooltip)
  {
    icon: null,
    title: 'Confirm a Plan',
    content: 'Confirming a plan unlocks the Scope Freeze stage.',
    selector: '#onboarding-confirm-plan-btn',
    side: 'top',
    showControls: true,
    pointerPadding: 4,
    pointerRadius: 8,
  },
  // Step 7 — Scope board (tooltip)
  {
    icon: null,
    title: 'Scope Freeze',
    content: 'Drag features into IN or OUT scope to define clear boundaries for your product.',
    selector: '#onboarding-scope-board',
    side: 'top',
    showControls: true,
    pointerPadding: 4,
    pointerRadius: 8,
  },
  // Step 8 — Freeze button (overlay)
  {
    icon: null,
    title: 'Freeze the Scope',
    content: 'Once satisfied, freeze the scope. This triggers AI to generate your PRD.',
    selector: '#onboarding-freeze-btn',
    side: 'top',
    showControls: true,
    pointerPadding: 8,
    pointerRadius: 8,
  },
  // Step 9 — PRD content (tooltip)
  {
    icon: null,
    title: 'Your PRD',
    content:
      'The AI-generated PRD includes Requirements, Sections, and a Backlog. You can export it anytime.',
    selector: '#onboarding-prd-content',
    side: 'top',
    showControls: true,
    pointerPadding: 4,
    pointerRadius: 8,
  },
  // Step 10 — Help button (tooltip)
  {
    icon: null,
    title: "You're all set!",
    content: 'Click the ? button anytime to replay this tour.',
    selector: '#onboarding-help-btn',
    side: 'bottom',
    showControls: true,
    pointerPadding: 4,
    pointerRadius: 8,
  },
]

function OnboardingAutoStart() {
  const { shouldAutoStart, markCompleted } = useOnboarding()
  const { startOnborda, closeOnborda } = useOnborda()

  useEffect(() => {
    if (shouldAutoStart) {
      // Small delay to ensure DOM is ready after route settle
      const t = setTimeout(() => startOnborda(), 600)
      return () => clearTimeout(t)
    }
  }, [shouldAutoStart, startOnborda])

  // When tour closes (skip or done), mark completed
  useEffect(() => {
    return () => {
      markCompleted()
    }
  }, [markCompleted])

  return null
}

type OnboardingProviderProps = Readonly<{ children: React.ReactNode }>

export function OnboardingProvider({ children }: OnboardingProviderProps) {
  return (
    <OnbordaProviderBase>
      <Onborda steps={STEPS} cardComponent={OnboardingCard} shadowRgb="0,0,0" shadowOpacity="0.7">
        {children}
      </Onborda>
      <OnboardingAutoStart />
    </OnbordaProviderBase>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/components/onboarding/OnboardingProvider.tsx
git commit -m "feat(onboarding): add OnboardingProvider with 10-step tour config"
```

---

## Task 5: Wire OnboardingProvider into layout.tsx and add ? button to AppShell

**Files:**

- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/components/layout/AppShell.tsx`

**Step 1: Wrap layout with OnboardingProvider**

In `frontend/app/layout.tsx`, import `OnboardingProvider` and wrap `AppShell`:

```tsx
import { OnboardingProvider } from '../components/onboarding/OnboardingProvider'

// In RootLayout, change:
<AppShell>{children}</AppShell>
// to:
<OnboardingProvider>
  <AppShell>{children}</AppShell>
</OnboardingProvider>
```

**Step 2: Add `?` help button to AppShell header**

In `frontend/components/layout/AppShell.tsx`:

1. Add imports at the top:

```tsx
import { CircleHelp } from 'lucide-react'
import { useOnborda } from 'onborda'
import { useOnboarding } from '../onboarding/useOnboarding'
```

2. Inside `AppShell` function body, add:

```tsx
const { startOnborda } = useOnborda()
const { resetTour } = useOnboarding()

const handleStartTour = () => {
  resetTour()
  startOnborda()
}
```

3. In the header right section, add `?` button between `<NotificationBell />` and the grouped pill div:

```tsx
{
  /* Help / tour trigger */
}
;<button
  id="onboarding-help-btn"
  type="button"
  onClick={handleStartTour}
  aria-label="Start guided tour"
  title="Guided tour"
  className="border-[#1e1e1e]/12 relative flex h-8 w-8 items-center justify-center rounded-lg border bg-white text-[#1e1e1e]/45 transition hover:bg-[#f5f5f5] hover:text-[#1e1e1e]/80"
>
  <CircleHelp size={14} />
</button>
```

**Step 3: Commit**

```bash
git add frontend/app/layout.tsx frontend/components/layout/AppShell.tsx
git commit -m "feat(onboarding): wire OnboardingProvider into layout, add help button"
```

---

## Task 6: Add onboarding target IDs to Settings page

**Files:**

- Modify: `frontend/components/settings/AISettingsPage.tsx`

**Step 1: Add `id="onboarding-ai-provider"` to the AI provider config section**

Find the outermost container div of the providers list/form in `AISettingsPage.tsx` and add `id="onboarding-ai-provider"`. It should be the section that contains the provider cards/fields, e.g.:

```tsx
<div id="onboarding-ai-provider" className="...existing classes...">
  {/* existing provider content */}
</div>
```

**Step 2: Commit**

```bash
git add frontend/components/settings/AISettingsPage.tsx
git commit -m "feat(onboarding): add target ID to AI settings section"
```

---

## Task 7: Add onboarding target IDs to Ideas page

**Files:**

- Modify: `frontend/components/ideas/IdeasDashboard.tsx`

**Step 1: Read IdeasDashboard.tsx to find the ideas list and new-idea button**

Run: read the file and identify:

- The ideas list container → add `id="onboarding-ideas-list"`
- The "New Idea" / create button → add `id="onboarding-new-idea-btn"`

**Step 2: Add the IDs to respective elements**

```tsx
<div id="onboarding-ideas-list" className="...">
  {/* ideas list content */}
</div>

<button id="onboarding-new-idea-btn" ...>
  New Idea
</button>
```

**Step 3: Commit**

```bash
git add frontend/components/ideas/IdeasDashboard.tsx
git commit -m "feat(onboarding): add target IDs to Ideas dashboard"
```

---

## Task 8: Add onboarding target IDs to Idea Canvas page

**Files:**

- Modify: `frontend/components/idea/dag/IdeaDAGCanvas.tsx`

**Step 1: Read IdeaDAGCanvas.tsx and find the canvas container**

Add `id="onboarding-dag-canvas"` to the outermost canvas/SVG wrapper div.

**Step 2: Commit**

```bash
git add frontend/components/idea/dag/IdeaDAGCanvas.tsx
git commit -m "feat(onboarding): add target ID to DAG canvas"
```

---

## Task 9: Add onboarding target IDs to Feasibility page

**Files:**

- Modify: `frontend/components/feasibility/PlanCards.tsx`
- Modify: `frontend/components/feasibility/FeasibilityPage.tsx`

**Step 1: Read both files and identify:**

- Plan cards container → `id="onboarding-feasibility-cards"` on the cards grid
- Confirm plan button → `id="onboarding-confirm-plan-btn"` on the confirm/select button

**Step 2: Add IDs**

In `PlanCards.tsx` or `FeasibilityPage.tsx`, whichever contains the grid:

```tsx
<div id="onboarding-feasibility-cards" className="...">
```

On the confirm button:

```tsx
<button id="onboarding-confirm-plan-btn" ...>
```

**Step 3: Commit**

```bash
git add frontend/components/feasibility/PlanCards.tsx frontend/components/feasibility/FeasibilityPage.tsx
git commit -m "feat(onboarding): add target IDs to Feasibility page"
```

---

## Task 10: Add onboarding target IDs to Scope Freeze page

**Files:**

- Modify: `frontend/components/scope/ScopeBoard.tsx`
- Modify: `frontend/components/scope/ScopeFreezePage.tsx`

**Step 1: Read both files and identify:**

- Scope board → `id="onboarding-scope-board"` on the board container
- Freeze button → `id="onboarding-freeze-btn"` on the freeze/confirm button

**Step 2: Add IDs**

```tsx
<div id="onboarding-scope-board" className="...">
```

```tsx
<button id="onboarding-freeze-btn" ...>
```

**Step 3: Commit**

```bash
git add frontend/components/scope/ScopeBoard.tsx frontend/components/scope/ScopeFreezePage.tsx
git commit -m "feat(onboarding): add target IDs to Scope Freeze page"
```

---

## Task 11: Add onboarding target IDs to PRD page

**Files:**

- Modify: `frontend/components/prd/PrdView.tsx`

**Step 1: Read PrdView.tsx and identify the main content container**

Add `id="onboarding-prd-content"` to the main PRD content wrapper.

**Step 2: Commit**

```bash
git add frontend/components/prd/PrdView.tsx
git commit -m "feat(onboarding): add target ID to PRD content"
```

---

## Task 12: Manual smoke test

**Goal:** Verify the full tour works end-to-end.

**Step 1: Start the dev server**

```bash
npm run dev
```

**Step 2: Test checklist**

- [ ] Clear localStorage (`decisionos_tour_completed`) and log in → tour auto-starts
- [ ] Tour navigates from `/settings` → `/ideas` via `nextRoute`
- [ ] Custom card renders with `#b9eb10` accent, dark background
- [ ] Progress bar advances correctly
- [ ] Skip button sets `decisionos_tour_completed=true` and stops tour
- [ ] `?` button in header (next to notification bell) is visible
- [ ] Clicking `?` button restarts the tour from step 1
- [ ] Tour completes fully → `decisionos_tour_completed=true` written to localStorage
- [ ] Refreshing after completion → tour does NOT auto-start

**Step 3: Final commit (if any tweaks)**

```bash
git add -A
git commit -m "feat(onboarding): guided tour complete - smoke tested"
```

---

## Task 13: Create PR

```bash
git push -u origin feat/onboarding-tour
gh pr create --title "feat: add onboarding guided tour with Onborda" --body "$(cat <<'EOF'
## Summary
- Adds 10-step cross-page guided tour using Onborda
- Custom tooltip card matching DecisionOS design system (#b9eb10 / #1e1e1e)
- Auto-starts on first login (localStorage guard)
- ? help button in header (next to notification bell) for replay
- Mixed overlay/tooltip mode: overlay for key steps, tooltip for secondary

## Test plan
- [ ] Clear localStorage, login → tour auto-starts at /settings AI provider section
- [ ] Tour navigates across pages correctly
- [ ] Skip/Done sets localStorage flag
- [ ] ? button replays tour from beginning
- [ ] No layout shifts or z-index conflicts with existing header/nav

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```
