# Frontend UI/UX Improvement Plan for Hackathon

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Polish DecisionOS frontend for hackathon demo: unify visual identity, fix inconsistencies, integrate agent thought visualization, and add proactive agent UI components.

**Architecture:** Tailwind CSS theming with centralized design tokens. New components for agent visualization and notifications. Prioritized by demo impact.

**Tech Stack:** Next.js 14 + Tailwind CSS + Framer Motion + Lucide React icons.

**Current State:** App scores 6.2/10 overall. AppShell and PRD pages are polished (8/10). Scope Freeze and Feasibility pages are prototype-quality (3-4/10). Major color inconsistency: three different accent colors used across pages (#b9eb10, #22C55E, #06B6D4).

---

## Design System

```
Primary accent:  #b9eb10 (lime green - used in AppShell, keep as brand color)
Background:      #f5f5f5 (light gray, main)
Surface:         #ffffff (cards)
Text primary:    #1e1e1e
Text secondary:  #6b7280 (gray-500)
Text muted:      #9ca3af (gray-400)
Success:         #22c55e (green-500)
Error:           #ef4444 (red-500)
Warning:         #f59e0b (amber-500)
Border:          #e5e7eb (gray-200)

DAG Canvas (dark context):
  Background:    #0F172A (slate-900)
  Surface:       #1E293B (slate-800)
  Accent:        #b9eb10 (SAME lime green, not different green)
  Text:          #F8FAFC (slate-50)

Font: IBM Plex Sans (already configured)
```

---

### Task F1: Unify Accent Color Across All Pages

**Impact: HIGH (fixes the most visible inconsistency)**

**Files:**

- Modify: `frontend/app/globals.css` (add CSS variables)
- Modify: `frontend/components/idea/dag/IdeaDAGCanvas.tsx` (change #22C55E to accent)
- Modify: `frontend/components/idea/dag/NodeDetailPanel.tsx` (change green to accent)
- Modify: `frontend/components/feasibility/PlanCards.tsx` (change cyan to accent)
- Modify: `frontend/components/common/GuardPanel.tsx` (change cyan to accent)
- Modify: `frontend/components/scope/ScopeFreezePage.tsx` (change cyan to accent)

**Changes:**

1. Add CSS variables in globals.css under `:root`:
   ```css
   --accent: #b9eb10;
   --accent-dim: #b9eb1033;
   --accent-hover: #d4f542;
   --accent-text: #1e1e1e; /* dark text on lime background */
   ```
2. Replace all instances of `#22C55E` / `green-500` in DAG components with the lime accent
3. Replace all instances of `#06B6D4` / `cyan` in feasibility/guard/scope with lime accent
4. Ensure button primary style everywhere is: `bg-[var(--accent)] text-[var(--accent-text)]`

**Verification:** Visually check each page — every accent color should be the same lime green.

---

### Task F2: Fix Scope Freeze Page (3/10 -> 7/10)

**Impact: HIGH (currently worst-looking page in the demo flow)**

**Files:**

- Modify: `frontend/components/scope/ScopeFreezePage.tsx`
- Modify: `frontend/components/scope/ScopeBoard.tsx`
- Modify: `frontend/components/scope/ScopeItem.tsx`

**Changes:**

**ScopeFreezePage.tsx:**

- Replace `border border-black` buttons with themed styling:
  - Primary: `bg-[#b9eb10] text-[#1e1e1e] font-medium rounded-lg px-4 py-2 hover:bg-[#d4f542] transition-colors`
  - Secondary: `border border-gray-300 text-gray-700 rounded-lg px-4 py-2 hover:bg-gray-50 transition-colors`
- Add proper section headings with spacing
- Replace plain "Loading scope draft..." with a skeleton loader
- Fix error message contrast (use `text-red-600 bg-red-50 border border-red-200 rounded-lg p-3`)

**ScopeBoard.tsx:**

- Column headers: Add `text-sm font-semibold text-gray-700 uppercase tracking-wide` + icon
- Column containers: Add `bg-gray-50 rounded-xl p-4 min-h-[200px]`
- Input: Add `focus:ring-2 focus:ring-[#b9eb10] focus:border-[#b9eb10] rounded-lg border-gray-300`
- Add/Remove buttons: Use icon buttons with hover state
- Locked overlay: Keep blur but add a lock icon from Lucide

**ScopeItem.tsx:**

- Card: `bg-white rounded-lg border border-gray-200 px-3 py-2.5 shadow-sm hover:shadow-md transition-shadow cursor-grab`
- During drag: `shadow-lg ring-2 ring-[#b9eb10] opacity-90`
- Delete button: `text-gray-400 hover:text-red-500 transition-colors`
- Add drag handle icon from Lucide (GripVertical)

---

### Task F3: Fix Feasibility Page (4/10 -> 7/10)

**Impact: HIGH (second worst page)**

**Files:**

- Modify: `frontend/components/feasibility/FeasibilityPage.tsx`
- Modify: `frontend/components/feasibility/PlanCards.tsx`

**Changes:**

**FeasibilityPage.tsx:**

- Replace `border border-black` generate button with themed primary button
- Add a visual progress bar instead of text "Streaming 50%":
  ```
  <div className="w-full bg-gray-200 rounded-full h-2">
    <div className="bg-[#b9eb10] h-2 rounded-full transition-all" style={{ width: `${pct}%` }} />
  </div>
  ```
- Improve section spacing and add proper headings
- Add context summary card showing what we're analyzing (idea seed, confirmed path)

**PlanCards.tsx:**

- Change hover accent from cyan to lime: `hover:border-[#b9eb10]`
- Selected state: `border-[#b9eb10] bg-[#b9eb10]/5 shadow-lg`
- Score badges: Use consistent color coding (green for >7, amber for 5-7, red for <5)
- Add subtle entrance animation with Framer Motion `variants`
- Improve score readability (increase from text-xs to text-sm, add bar visualization)

---

### Task F4: Integrate Agent Thought Stream into Pages

**Impact: CRITICAL (this is the hackathon differentiator)**

**Files:**

- Create: `frontend/components/agent/AgentThoughtStream.tsx` (already planned in backend plan Task 10)
- Modify: `frontend/lib/sse.ts` (add onAgentThought handler)
- Modify: `frontend/components/feasibility/FeasibilityPage.tsx` (add thought stream)
- Modify: `frontend/components/prd/PrdView.tsx` (add thought stream)
- Modify: `frontend/app/ideas/[ideaId]/idea-canvas/page.tsx` (add thought stream for DAG generation)

**Changes:**

1. **SSE client** (`sse.ts`): Already in backend plan Task 10. Add `onAgentThought` and `onMemoryInsight` handlers.

2. **AgentThoughtStream component**: Already designed in backend plan Task 10. Key design specs:
   - Positioned as a collapsible panel at the bottom of generation areas
   - Dark background (`bg-zinc-900/95 backdrop-blur-sm`) for contrast against light pages
   - Animated entry of each thought line (Framer Motion `initial={{ opacity: 0, y: 10 }}`)
   - Agent icons from Lucide (Search, Lightbulb, FileText, Brain, Database, CheckCircle)
   - Pulsing green dot for active state
   - Color coding per agent role:
     - Researcher: blue-400
     - Generator: amber-400
     - Critic/Reviewer: orange-400
     - Memory Writer: green-400
     - Pattern Matcher: purple-400

3. **Integration pattern** (same for each page):

   ```tsx
   const { thoughts, addThought, reset } = useAgentThoughts()

   // In SSE call:
   streamPost(url, payload, {
     onAgentThought: addThought,
     onDone: (data) => { /* existing handler */ },
   })

   // In JSX:
   <AgentThoughtStream thoughts={thoughts} />
   ```

4. **Layout**: The thought stream appears BELOW the generation button area, ABOVE the results. It should feel like "peeking behind the curtain at the agents working."

---

### Task F5: Add Notification Bell to Header

**Impact: MEDIUM-HIGH (demonstrates proactive agent capability)**

**Files:**

- Create: `frontend/components/notifications/NotificationBell.tsx` (already in backend plan Task 11)
- Modify: `frontend/components/layout/AppShell.tsx` (add bell to header)

**Changes:**

1. **NotificationBell**: Already designed in backend plan Task 11. Additional design specs:
   - Position: Right side of AppShell header, next to settings icon
   - Badge: Red circle with count (animate-bounce on new notification)
   - Dropdown: Dark card with `bg-zinc-900 border-zinc-700 shadow-2xl rounded-xl`
   - Each notification card:
     - Type icon: Newspaper (news), Link (cross-idea), Brain (pattern)
     - Title in white, body in zinc-400
     - Dismiss button on hover only
     - Click to expand detail
   - Empty state: "No new notifications" with a subtle illustration

2. **AppShell integration**:
   - Add `<NotificationBell />` to the header right section
   - Ensure it's inside the auth-protected area
   - On mobile: Show as icon in hamburger menu

---

### Task F6: Add Cross-Idea Insights to Ideas Dashboard

**Impact: MEDIUM (shows "system intelligence" in the ideas list)**

**Files:**

- Create: `frontend/components/insights/CrossIdeaInsights.tsx` (already in backend plan Task 11)
- Modify: `frontend/components/ideas/IdeasDashboard.tsx` (add insights section)

**Changes:**

1. **CrossIdeaInsights**: Already designed in backend plan. Additional design specs:
   - Position: Above the ideas grid on the dashboard, collapsible
   - Card design: `bg-gradient-to-r from-[#b9eb10]/5 to-transparent border-l-4 border-[#b9eb10]`
   - Each insight card shows two idea names connected by a dotted line
   - Similarity percentage as a small badge
   - Analysis text in gray-600
   - "Run Analysis" button triggers the backend agent

2. **Dashboard integration**:
   - Add "Insights" section above the ideas grid
   - Show only if there are >= 2 ideas
   - "Run Analysis" triggers `/insights/cross-idea-analysis`
   - Results animate in with staggered delay

---

### Task F7: Add User Patterns to Settings Page

**Impact: MEDIUM (demonstrates "system learns about you")**

**Files:**

- Create: `frontend/components/insights/UserPatternCard.tsx` (already in backend plan Task 11)
- Modify: `frontend/components/settings/AISettingsPage.tsx` (add patterns section)

**Changes:**

1. **UserPatternCard**: Already designed in backend plan. Additional design specs:
   - Position: Below the AI provider settings in the settings page
   - Card design: Section with header "What the system has learned about you"
   - Each pattern as a key-value row with:
     - Key: `text-[#b9eb10] font-medium` (lime accent)
     - Value: `text-gray-600`
   - "Refresh Analysis" button to re-run pattern learning
   - If no patterns: "Create more ideas to help the system learn your preferences"

2. **Settings integration**: Add as a new section after the provider cards.

---

### Task F8: Ideas Dashboard Polish

**Impact: MEDIUM (first thing user sees after login)**

**Files:**

- Modify: `frontend/components/ideas/IdeasDashboard.tsx`

**Changes:**

- Improve card hover: Add `hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200`
- Add skeleton loader (3 placeholder cards with `animate-pulse bg-gray-200 rounded-lg`)
- Improve empty state: Add Lucide `Lightbulb` icon, larger text, lime CTA button
- Add stage badges with color coding:
  - idea_canvas: gray badge
  - feasibility: blue badge
  - scope_freeze: amber badge
  - prd: green badge
- "Create idea" button: Use primary lime styling

---

### Task F9: Loading States and Transitions

**Impact: LOW-MEDIUM (polish detail)**

**Files:**

- Modify: Multiple page components

**Changes:**

- Replace all "Loading..." text with skeleton loaders
- Add Framer Motion `layout` animations for list item reordering
- Add `transition-colors duration-200` to all interactive elements
- Ensure all buttons have `cursor-pointer` class
- Add `disabled:opacity-50 disabled:cursor-not-allowed` to all disabled buttons

---

## Priority Execution Order

```
F1 (accent unify) ──→ F2 (scope fix) ──→ F3 (feasibility fix)
                                              |
F4 (agent thoughts) ←────────────────────────┘
  |
  ├──→ F5 (notification bell)
  └──→ F6 (cross-idea insights)
         |
         └──→ F7 (user patterns) ──→ F8 (dashboard polish) ──→ F9 (loading states)
```

**Critical path for demo:** F1 → F4 → F5 (accent fix + agent thoughts + notifications)

**If time is short, cut:** F8 and F9 (polish that doesn't affect demo narrative)
