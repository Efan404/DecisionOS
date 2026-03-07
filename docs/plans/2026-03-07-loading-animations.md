# Loading Animations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add text-based step animation to PRD generation, and progress bar animations to both PRD and Scope generation (Scope requires a new SSE backend endpoint).

**Architecture:**

- PRD: already has SSE with `progress.step` + `agent_thought` events — map `step` to human-readable labels and render as an animated step list above the empty state.
- Scope: currently calls `POST /ideas/{idea_id}/agents/scope` (synchronous REST) inside `hydrateDraftIfEmpty`. Add a new `POST /ideas/{idea_id}/agents/scope/stream` SSE endpoint that mirrors the feasibility stream pattern, then wire it into `ScopeFreezePage`.
- Shared UI: extract a `<GenerationProgress>` component used by both pages.

**Tech Stack:** FastAPI SSE (sse-starlette), LangGraph not needed (scope uses direct `llm.generate_scope`), Next.js/React, Tailwind CSS.

---

### Task 1: Create shared `<GenerationProgress>` component

**Files:**

- Create: `frontend/components/common/GenerationProgress.tsx`

This component accepts a list of steps with labels + status, a current text label, and renders:

1. A progress bar (indeterminate shimmer while loading, filled when done)
2. Completed steps as ticked lines
3. Current active step with pulsing dot + animated ellipsis

**Step 1: Create the component**

```tsx
// frontend/components/common/GenerationProgress.tsx
'use client'

type StepStatus = 'pending' | 'active' | 'done'

export type ProgressStep = {
  key: string
  label: string
  status: StepStatus
}

type Props = {
  steps: ProgressStep[]
  isActive: boolean
}

export function GenerationProgress({ steps, isActive }: Props) {
  const doneCount = steps.filter((s) => s.status === 'done').length
  const pct = steps.length > 0 ? Math.round((doneCount / steps.length) * 100) : 0

  return (
    <div className="rounded-xl border border-zinc-200 bg-white px-5 py-4 shadow-sm">
      {/* Progress bar */}
      <div className="mb-4 h-1 w-full overflow-hidden rounded-full bg-zinc-100">
        {isActive ? (
          <div
            className="h-full rounded-full bg-[#b9eb10] transition-all duration-700 ease-out"
            style={{ width: `${Math.max(4, pct)}%` }}
          />
        ) : (
          <div className="h-full w-full rounded-full bg-[#b9eb10]" />
        )}
      </div>

      {/* Step list */}
      <ul className="space-y-2">
        {steps.map((step) => (
          <li key={step.key} className="flex items-center gap-2.5 text-sm">
            {step.status === 'done' ? (
              <svg
                aria-hidden="true"
                className="h-4 w-4 shrink-0 text-[#b9eb10]"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M2.5 8.5l3.5 3.5 7-7" />
              </svg>
            ) : step.status === 'active' ? (
              <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
                <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-[#b9eb10] opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#b9eb10]" />
              </span>
            ) : (
              <span className="h-4 w-4 shrink-0 rounded-full border border-zinc-200" />
            )}
            <span
              className={
                step.status === 'done'
                  ? 'text-zinc-400 line-through'
                  : step.status === 'active'
                    ? 'font-medium text-zinc-800'
                    : 'text-zinc-400'
              }
            >
              {step.label}
              {step.status === 'active' && (
                <span className="ml-1 inline-flex gap-0.5">
                  <span className="animate-bounce" style={{ animationDelay: '0ms' }}>
                    .
                  </span>
                  <span className="animate-bounce" style={{ animationDelay: '150ms' }}>
                    .
                  </span>
                  <span className="animate-bounce" style={{ animationDelay: '300ms' }}>
                    .
                  </span>
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

**Step 2: Verify it renders (visual check — no automated test needed for pure UI)**

No test needed — this is a dumb display component wired up in tasks 2 and 3.

**Step 3: Commit**

```bash
git add frontend/components/common/GenerationProgress.tsx
git commit -m "feat(ui): add GenerationProgress step-list component"
```

---

### Task 2: Wire GenerationProgress into PRD page

The PRD SSE stream already emits `progress` events with a `step` field. Map those steps to human-readable labels and drive `GenerationProgress`.

**Files:**

- Modify: `frontend/components/prd/PrdPage.tsx:38-44` (add `progressStep` state)
- Modify: `frontend/components/prd/PrdPage.tsx:119-131` (handle `onProgress` in streamPost)
- Modify: `frontend/components/prd/PrdPage.tsx:256-278` (render GenerationProgress)

**Step 1: Define step config near the top of `PrdPage.tsx` (after imports)**

The backend emits these `step` values in order (from `idea_agents.py`):

```
validating → building_context → running_graph → requirements_done → backlog_done → saving
```

Add this constant after the imports:

```tsx
import { type ProgressStep, GenerationProgress } from '../common/GenerationProgress'

const PRD_STEPS: { key: string; label: string }[] = [
  { key: 'validating', label: 'Validating idea context' },
  { key: 'building_context', label: 'Building PRD context pack' },
  { key: 'running_graph', label: 'Starting AI agents' },
  { key: 'requirements_done', label: 'Requirements written' },
  { key: 'backlog_done', label: 'Backlog generated' },
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
```

**Step 2: Add state for current progress step in `PrdPage`**

In the state declarations section (around line 38):

```tsx
const [progressStep, setProgressStep] = useState<string | null>(null)
```

**Step 3: Wire `onProgress` inside the `streamPost` call (around line 119)**

The `onProgress` handler already exists as an empty slot. Fill it in:

```tsx
onProgress: (data) => {
  if (
    !cancelled &&
    typeof data === 'object' &&
    data !== null &&
    'step' in data
  ) {
    setProgressStep((data as { step: string }).step)
  }
},
```

Also reset `progressStep` when the stream starts, alongside `reset()`:

```tsx
setProgressStep(null)
```

**Step 4: Replace the loading section in the JSX (around line 258-262)**

Current code:

```tsx
{
  ;(loading || thoughts.length > 0) && (
    <div className="mx-auto w-full max-w-7xl px-6 pt-4">
      <AgentThoughtStream thoughts={thoughts} isActive={loading} />
    </div>
  )
}
```

Replace with:

```tsx
{
  loading && (
    <div className="mx-auto w-full max-w-4xl px-6 pt-4">
      <GenerationProgress steps={buildPrdProgressSteps(progressStep)} isActive={loading} />
    </div>
  )
}
{
  ;(thoughts.length > 0 || (loading && thoughts.length === 0)) && (
    <div className="mx-auto w-full max-w-7xl px-6 pt-3">
      <AgentThoughtStream thoughts={thoughts} isActive={loading} />
    </div>
  )
}
```

**Step 5: Reset `progressStep` in the `finally` block when loading ends**

After `setLoading(false)` in both the success and error paths, add:

```tsx
setProgressStep(null)
```

Actually — put it in the `finally` block alongside `setLoading(false)`:

```tsx
} finally {
  ...
  setLoading(false)
  setProgressStep(null)
}
```

Wait — `progressStep` should stay showing the last step briefly. Actually just reset it when loading becomes false is fine; the `GenerationProgress` won't show when `loading=false`.

**Step 6: Commit**

```bash
git add frontend/components/prd/PrdPage.tsx
git commit -m "feat(prd): add step-by-step progress animation during generation"
```

---

### Task 3: Backend — add `POST /ideas/{idea_id}/agents/scope/stream` SSE endpoint

The scope agent (`llm.generate_scope`) is synchronous. Wrap it in an SSE endpoint that:

1. Emits `progress` events with step + pct
2. Emits `agent_thought` events at key points
3. Calls `llm.generate_scope` in a thread pool
4. Returns `done` with `{ idea_id, idea_version, data: ScopeOutput }`

**Files:**

- Modify: `backend/app/routes/idea_agents.py` — add new route after existing `/scope` POST

**Step 1: Add the stream endpoint to `idea_agents.py`**

Find the existing `post_scope` handler (around line 137) and add after it:

```python
@router.post("/scope/stream")
async def stream_scope(idea_id: str, payload: ScopeIdeaRequest) -> EventSourceResponse:
    """SSE-streaming scope generation. Wraps synchronous llm.generate_scope in a thread pool."""
    _logger.info("agent.scope.stream.start idea_id=%s version=%s", idea_id, payload.version)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        yield _sse_event("progress", {"step": "received_request", "pct": 5})

        current = _repo.get_idea(idea_id)
        if current is None:
            yield _sse_event("error", {"code": "IDEA_NOT_FOUND", "message": "Idea not found"})
            return
        if current.version != payload.version:
            yield _sse_event("error", {
                "code": "IDEA_VERSION_CONFLICT",
                "message": f"Version conflict: expected {current.version}, got {payload.version}",
            })
            return

        yield _sse_agent_thought("Architect", "Analyzing confirmed path and feasibility plan...")
        yield _sse_event("progress", {"step": "analyzing_context", "pct": 15})

        loop = asyncio.get_running_loop()
        try:
            output: ScopeOutput = await loop.run_in_executor(
                None, llm.generate_scope, payload
            )
        except Exception as exc:
            _raise_if_no_provider(exc)
            _logger.exception("agent.scope.stream.failed idea_id=%s", idea_id)
            yield _sse_event("error", {"code": "SCOPE_GENERATION_FAILED", "message": str(exc)})
            return

        yield _sse_agent_thought("Architect", f"Generated {len(output.in_scope)} in-scope and {len(output.out_scope)} out-of-scope items")
        yield _sse_event("progress", {"step": "saving", "pct": 85})

        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            mutate_context=lambda context: _apply_scope(context, payload, output),
            allow_conflict_retry=True,
        )
        error_payload = _sse_error_payload(result)
        if error_payload is not None:
            _logger.warning(
                "agent.scope.stream.failed idea_id=%s version=%s code=%s",
                idea_id, payload.version, error_payload.get("code", "UNKNOWN_ERROR"),
            )
            yield _sse_event("error", error_payload)
            return

        assert result.idea is not None
        _logger.info("agent.scope.stream.done idea_id=%s idea_version=%s", idea_id, result.idea.version)
        yield _sse_event("progress", {"step": "done", "pct": 100})
        yield _sse_event("done", {
            "idea_id": idea_id,
            "idea_version": result.idea.version,
            "data": output.model_dump(),
        })

    return EventSourceResponse(event_generator())
```

**Step 2: Check what `_apply_scope` looks like — it should already exist in the file**

Search for `_apply_scope` in `idea_agents.py`. It's called by `post_scope` so it must exist. The stream endpoint reuses it identically.

**Step 3: Verify `ScopeOutput` is imported**

It's already imported at the top: `from app.schemas.scope import InScopeItem, OutScopeItem, ScopeOutput`

**Step 4: Run backend smoke test**

```bash
cd backend
DECISIONOS_CHROMA_PATH="" PYTHONPATH=. python -c "from app.routes.idea_agents import router; print('import ok')"
```

Expected: `import ok`

**Step 5: Commit**

```bash
git add backend/app/routes/idea_agents.py
git commit -m "feat(backend): add /agents/scope/stream SSE endpoint"
```

---

### Task 4: Frontend — add `streamScopeAgent` to `api.ts`

**Files:**

- Modify: `frontend/lib/api.ts` — add `streamScopeAgent` function near the `postIdeaScopedAgent` function

**Step 1: Find `postIdeaScopedAgent` in `api.ts`**

Grep for it — it's used in `ScopeFreezePage.tsx` line 173. The function wraps `jsonPost`. Add a streaming variant alongside it:

```ts
export const streamScopeAgent = async (
  ideaId: string,
  payload: ScopeInput & { version: number },
  handlers: Parameters<typeof streamPost>[2],
  signal?: AbortSignal
): Promise<void> => {
  return streamPost(`/ideas/${ideaId}/agents/scope/stream`, payload, handlers, signal)
}
```

You'll also need to import `ScopeInput` in `api.ts` — check whether it's already imported from `./schemas`. If not, add it.

**Step 2: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend/api): add streamScopeAgent for SSE scope generation"
```

---

### Task 5: Wire scope SSE + progress into `ScopeFreezePage`

The scope generation currently happens inside `hydrateDraftIfEmpty` via `postIdeaScopedAgent`. Replace that call with `streamScopeAgent`, and show `GenerationProgress` while it runs.

**Files:**

- Modify: `frontend/components/scope/ScopeFreezePage.tsx`

**Step 1: Add imports and state**

Add at top of file:

```tsx
import { streamScopeAgent } from '../../lib/api'
import { streamPost } from '../../lib/sse'
import { type ProgressStep, GenerationProgress } from '../common/GenerationProgress'
import { useAgentThoughts } from '../agent/AgentThoughtStream'
```

Add inside `ScopeFreezePage` component alongside existing state:

```tsx
const [scopeGenerating, setScopeGenerating] = useState(false)
const [scopeProgressStep, setScopeProgressStep] = useState<string | null>(null)
const {
  thoughts: scopeThoughts,
  addThought: addScopeThought,
  reset: resetScopeThoughts,
} = useAgentThoughts()
```

**Step 2: Define scope progress steps**

Add this constant at module level (outside the component):

```tsx
const SCOPE_STEPS: { key: string; label: string }[] = [
  { key: 'received_request', label: 'Receiving request' },
  { key: 'analyzing_context', label: 'Analyzing confirmed path' },
  { key: 'saving', label: 'Saving scope items' },
  { key: 'done', label: 'Scope generated' },
]

function buildScopeProgressSteps(currentStep: string | null): ProgressStep[] {
  const currentIndex = SCOPE_STEPS.findIndex((s) => s.key === currentStep)
  return SCOPE_STEPS.map((s, i) => ({
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
```

**Step 3: Replace `postIdeaScopedAgent` call in `hydrateDraftIfEmpty`**

The current code (around line 173 in `ScopeFreezePage.tsx`):

```tsx
const envelope = await postIdeaScopedAgent<ScopeInput & { version: number }, ScopeOutput>(
  ideaId,
  'scope',
  payload
)
sourceScope = envelope.data
workingVersion = envelope.idea_version
versionChanged = true
```

Replace with:

```tsx
setScopeGenerating(true)
setScopeProgressStep(null)
resetScopeThoughts()
let scopeDonePayload: { idea_id: string; idea_version: number; data: ScopeOutput } | null = null
try {
  await streamScopeAgent(ideaId, payload, {
    onProgress: (data) => {
      if (typeof data === 'object' && data !== null && 'step' in data) {
        setScopeProgressStep((data as { step: string }).step)
      }
    },
    onAgentThought: addScopeThought,
    onDone: (data) => {
      scopeDonePayload = data as { idea_id: string; idea_version: number; data: ScopeOutput }
    },
  })
} catch {
  // If SSE stream fails, fall back to the existing REST call
  const envelope = await postIdeaScopedAgent<ScopeInput & { version: number }, ScopeOutput>(
    ideaId,
    'scope',
    payload
  )
  sourceScope = envelope.data
  workingVersion = envelope.idea_version
  versionChanged = true
  setScopeGenerating(false)
  return { draft: currentDraft, version: workingVersion, versionChanged } // handled below
}
if (scopeDonePayload) {
  sourceScope = scopeDonePayload.data
  workingVersion = scopeDonePayload.idea_version
  versionChanged = true
}
setScopeGenerating(false)
setScopeProgressStep(null)
```

Note: `hydrateDraftIfEmpty` is a `useCallback`. The `setScopeGenerating`, `setScopeProgressStep`, `addScopeThought`, `resetScopeThoughts` setters need to be in its dependency array.

**Step 4: Render `GenerationProgress` in the JSX**

In the JSX return (around line 632 where the loading skeleton currently is):

Replace:

```tsx
{
  /* Loading skeleton */
}
{
  loading && !draft ? (
    <div className="mt-4 space-y-2">
      <div className="h-4 w-48 animate-pulse rounded-md bg-[#f0f0f0]" />
      <div className="h-4 w-32 animate-pulse rounded-md bg-[#f0f0f0]" />
    </div>
  ) : null
}
```

With:

```tsx
{
  /* Loading / generation progress */
}
{
  ;(loading && !draft) || scopeGenerating ? (
    <div className="mt-4">
      {scopeGenerating ? (
        <GenerationProgress
          steps={buildScopeProgressSteps(scopeProgressStep)}
          isActive={scopeGenerating}
        />
      ) : (
        <div className="space-y-2">
          <div className="h-4 w-48 animate-pulse rounded-md bg-[#f0f0f0]" />
          <div className="h-4 w-32 animate-pulse rounded-md bg-[#f0f0f0]" />
        </div>
      )}
    </div>
  ) : null
}
```

**Step 5: Commit**

```bash
git add frontend/components/scope/ScopeFreezePage.tsx
git commit -m "feat(scope): add SSE-driven progress animation during scope generation"
```

---

### Task 6: Verify end-to-end

**Step 1: Start backend**

```bash
cd backend
DECISIONOS_CHROMA_PATH="" PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

**Step 2: Start frontend**

```bash
cd frontend
npm run dev
```

**Step 3: Manual smoke test — PRD animation**

1. Navigate to an idea that has completed feasibility + scope freeze
2. Open PRD page
3. Verify: `GenerationProgress` renders with steps animating as SSE events arrive
4. Verify: after done, the progress component disappears and PRD content shows

**Step 4: Manual smoke test — Scope animation**

1. Navigate to an idea with no scope draft yet
2. Open Scope Freeze page
3. Verify: `GenerationProgress` shows during the `scope/stream` call
4. Verify: after done, the ScopeBoard renders with generated items

**Step 5: Final commit (if any cleanup needed)**

```bash
git add -A
git commit -m "fix: polish loading animations for PRD and Scope pages"
```

---

## Summary of Changes

| File                                                | Change                                                                   |
| --------------------------------------------------- | ------------------------------------------------------------------------ |
| `frontend/components/common/GenerationProgress.tsx` | New — shared step-list + progress bar component                          |
| `frontend/components/prd/PrdPage.tsx`               | Add `progressStep` state, wire `onProgress`, render `GenerationProgress` |
| `backend/app/routes/idea_agents.py`                 | Add `POST /agents/scope/stream` SSE endpoint                             |
| `frontend/lib/api.ts`                               | Add `streamScopeAgent` function                                          |
| `frontend/components/scope/ScopeFreezePage.tsx`     | Replace REST scope call with SSE stream, render `GenerationProgress`     |
