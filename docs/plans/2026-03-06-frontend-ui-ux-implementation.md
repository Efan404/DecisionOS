# Frontend UI/UX + Responsive Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Polish DecisionOS frontend for hackathon demo: unify visual identity, add agent thought visualization, notification bell, cross-idea insights, user pattern display, polish Scope/Feasibility pages, then apply full mobile-first responsive layout (320px+).

**Design Doc:** `docs/plans/2026-03-06-frontend-ui-ux-improvement.md`

**Tech Stack:** Next.js 14, React 18, TypeScript, Tailwind CSS, Lucide React icons.

**Branch:** `develop` (current)

**Execution order:** T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10 → T11 → T12 → T13 → R1 → R2 → R3 → R4

---

## Design System Reference

```
Primary accent:   #b9eb10   (lime green — brand color, replaces ALL cyan/#22C55E)
accent-hover:     #d4f542
accent-dim:       rgba(185,235,16,0.12)
Background:       #f5f5f5
Surface:          #ffffff
Text primary:     #1e1e1e
Text secondary:   #1e1e1e/50
Border:           #1e1e1e/10

DAG canvas (dark):
  bg: #0F172A   surface: #1E293B   text: #F8FAFC
  accent: #b9eb10  (same lime, replaces #22C55E in DAG)

Breakpoints (Tailwind):
  sm: 640px   md: 768px   lg: 1024px   xl: 1280px
```

---

## P0 — Foundation

### Task T1: F1 — Unify accent color across all components

**Files:**

- `frontend/components/feasibility/PlanCards.tsx`
- `frontend/components/common/GuardPanel.tsx`
- `frontend/components/idea/dag/NodeDetailPanel.tsx`
- `frontend/components/idea/dag/DAGNode.tsx`
- `frontend/components/idea/dag/DAGEdge.tsx`
- `frontend/components/idea/dag/ExpansionPatternPicker.tsx`
- `frontend/components/scope/ScopeFreezePage.tsx`
- `frontend/components/home/EntryCards.tsx`

**PlanCards.tsx** — replace all `cyan` with lime:

- `hover:border-cyan-400/60` → `hover:border-[#b9eb10]/60`
- `focus-visible:ring-cyan-500` → `focus-visible:ring-[#b9eb10]`
- `group-hover:border-cyan-200 group-hover:bg-cyan-50 group-hover:text-cyan-700` → `group-hover:border-[#b9eb10]/40 group-hover:bg-[#b9eb10]/8 group-hover:text-[#1e1e1e]`
- Selected state: `border-slate-900 bg-slate-900` → `border-[#b9eb10] bg-[#1e1e1e]`

**GuardPanel.tsx** — replace cyan hover:

- `hover:border-cyan-500 hover:bg-cyan-50 hover:text-cyan-800 focus-visible:ring-cyan-500` → `hover:border-[#b9eb10] hover:bg-[#b9eb10]/10 hover:text-[#1e1e1e] focus-visible:ring-[#b9eb10]`

**NodeDetailPanel.tsx** — replace `#22C55E`:

- All `#22C55E` → `#b9eb10`
- `#16A34A` (hover green) → `#d4f542`
- Text on lime bg: ensure `text-[#1e1e1e]` (dark text, lime is light)

**DAGNode.tsx** — replace `#22C55E`:

- `border-[#22C55E]` → `border-[#b9eb10]`
- `shadow-[0_0_16px_rgba(34,197,94,0.4)]` → `shadow-[0_0_16px_rgba(185,235,16,0.4)]`
- `bg-[#22C55E]/10` → `bg-[#b9eb10]/10`

**DAGEdge.tsx** — replace `#22C55E`:

- `stroke: isHighlighted ? '#22C55E'` → `stroke: isHighlighted ? '#b9eb10'`

**ExpansionPatternPicker.tsx** — replace `#22C55E`:

- `hover:border-[#22C55E] hover:bg-[#22C55E]/5` → `hover:border-[#b9eb10] hover:bg-[#b9eb10]/8`

**ScopeFreezePage.tsx** — replace `cyan-600`:

- `border-cyan-600 bg-cyan-600 text-white` → `bg-[#b9eb10] border-[#b9eb10] text-[#1e1e1e]`

**EntryCards.tsx** — replace cyan:

- Same pattern as PlanCards/GuardPanel

**Verify:**

```bash
grep -rn "cyan\|#22C55E\|#16A34A" frontend/components/ --include="*.tsx" | grep -v "PrdBacklogPanel\|PrdFeedbackCard"
```

Expected: 0 results.

**Commit:**

```bash
git add frontend/components/
git commit -m "fix(ui): unify accent color to #b9eb10, remove all cyan/#22C55E references"
```

---

## P1 — New Feature Components

### Task T2: F4-a — Backend SSE agent_thought events

**Files:**

- `backend/app/routes/idea_agents.py`
- `backend/app/routes/idea_dag.py`

**Step 1: Add helper in idea_agents.py**

After the existing `_sse_event` helper, add:

```python
def _sse_agent_thought(agent: str, thought: str) -> str:
    return _sse_event("agent_thought", {"agent": agent, "thought": thought})
```

**Step 2: Emit thoughts in stream_prd generator**

Inside the `stream_prd` async generator, before the LLM call:

```python
yield _sse_agent_thought("Architect", "Reading confirmed scope baseline and path context...")
yield _sse_agent_thought("Generator", "Drafting product requirements document structure...")
```

After the LLM call completes:

```python
yield _sse_agent_thought("Reviewer", "PRD generation complete. Validating output...")
```

**Step 3: Emit thoughts in feasibility stream (idea_dag.py)**

Find the feasibility generation endpoint/generator and add similar helper + emit calls:

```python
def _sse_agent_thought(agent: str, thought: str) -> str:
    return _sse_event("agent_thought", {"agent": agent, "thought": thought})

# Before parallel plan generation:
yield _sse_agent_thought("Researcher", "Analyzing confirmed idea path and node context...")
yield _sse_agent_thought("Generator", "Generating feasibility plans in parallel...")
# After generation:
yield _sse_agent_thought("Critic", "Scoring plans on technical feasibility, market viability, execution risk...")
```

**Verify:** Run backend and curl a feasibility/PRD stream — check for `event: agent_thought` lines in the SSE output.

**Commit:**

```bash
git add backend/app/routes/idea_agents.py backend/app/routes/idea_dag.py
git commit -m "feat(sse): emit agent_thought events during PRD and feasibility generation"
```

---

### Task T3: F4-b — AgentThoughtStream component + SSE handler

**Files:**

- Create: `frontend/components/agent/AgentThoughtStream.tsx`
- Modify: `frontend/lib/sse.ts`

**Step 1: Add onAgentThought to StreamPostHandlers in sse.ts**

Add to the `StreamPostHandlers` type:

```typescript
onAgentThought?: (data: { agent: string; thought: string }) => void
```

Add handler in the event loop after `onPartial` handling:

```typescript
if (parsed.event === 'agent_thought') {
  handlers.onAgentThought?.(parsed.data as { agent: string; thought: string })
  continue
}
```

**Step 2: Create AgentThoughtStream.tsx**

```tsx
'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

export type AgentThought = {
  agent: string
  thought: string
  timestamp: number
}

const AGENT_COLORS: Record<string, string> = {
  Researcher: 'text-blue-400',
  Generator: 'text-[#b9eb10]',
  Critic: 'text-orange-400',
  Reviewer: 'text-orange-400',
  Architect: 'text-purple-400',
  'Memory Writer': 'text-green-400',
  'Pattern Matcher': 'text-pink-400',
}

const getAgentColor = (agent: string) => AGENT_COLORS[agent] ?? 'text-zinc-400'

type Props = {
  thoughts: AgentThought[]
  isActive?: boolean
}

export function AgentThoughtStream({ thoughts, isActive = false }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [thoughts.length])

  if (thoughts.length === 0 && !isActive) return null

  return (
    <div className="rounded-xl border border-zinc-700/50 bg-zinc-900/95 p-4 backdrop-blur-sm">
      <div className="mb-2 flex items-center gap-2">
        {isActive && (
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#b9eb10] opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[#b9eb10]" />
          </span>
        )}
        <span className="text-xs font-medium tracking-wide text-zinc-400 uppercase">
          Agent Activity
        </span>
      </div>
      <div className="max-h-36 space-y-1.5 overflow-y-auto">
        {thoughts.map((t, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className={`shrink-0 font-medium ${getAgentColor(t.agent)}`}>{t.agent}</span>
            <span className="text-zinc-400">{t.thought}</span>
          </div>
        ))}
        {isActive && thoughts.length === 0 && (
          <p className="text-xs text-zinc-500">Initializing agents...</p>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

export function useAgentThoughts() {
  const [thoughts, setThoughts] = useState<AgentThought[]>([])

  const addThought = useCallback((data: { agent: string; thought: string }) => {
    setThoughts((prev) => [...prev, { ...data, timestamp: Date.now() }])
  }, [])

  const reset = useCallback(() => setThoughts([]), [])

  return { thoughts, addThought, reset }
}
```

**Verify:** `cd frontend && npx tsc --noEmit` — no errors.

**Commit:**

```bash
git add frontend/components/agent/AgentThoughtStream.tsx frontend/lib/sse.ts
git commit -m "feat(ui): add AgentThoughtStream component and onAgentThought SSE handler"
```

---

### Task T4: F4-c — Integrate AgentThoughtStream into pages

**Files:**

- `frontend/components/feasibility/FeasibilityPage.tsx`
- `frontend/components/prd/PrdView.tsx`

**Pattern (same for both pages):**

1. Add imports:

   ```tsx
   import { AgentThoughtStream, useAgentThoughts } from '../../components/agent/AgentThoughtStream'
   ```

   (adjust relative path as needed)

2. Add hook inside component:

   ```tsx
   const { thoughts, addThought, reset } = useAgentThoughts()
   ```

3. Before calling `streamPost`, call `reset()`.

4. Add `onAgentThought: addThought` to the `streamPost` handlers object.

5. Render the component:
   - **FeasibilityPage:** between the generate button row and `<PlanCards>`
   - **PrdView:** between the generate button and the markdown output area
   ```tsx
   <AgentThoughtStream thoughts={thoughts} isActive={loading} />
   ```

**Verify:** Trigger a feasibility generation — thought panel appears and updates live.

**Commit:**

```bash
git add frontend/components/feasibility/FeasibilityPage.tsx frontend/components/prd/PrdView.tsx
git commit -m "feat(ui): integrate AgentThoughtStream into FeasibilityPage and PrdView"
```

---

### Task T5: F5 — NotificationBell component

**Files:**

- Create: `frontend/components/notifications/NotificationBell.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/layout/AppShell.tsx`

**Step 1: Add API functions to api.ts**

```typescript
// ── Notifications ────────────────────────────────────────────────────────────

export type AppNotification = {
  id: string
  type: string
  title: string
  body: string
  metadata: Record<string, unknown>
  read_at: string | null
  created_at: string
}

export const getNotifications = async (unreadOnly = false): Promise<AppNotification[]> => {
  const url = buildApiUrl(`/notifications${unreadOnly ? '?unread_only=true' : ''}`)
  const response = await fetch(url, { headers: withAuthHeaders() })
  if (!response.ok)
    throw new ApiError(response.status, 'NOTIF_FETCH_FAILED', 'Failed to fetch notifications')
  const data = (await response.json()) as { notifications: AppNotification[] }
  return data.notifications
}

export const dismissNotification = async (notificationId: string): Promise<void> => {
  const response = await fetch(buildApiUrl(`/notifications/${notificationId}/dismiss`), {
    method: 'POST',
    headers: withAuthHeaders(),
  })
  if (!response.ok)
    throw new ApiError(response.status, 'NOTIF_DISMISS_FAILED', 'Failed to dismiss notification')
}
```

**Step 2: Create NotificationBell.tsx**

```tsx
'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell } from 'lucide-react'
import { dismissNotification, getNotifications, type AppNotification } from '../../lib/api'

const TYPE_ICONS: Record<string, string> = {
  news_match: '📰',
  cross_idea_insight: '🔗',
  pattern_learned: '🧠',
}

export function NotificationBell() {
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await getNotifications(true)
      setNotifications(data)
    } catch {
      // bell is non-critical, fail silently
    }
  }, [])

  useEffect(() => {
    void fetchNotifications()
    const interval = setInterval(() => void fetchNotifications(), 30_000)
    return () => clearInterval(interval)
  }, [fetchNotifications])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleDismiss = async (id: string) => {
    await dismissNotification(id)
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }

  const unreadCount = notifications.length

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-8 w-8 items-center justify-center rounded-lg border border-[#1e1e1e]/12 bg-white transition hover:bg-[#f5f5f5]"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      >
        <Bell className="h-4 w-4 text-[#1e1e1e]/60" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 flex h-4 w-4 animate-bounce items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute top-10 right-0 z-50 w-80 rounded-xl border border-zinc-700 bg-zinc-900 shadow-2xl">
          <div className="border-b border-zinc-700 px-4 py-3">
            <p className="text-sm font-semibold text-white">Notifications</p>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-zinc-500">No new notifications</p>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className="group flex items-start gap-3 border-b border-zinc-800 px-4 py-3 last:border-0"
                >
                  <span className="mt-0.5 shrink-0 text-base">{TYPE_ICONS[n.type] ?? '🔔'}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-white">{n.title}</p>
                    <p className="mt-0.5 line-clamp-2 text-xs text-zinc-400">{n.body}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDismiss(n.id)}
                    className="shrink-0 text-zinc-600 opacity-0 transition group-hover:opacity-100 hover:text-zinc-300"
                    aria-label="Dismiss"
                  >
                    ✕
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
```

**Step 3: Add to AppShell header**

In `AppShell.tsx`, import `NotificationBell` and add before the Settings link in the right-side actions div:

```tsx
import { NotificationBell } from '../notifications/NotificationBell'

// In the right-side actions div, before the Settings Link:
;<NotificationBell />
```

**Verify:** Bell icon appears in header, dropdown shows on click, badge shows for unread.

**Commit:**

```bash
git add frontend/components/notifications/NotificationBell.tsx frontend/lib/api.ts frontend/components/layout/AppShell.tsx
git commit -m "feat(ui): add NotificationBell with 30s polling and dismiss support"
```

---

### Task T6: F6 — CrossIdeaInsights component + IdeasDashboard

**Files:**

- Create: `frontend/components/insights/CrossIdeaInsights.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/ideas/IdeasDashboard.tsx`

**Step 1: Add API function to api.ts**

```typescript
// ── Insights ──────────────────────────────────────────────────────────────────

export type CrossIdeaInsight = {
  idea_a_id: string
  idea_b_id: string
  similarity_score?: number
  analysis: string
}

export const triggerCrossIdeaAnalysis = async (): Promise<{
  insights: CrossIdeaInsight[]
  agent_thoughts: { agent: string; thought: string }[]
}> => {
  const response = await fetch(buildApiUrl('/insights/cross-idea-analysis'), {
    method: 'POST',
    headers: withAuthHeaders(),
  })
  if (!response.ok)
    throw new ApiError(response.status, 'INSIGHTS_FAILED', 'Failed to run cross-idea analysis')
  return response.json()
}
```

**Step 2: Create CrossIdeaInsights.tsx**

```tsx
'use client'

import { useState } from 'react'
import { triggerCrossIdeaAnalysis, type CrossIdeaInsight } from '../../lib/api'

type Props = { ideaCount: number }

export function CrossIdeaInsights({ ideaCount }: Props) {
  const [insights, setInsights] = useState<CrossIdeaInsight[]>([])
  const [loading, setLoading] = useState(false)
  const [ran, setRan] = useState(false)

  if (ideaCount < 2) return null

  const handleRun = async () => {
    setLoading(true)
    try {
      const result = await triggerCrossIdeaAnalysis()
      setInsights(result.insights)
      setRan(true)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mb-5 rounded-xl border-l-4 border-[#b9eb10] bg-gradient-to-r from-[#b9eb10]/5 to-transparent p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-[#1e1e1e]">🧠 System Insights</p>
          <p className="mt-0.5 text-xs text-[#1e1e1e]/50">Cross-idea pattern analysis</p>
        </div>
        <button
          type="button"
          onClick={() => void handleRun()}
          disabled={loading}
          className="shrink-0 rounded-lg bg-[#b9eb10] px-3 py-1.5 text-xs font-bold text-[#1e1e1e] transition hover:bg-[#d4f542] disabled:opacity-50"
        >
          {loading ? 'Analyzing...' : 'Run Analysis'}
        </button>
      </div>

      {ran && insights.length === 0 && !loading && (
        <p className="mt-3 text-xs text-[#1e1e1e]/40">No significant connections found yet.</p>
      )}

      {insights.length > 0 && (
        <div className="mt-3 space-y-2">
          {insights.map((insight, i) => (
            <div key={i} className="rounded-lg border border-[#1e1e1e]/8 bg-white p-3">
              <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-[#1e1e1e]/70">
                <span className="rounded bg-[#b9eb10]/20 px-1.5 py-0.5 text-[#1e1e1e]">
                  {insight.idea_a_id.slice(0, 8)}
                </span>
                <span className="text-[#1e1e1e]/30">↔</span>
                <span className="rounded bg-[#b9eb10]/20 px-1.5 py-0.5 text-[#1e1e1e]">
                  {insight.idea_b_id.slice(0, 8)}
                </span>
                {insight.similarity_score != null && (
                  <span className="ml-auto text-[#1e1e1e]/40">
                    {Math.round(insight.similarity_score * 100)}% similar
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-xs text-[#1e1e1e]/60">{insight.analysis}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

**Step 3: Add to IdeasDashboard**

In `IdeasDashboard.tsx`, import and render above the ideas grid:

```tsx
import { CrossIdeaInsights } from '../insights/CrossIdeaInsights'

// Above the grid div:
;<CrossIdeaInsights ideaCount={ideas.length} />
```

**Commit:**

```bash
git add frontend/components/insights/CrossIdeaInsights.tsx frontend/lib/api.ts frontend/components/ideas/IdeasDashboard.tsx
git commit -m "feat(ui): add CrossIdeaInsights panel to IdeasDashboard"
```

---

### Task T7: F7 — UserPatternCard + AISettingsPage

**Files:**

- Create: `frontend/components/insights/UserPatternCard.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/settings/AISettingsPage.tsx`

**Step 1: Add API function to api.ts**

```typescript
export const getUserPatterns = async (): Promise<Record<string, string>> => {
  const response = await fetch(buildApiUrl('/insights/user-patterns'), {
    headers: withAuthHeaders(),
  })
  if (!response.ok)
    throw new ApiError(response.status, 'PATTERNS_FAILED', 'Failed to fetch user patterns')
  const data = (await response.json()) as { preferences: Record<string, string> }
  return data.preferences
}
```

**Step 2: Create UserPatternCard.tsx**

```tsx
'use client'

import { useEffect, useState } from 'react'
import { getUserPatterns } from '../../lib/api'

export function UserPatternCard() {
  const [patterns, setPatterns] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)

  const fetchPatterns = async () => {
    setLoading(true)
    try {
      const data = await getUserPatterns()
      setPatterns(data)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchPatterns()
  }, [])

  const entries = Object.entries(patterns)

  return (
    <div className="rounded-xl border border-[#1e1e1e]/10 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[#1e1e1e]">
            What the system has learned about you
          </h2>
          <p className="mt-0.5 text-xs text-[#1e1e1e]/40">
            Based on your decision patterns across ideas
          </p>
        </div>
        <button
          type="button"
          onClick={() => void fetchPatterns()}
          disabled={loading}
          className="rounded-lg border border-[#1e1e1e]/15 px-3 py-1.5 text-xs font-medium text-[#1e1e1e]/60 transition hover:bg-[#f5f5f5] disabled:opacity-50"
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {entries.length === 0 && !loading && (
        <p className="mt-4 text-xs text-[#1e1e1e]/35">
          Create more ideas and complete flows to help the system learn your preferences.
        </p>
      )}

      {entries.length > 0 && (
        <div className="mt-4 space-y-2">
          {entries.map(([key, value]) => (
            <div key={key} className="flex items-start gap-3 rounded-lg bg-[#f5f5f5] px-3 py-2">
              <span className="text-xs font-semibold text-[#7ab800]">{key}</span>
              <span className="text-xs text-[#1e1e1e]/60">{String(value)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

**Step 3: Add to AISettingsPage**

Read `AISettingsPage.tsx` first to find the insertion point (after the last provider card section), then add:

```tsx
import { UserPatternCard } from '../insights/UserPatternCard'

// After the last provider settings section:
;<UserPatternCard />
```

**Commit:**

```bash
git add frontend/components/insights/UserPatternCard.tsx frontend/lib/api.ts frontend/components/settings/AISettingsPage.tsx
git commit -m "feat(ui): add UserPatternCard to AISettingsPage showing learned preferences"
```

---

## P2 — Page UI Upgrades

### Task T8: F2-a — ScopeItem + ScopeColumn visual upgrade

**Files:**

- `frontend/components/scope/ScopeItem.tsx`
- `frontend/components/scope/ScopeColumn.tsx`

**ScopeItem.tsx — full redesign:**

Read the file, then replace the JSX:

- Card wrapper: `bg-white rounded-lg border border-[#1e1e1e]/10 px-3 py-2.5 shadow-sm hover:shadow-md transition-shadow`
- Content text: `text-sm text-[#1e1e1e]/85`
- Controls row: `mt-2 flex items-center gap-1.5`
- Up/Down buttons (use ChevronUp/ChevronDown from lucide-react):

  ```tsx
  import { ChevronUp, ChevronDown, Trash2 } from 'lucide-react'

  ;<button
    type="button"
    disabled={readonly || disableMoveUp}
    onClick={() => onMove(item.id, 'up')}
    className="flex h-6 w-6 items-center justify-center rounded border border-[#1e1e1e]/15 text-[#1e1e1e]/50 transition hover:bg-[#f5f5f5] hover:text-[#1e1e1e] disabled:cursor-not-allowed disabled:opacity-30"
    aria-label="Move up"
  >
    <ChevronUp className="h-3 w-3" />
  </button>
  ```

- Delete button: `ml-auto flex h-6 w-6 items-center justify-center rounded text-[#1e1e1e]/30 transition hover:bg-red-50 hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-30`

**ScopeColumn.tsx — read file first, then:**

- Column header: add `text-xs font-semibold text-[#1e1e1e]/50 uppercase tracking-widest` + lane icon (CheckCircle2 for IN, XCircle for OUT)
- Column container: `bg-[#f5f5f5] rounded-xl p-3 min-h-[160px]`
- Add item input: `focus:ring-2 focus:ring-[#b9eb10]/40 focus:border-[#b9eb10] rounded-lg border border-[#1e1e1e]/12 text-sm`
- Add item button: `bg-[#b9eb10] text-[#1e1e1e] font-bold hover:bg-[#d4f542] transition`

**Commit:**

```bash
git add frontend/components/scope/ScopeItem.tsx frontend/components/scope/ScopeColumn.tsx
git commit -m "fix(ui): redesign ScopeItem and ScopeColumn with polished visual style"
```

---

### Task T9: F2-b — ScopeBoard + ScopeFreezePage buttons/loading/error

**Files:**

- `frontend/components/scope/ScopeBoard.tsx`
- `frontend/components/scope/ScopeFreezePage.tsx`

**ScopeBoard.tsx — locked overlay:**
Replace the current `border-black/20` overlay content with:

```tsx
<div className="flex items-center gap-2 rounded-xl border border-[#1e1e1e]/15 bg-white/80 px-4 py-2 text-sm font-medium text-[#1e1e1e]/60 backdrop-blur-sm">
  <LockIcon className="h-4 w-4" />
  Scope Locked
</div>
```

Import `Lock` from `lucide-react`.

**ScopeFreezePage.tsx — read the full file, then apply:**

- All primary action buttons (freeze/continue to PRD):
  `bg-[#b9eb10] text-[#1e1e1e] font-bold rounded-xl px-4 py-2 hover:bg-[#d4f542] transition disabled:opacity-50 disabled:cursor-not-allowed`

- All secondary buttons (edit/cancel/new draft):
  `border border-[#1e1e1e]/15 text-[#1e1e1e]/70 rounded-xl px-4 py-2 hover:bg-[#f5f5f5] transition disabled:opacity-50`

- Loading state — replace text with skeleton:

  ```tsx
  <div className="animate-pulse space-y-3 p-6">
    <div className="h-4 w-1/3 rounded bg-[#1e1e1e]/10" />
    <div className="h-32 rounded-xl bg-[#1e1e1e]/6" />
  </div>
  ```

- Error message: `text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm`

**Commit:**

```bash
git add frontend/components/scope/ScopeBoard.tsx frontend/components/scope/ScopeFreezePage.tsx
git commit -m "fix(ui): polish ScopeBoard locked overlay and ScopeFreezePage buttons/loading/errors"
```

---

### Task T10: F3-a — FeasibilityPage button/progress bar/context card

**File:** `frontend/components/feasibility/FeasibilityPage.tsx`

Read the full file first, then:

**Generate button** — replace `border border-black` with:
`bg-[#b9eb10] text-[#1e1e1e] font-bold rounded-xl px-5 py-2.5 hover:bg-[#d4f542] transition disabled:opacity-50 disabled:cursor-not-allowed`

**Progress bar** — replace text "Streaming X%" with:

```tsx
{
  loading && (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs text-[#1e1e1e]/40">
        <span>Generating feasibility plans</span>
        <span>{progressPct}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-[#1e1e1e]/8">
        <div
          className="h-1.5 rounded-full bg-[#b9eb10] transition-all duration-500"
          style={{ width: `${progressPct}%` }}
        />
      </div>
    </div>
  )
}
```

**Context summary card** — add above generate button when `confirmedPathContext` is set:

```tsx
{
  confirmedPathContext && (
    <div className="rounded-xl border border-[#1e1e1e]/8 bg-white p-4">
      <p className="text-xs font-semibold tracking-wide text-[#1e1e1e]/40 uppercase">Analyzing</p>
      <p className="mt-1 text-sm font-medium text-[#1e1e1e]">{confirmedPathContext.idea_seed}</p>
      {confirmedPathContext.confirmed_path && (
        <p className="mt-0.5 text-xs text-[#1e1e1e]/50">
          {confirmedPathContext.confirmed_path.join(' → ')}
        </p>
      )}
    </div>
  )
}
```

Check the exact shape of `ConfirmedPathContext` in `schemas.ts` before using fields.

**Commit:**

```bash
git add frontend/components/feasibility/FeasibilityPage.tsx
git commit -m "fix(ui): add progress bar, context card, and themed button to FeasibilityPage"
```

---

### Task T11: F3-b — PlanCards score display + color coding

**File:** `frontend/components/feasibility/PlanCards.tsx`

Changes:

- Score badge (unselected): `group-hover:border-[#b9eb10]/40 group-hover:bg-[#b9eb10]/10 group-hover:text-[#1e1e1e]`
- Sub-scores section: upgrade from `text-xs` to `text-sm`, add color coding helper:
  ```tsx
  const scoreColor = (s: number) =>
    s >= 7 ? 'text-green-600' : s >= 5 ? 'text-amber-600' : 'text-red-500'
  ```
- Add score bar below each sub-score:
  ```tsx
  <div>
    <span className={`text-sm font-medium ${scoreColor(plan.scores.technical_feasibility)}`}>
      Tech: {plan.scores.technical_feasibility.toFixed(1)}
    </span>
    <div className="mt-0.5 h-1 w-full rounded-full bg-[#1e1e1e]/8">
      <div
        className="h-1 rounded-full bg-[#b9eb10]"
        style={{ width: `${plan.scores.technical_feasibility * 10}%` }}
      />
    </div>
  </div>
  ```
  Repeat for market and risk scores.

**Commit:**

```bash
git add frontend/components/feasibility/PlanCards.tsx
git commit -m "fix(ui): upgrade PlanCards with lime accent, score color coding and bar visualization"
```

---

## P3 — Polish

### Task T12: F8 — IdeasDashboard skeleton + empty state + stage badges

**File:** `frontend/components/ideas/IdeasDashboard.tsx`

**Skeleton loader** — replace `loading ? <p>Loading...</p>` with 3 card skeletons:

```tsx
{
  loading && ideas.length === 0 && (
    <div className="mt-5 grid gap-3 md:grid-cols-2">
      {[1, 2, 3].map((i) => (
        <div key={i} className="animate-pulse rounded-xl border border-[#1e1e1e]/8 bg-white p-4">
          <div className="h-4 w-2/3 rounded bg-[#1e1e1e]/8" />
          <div className="mt-2 h-3 w-1/3 rounded bg-[#1e1e1e]/6" />
          <div className="mt-4 h-7 w-20 rounded-lg bg-[#1e1e1e]/6" />
        </div>
      ))}
    </div>
  )
}
```

**Stage badges** — add inside each idea card after the title:

```tsx
const STAGE_BADGES: Record<string, { label: string; cls: string }> = {
  opportunity:  { label: 'Canvas',      cls: 'bg-gray-100 text-gray-600' },
  feasibility:  { label: 'Feasibility', cls: 'bg-blue-50 text-blue-600' },
  scope_freeze: { label: 'Scope',       cls: 'bg-amber-50 text-amber-600' },
  prd:          { label: 'PRD',         cls: 'bg-[#b9eb10]/20 text-[#5a7a00]' },
}

// In card JSX, after idea title:
<span className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${STAGE_BADGES[idea.stage]?.cls ?? 'bg-gray-100 text-gray-500'}`}>
  {STAGE_BADGES[idea.stage]?.label ?? idea.stage}
</span>
```

**Empty state** — replace the plain dashed div with:

```tsx
<div className="col-span-2 flex flex-col items-center rounded-xl border border-dashed border-[#1e1e1e]/15 py-12 text-center">
  <span className="text-3xl">💡</span>
  <p className="mt-3 text-sm font-medium text-[#1e1e1e]/60">No ideas yet</p>
  <p className="mt-1 text-xs text-[#1e1e1e]/35">Create your first idea using the form above</p>
</div>
```

**Card hover** — add `hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200` to non-active card article.

**Commit:**

```bash
git add frontend/components/ideas/IdeasDashboard.tsx
git commit -m "fix(ui): add skeleton loader, stage badges, improved empty state to IdeasDashboard"
```

---

### Task T13: F9 — Global loading/disabled/transition polish

**Files:** `PrdView.tsx`, `PrdPage.tsx`, `AISettingsPage.tsx`, `ProfilePage.tsx`

Read each file before editing. Apply these rules:

1. All buttons: add `disabled:opacity-50 disabled:cursor-not-allowed` if missing.
2. All interactive elements: ensure `transition-colors duration-200` or `transition-all duration-200`.
3. Page-level loading text → skeleton or inline spinner in button:
   ```tsx
   // Inline spinner for save/generate buttons:
   {
     saving ? (
       <span className="flex items-center gap-1.5">
         <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
           <circle
             className="opacity-25"
             cx="12"
             cy="12"
             r="10"
             stroke="currentColor"
             strokeWidth="4"
           />
           <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
         </svg>
         Saving…
       </span>
     ) : (
       'Save'
     )
   }
   ```

**Commit:**

```bash
git add frontend/components/
git commit -m "fix(ui): unify disabled states, transitions, and loading spinners globally"
```

---

## Responsive Layout (R-tasks — run after T1–T13)

> Mobile-first, 320px+. Breakpoints: sm=640px, md=768px, lg=1024px.

### Task R1: AppShell responsive overhaul

**File:** `frontend/components/layout/AppShell.tsx`

Read the full file first, then:

**Header:**

- Add `px-4 sm:px-6` padding to header container
- Logo subtitle text: `hidden sm:block`
- Right actions: on mobile show only bell + hamburger; hide Settings/Logout links (they move to mobile drawer)
  ```tsx
  <Link href="/settings" className="hidden sm:block rounded-lg ...">Settings</Link>
  <button onClick={logout} className="hidden sm:block rounded-lg ...">Logout</button>
  ```

**Step navigation:**

- Current desktop sidebar: wrap in `hidden md:flex md:flex-col`
- Add mobile horizontal scrollable strip:
  ```tsx
  <nav className="flex overflow-x-auto gap-1 border-b border-[#1e1e1e]/8 bg-white px-4 py-2 md:hidden">
    {steps.map((item) => (
      <Link
        key={item.step}
        href={...}
        className="shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium transition ..."
      >
        {item.label}
      </Link>
    ))}
  </nav>
  ```

**Mobile drawer** — expand the existing `mobileNavOpen` drawer to include Settings and Logout links.

**Commit:**

```bash
git add frontend/components/layout/AppShell.tsx
git commit -m "feat(responsive): mobile-first AppShell with horizontal step strip and full drawer nav"
```

---

### Task R2: DAG Canvas mobile degraded mode

**Files:**

- `frontend/components/idea/dag/IdeaDAGCanvas.tsx`
- `frontend/components/idea/dag/NodeDetailPanel.tsx`

Read both files first, then:

**IdeaDAGCanvas.tsx:**

1. Add SSR-safe mobile detection:

   ```tsx
   const [isMobile, setIsMobile] = useState(false)
   const [landscapeDismissed, setLandscapeDismissed] = useState(false)
   useEffect(() => {
     setIsMobile(window.innerWidth < 768)
   }, [])
   ```

2. Ensure ReactFlow props include `panOnDrag zoomOnScroll zoomOnPinch` (check if already set).

3. Add landscape hint banner (non-blocking, dismissible):
   ```tsx
   {
     isMobile && !landscapeDismissed && (
       <div className="absolute top-2 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-lg bg-[#1e1e1e]/80 px-4 py-2 text-xs text-white backdrop-blur-sm">
         <span>Rotate for best experience</span>
         <button
           onClick={() => setLandscapeDismissed(true)}
           className="text-white/60 hover:text-white"
         >
           ✕
         </button>
       </div>
     )
   }
   ```

**NodeDetailPanel.tsx:**

On mobile (pass `isMobile` prop or detect inside), render as bottom sheet instead of side panel:

- Desktop: existing side panel style
- Mobile: `fixed bottom-0 left-0 right-0 z-30 rounded-t-2xl bg-[#1E293B] shadow-2xl max-h-[70vh] overflow-y-auto`

Add a drag handle at top of mobile bottom sheet:

```tsx
{
  isMobile && <div className="mx-auto mt-2 mb-4 h-1 w-10 rounded-full bg-white/20" />
}
```

**Commit:**

```bash
git add frontend/components/idea/dag/IdeaDAGCanvas.tsx frontend/components/idea/dag/NodeDetailPanel.tsx
git commit -m "feat(responsive): DAG canvas landscape hint and NodeDetailPanel mobile bottom sheet"
```

---

### Task R3: Content pages responsive

**Files:**

- `frontend/components/ideas/IdeasDashboard.tsx`
- `frontend/components/feasibility/FeasibilityPage.tsx`
- `frontend/components/feasibility/PlanCards.tsx`
- `frontend/components/scope/ScopeFreezePage.tsx`
- `frontend/components/scope/ScopeBoard.tsx`
- `frontend/components/prd/PrdView.tsx`

Read each file, then apply:

**IdeasDashboard:** `main` gets `px-4 sm:px-6`. Form: already `flex-col sm:flex-row` — verify. Grid: already `md:grid-cols-2` — verify.

**FeasibilityPage:** Wrap content in `px-4 sm:px-6 max-w-5xl mx-auto`. Buttons row: `flex flex-col sm:flex-row gap-2`. Context card: full-width always.

**PlanCards:** Change `grid gap-4 md:grid-cols-3` → `grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`.

**ScopeFreezePage:** Header/action area: `flex flex-col sm:flex-row`. Buttons that are side-by-side: stack on mobile.

**ScopeBoard:** Grid: `grid-cols-1 md:grid-cols-2`. On mobile, columns stack.

**PrdView:** Tabs: `flex overflow-x-auto`. Content: `prose-sm sm:prose max-w-none px-4 sm:px-0`.

**Commit:**

```bash
git add frontend/components/
git commit -m "feat(responsive): mobile-first layout for content pages"
```

---

### Task R4: Profile, Settings, and utility pages responsive

**Files:**

- `frontend/components/profile/ProfilePage.tsx`
- `frontend/components/settings/AISettingsPage.tsx`
- `frontend/components/common/GuardPanel.tsx`
- `frontend/components/home/EntryCards.tsx`

Read each file, then apply:

**ProfilePage:** Already `max-w-2xl mx-auto px-6` — change to `px-4 sm:px-6`. Button rows: `flex justify-end` → `flex flex-col sm:flex-row sm:justify-end gap-2`.

**AISettingsPage:** Read file. Provider cards: ensure full-width on mobile. `px-4 sm:px-6`.

**GuardPanel:** `p-6` → `p-4 sm:p-6`. Button: `w-full sm:w-auto`.

**EntryCards:** Grid: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`.

**Commit:**

```bash
git add frontend/components/
git commit -m "feat(responsive): mobile-first layout for profile, settings, and utility pages"
```

---

## Summary

| Phase           | Tasks   | Commits |
| --------------- | ------- | ------- |
| P0 Foundation   | T1      | 1       |
| P1 New features | T2–T7   | 6       |
| P2 Page UI      | T8–T11  | 4       |
| P3 Polish       | T12–T13 | 2       |
| Responsive      | R1–R4   | 4       |
| **Total**       | **17**  | **17**  |

Each task is one commit, independently reviewable.
