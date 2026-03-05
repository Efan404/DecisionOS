# Bug Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 10 bugs (2 critical, 3 high, 3 medium, 2 low) discovered via Playwright E2E testing + code review.

**Architecture:** Ordered by risk (lowest first). Each task is one isolated fix with its own commit. Backend fixes use Python/FastAPI. Frontend fixes use React/Next.js/TypeScript.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, Next.js 14, React 18, Zustand, TypeScript

**Branch:** `dev/bug-hunting` (already checked out)

**Design doc:** `docs/plans/2026-03-06-bug-fixes-design.md`

---

### Task 1: BUG-003 — Fix /icon.svg 500 error

**Files:**

- Delete: `frontend/public/icon.svg`

**Step 1: Delete the duplicate file**

```bash
rm frontend/public/icon.svg
```

**Step 2: Verify fix**

```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:3000/icon.svg
```

Expected: `200` (not `500`). Note: requires dev server restart if running.

**Step 3: Commit**

```bash
git add frontend/public/icon.svg
git commit -m "fix: remove duplicate icon.svg from public/ to resolve Next.js 500 conflict"
```

---

### Task 2: BUG-007 — Remove non-standard `enable_thinking` field

**Files:**

- Modify: `backend/app/core/ai_gateway.py:92` and `:287`

**Step 1: Remove line 92 from `_invoke_provider_text`**

In the `body` dict in `_invoke_provider_text` (~line 85-93), delete the line:

```python
        "enable_thinking": False,
```

**Step 2: Remove line 287 from `_call_openai_compatible_provider`**

In the `body` dict in `_call_openai_compatible_provider` (~line 280-289), delete the line:

```python
        "enable_thinking": False,
```

**Step 3: Verify no other occurrences**

```bash
cd backend && grep -rn "enable_thinking" app/
```

Expected: no results.

**Step 4: Commit**

```bash
git add backend/app/core/ai_gateway.py
git commit -m "fix: remove non-standard enable_thinking field from provider requests"
```

---

### Task 3: BUG-009 — Add input length validation for node expansion

**Files:**

- Modify: `backend/app/routes/idea_dag.py` — `UserExpandRequest` class

**Step 1: Find UserExpandRequest and add Field constraint**

Locate the `UserExpandRequest` Pydantic model in `idea_dag.py`. Add `max_length=2000` to the `description` field. If the class uses a plain type annotation like `description: str`, change it to:

```python
from pydantic import Field

class UserExpandRequest(BaseModel):
    description: str = Field(max_length=2000)
```

Ensure `Field` is imported from `pydantic` (may already be imported).

**Step 2: Verify backend still starts**

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health
```

Expected: `200`

**Step 3: Commit**

```bash
git add backend/app/routes/idea_dag.py
git commit -m "fix: add max_length=2000 to UserExpandRequest.description"
```

---

### Task 4: BUG-006 — Fix HTTPException.detail type-unsafe access

**Files:**

- Modify: `backend/app/routes/idea_agents.py:446-451`

**Step 1: Replace the existing handler**

Current code at ~line 446-451:

```python
        except HTTPException as exc:
            detail = exc.detail
            code = detail.get("code", "ERROR") if isinstance(detail, dict) else "ERROR"
            message = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
            yield _sse_event("error", {"code": code, "message": message})
            return
```

This code already has the `isinstance` guard — verify it matches. If the guard is missing, add it. The current code on disk already has the guard (confirmed at line 448), so this task is just verification.

**Step 2: Verify by reading the file**

```bash
sed -n '446,451p' backend/app/routes/idea_agents.py
```

Expected: code includes `isinstance(detail, dict)` checks on both the `code` and `message` lines. If already present, no change needed.

**Step 3: Commit (only if changes were made)**

```bash
git add backend/app/routes/idea_agents.py
git commit -m "fix: add type guard for HTTPException.detail in stream_prd"
```

---

### Task 5: BUG-005 — Fix path summary background task silent failure

**Files:**

- Modify: `backend/app/routes/idea_dag.py:341`

**Step 1: Add `allow_conflict_retry=True` to the `apply_agent_update` call**

Change line ~341 from:

```python
    _repo.apply_agent_update(
        idea_id,
        version=idea.version,
        mutate_context=lambda ctx: ctx.model_copy(
            update={"confirmed_dag_path_summary": summary}
        ),
    )
```

To:

```python
    _repo.apply_agent_update(
        idea_id,
        version=idea.version,
        mutate_context=lambda ctx: ctx.model_copy(
            update={"confirmed_dag_path_summary": summary}
        ),
        allow_conflict_retry=True,
    )
```

**Step 2: Verify backend starts**

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health
```

Expected: `200`

**Step 3: Commit**

```bash
git add backend/app/routes/idea_dag.py
git commit -m "fix: enable conflict retry for background path summary update"
```

---

### Task 6: BUG-001 — Fix feasibility plan ID duplication

**Files:**

- Modify: `backend/app/core/llm.py:50-63`

**Step 1: Override plan.id after LLM generation**

Change `generate_single_plan` from:

```python
def generate_single_plan(payload: FeasibilityInput, plan_index: int) -> Plan:
    """Generate exactly one feasibility Plan concurrently with other plan calls."""
    from app.schemas.feasibility import Plan

    return ai_gateway.generate_structured(
        task="feasibility",
        user_prompt=prompts.build_single_plan_prompt(
            idea_seed=payload.idea_seed,
            confirmed_node_content=payload.confirmed_node_content,
            confirmed_path_summary=payload.confirmed_path_summary,
            plan_index=plan_index,
        ),
        schema_model=Plan,
    )
```

To:

```python
def generate_single_plan(payload: FeasibilityInput, plan_index: int) -> Plan:
    """Generate exactly one feasibility Plan concurrently with other plan calls."""
    from app.schemas.feasibility import Plan

    plan = ai_gateway.generate_structured(
        task="feasibility",
        user_prompt=prompts.build_single_plan_prompt(
            idea_seed=payload.idea_seed,
            confirmed_node_content=payload.confirmed_node_content,
            confirmed_path_summary=payload.confirmed_path_summary,
            plan_index=plan_index,
        ),
        schema_model=Plan,
    )
    plan.id = f"plan{plan_index + 1}"
    return plan
```

**Step 2: Verify Plan.id is mutable**

Check `backend/app/schemas/feasibility.py` — ensure the `Plan` model does NOT use `frozen=True` in its Config. Pydantic v2 models are mutable by default.

**Step 3: Run existing tests**

```bash
cd backend && python -m pytest tests/test_api_ideas_and_agents.py -v -x --timeout=30 2>&1 | tail -20
```

Expected: existing tests pass (they use mock LLM responses that already return plan1/plan2/plan3).

**Step 4: Commit**

```bash
git add backend/app/core/llm.py
git commit -m "fix: force unique plan IDs (plan1/plan2/plan3) after LLM generation"
```

---

### Task 7: BUG-004 — Mask API keys in GET response

**Files:**

- Modify: `backend/app/db/repo_ai.py:127-133`
- Modify: `backend/app/routes/ai_settings.py:24`

**Step 1: Add mask helper in `repo_ai.py`**

Add this function before `to_schema`:

```python
_MASK_SENTINEL = "****"

def _mask_api_key(key: str | None) -> str | None:
    if not key:
        return key
    if len(key) <= 12:
        return _MASK_SENTINEL
    return f"{key[:4]}{_MASK_SENTINEL}{key[-4:]}"
```

**Step 2: Apply masking in `to_schema`**

Change `to_schema` from:

```python
def to_schema(record: AISettingsRecord) -> AISettingsDetail:
    return AISettingsDetail(
        id=record.id,
        providers=record.config.providers,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
```

To:

```python
def to_schema(record: AISettingsRecord) -> AISettingsDetail:
    masked_providers = [
        p.model_copy(update={"api_key": _mask_api_key(p.api_key)})
        for p in record.config.providers
    ]
    return AISettingsDetail(
        id=record.id,
        providers=masked_providers,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
```

**Step 3: Preserve existing keys on PATCH when masked value is sent**

In `backend/app/routes/ai_settings.py`, change `patch_ai_settings`:

```python
@router.patch("/ai", response_model=AISettingsDetail)
async def patch_ai_settings(payload: AISettingsPayload) -> AISettingsDetail:
    return to_schema(_repo.update_settings(payload))
```

To:

```python
@router.patch("/ai", response_model=AISettingsDetail)
async def patch_ai_settings(payload: AISettingsPayload) -> AISettingsDetail:
    existing = _repo.get_settings()
    existing_keys = {p.id: p.api_key for p in existing.config.providers}
    for provider in payload.providers:
        if provider.api_key and _MASK_SENTINEL in provider.api_key:
            provider.api_key = existing_keys.get(provider.id)
    return to_schema(_repo.update_settings(payload))
```

Add the import at top of `ai_settings.py`:

```python
from app.db.repo_ai import AISettingsRepository, to_schema, _MASK_SENTINEL
```

**Step 4: Verify via curl**

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login -H 'Content-Type: application/json' -d '{"username":"test","password":"test"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])') && curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/settings/ai | python3 -c "import sys,json; [print(p.get('api_key','')) for p in json.load(sys.stdin).get('providers',[])]"
```

Expected: masked keys like `sk-o****1ee8`, not full keys.

**Step 5: Run existing tests**

```bash
cd backend && python -m pytest tests/test_ai_settings_api.py -v -x --timeout=30 2>&1 | tail -20
```

**Step 6: Commit**

```bash
git add backend/app/db/repo_ai.py backend/app/routes/ai_settings.py
git commit -m "fix(security): mask API keys in GET /settings/ai response"
```

---

### Task 8: BUG-010 — Add React Error Boundary

**Files:**

- Create: `frontend/components/common/PageErrorBoundary.tsx`
- Modify: `frontend/app/ideas/[ideaId]/prd/page.tsx`
- Modify: `frontend/app/ideas/[ideaId]/scope-freeze/page.tsx`

**Step 1: Create PageErrorBoundary component**

Create `frontend/components/common/PageErrorBoundary.tsx`:

```tsx
'use client'

import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { error: Error | null }

export class PageErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('PageErrorBoundary caught:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <main className="mx-auto mt-12 max-w-md px-6 text-center">
          <h1 className="text-lg font-semibold text-[#1e1e1e]">Something went wrong</h1>
          <p className="mt-2 text-sm text-[#1e1e1e]/50">{this.state.error.message}</p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="mt-4 rounded-lg border border-[#1e1e1e]/15 px-4 py-2 text-sm font-medium text-[#1e1e1e]/70 transition hover:bg-[#f5f5f5]"
          >
            Try Again
          </button>
        </main>
      )
    }
    return this.props.children
  }
}
```

**Step 2: Wrap PrdPage in `frontend/app/ideas/[ideaId]/prd/page.tsx`**

Change from:

```tsx
return (
  <IdeaScopedHydration ideaId={ideaId}>
    <PrdPage baselineId={baselineId ?? null} />
  </IdeaScopedHydration>
)
```

To:

```tsx
return (
  <IdeaScopedHydration ideaId={ideaId}>
    <PageErrorBoundary>
      <PrdPage baselineId={baselineId ?? null} />
    </PageErrorBoundary>
  </IdeaScopedHydration>
)
```

Add import: `import { PageErrorBoundary } from '../../../../components/common/PageErrorBoundary'`

**Step 3: Wrap ScopeFreezePage in `frontend/app/ideas/[ideaId]/scope-freeze/page.tsx`**

Change from:

```tsx
return (
  <IdeaScopedHydration ideaId={ideaId}>
    <ScopeFreezePage />
  </IdeaScopedHydration>
)
```

To:

```tsx
return (
  <IdeaScopedHydration ideaId={ideaId}>
    <PageErrorBoundary>
      <ScopeFreezePage />
    </PageErrorBoundary>
  </IdeaScopedHydration>
)
```

Add import: `import { PageErrorBoundary } from '../../../../components/common/PageErrorBoundary'`

**Step 4: Run frontend tests**

```bash
pnpm test:web 2>&1 | tail -20
```

Expected: all existing tests pass.

**Step 5: Commit**

```bash
git add frontend/components/common/PageErrorBoundary.tsx frontend/app/ideas/\[ideaId\]/prd/page.tsx frontend/app/ideas/\[ideaId\]/scope-freeze/page.tsx
git commit -m "feat: add PageErrorBoundary to PRD and Scope Freeze pages"
```

---

### Task 9: BUG-002 — Stop auto-bootstrap when frozen baseline exists

**Files:**

- Modify: `frontend/components/scope/ScopeFreezePage.tsx:237-304`

This is the most complex fix. The current `useEffect` at line 237 always bootstraps when `getScopeDraft` returns 404. We need to add a branch: if 404 AND `context.scope_frozen === true`, load the frozen baseline in read-only mode instead.

**Step 1: Modify the draft-loading `useEffect`**

In the `run` async function inside the useEffect (~line 247), after the `getScopeDraft` 404 catch block (~line 257-265), add a check before bootstrapping:

Replace the inner catch block (lines 257-303):

```typescript
        } catch (error) {
          if (!isNotFoundError(error)) {
            if (!cancelled) {
              const message = error instanceof Error ? error.message : 'Failed to load scope draft.'
              setErrorMessage(message)
              toast.error(message)
            }
            return
          }

          // 404: no draft exists
          // If scope is already frozen, show frozen baseline read-only instead of auto-bootstrapping
          if (context.scope_frozen && context.current_scope_baseline_id && routeIdeaId) {
            try {
              const baseline = await getScopeBaseline(routeIdeaId, context.current_scope_baseline_id)
              if (!cancelled) {
                setDraft({
                  baseline: baseline.baseline,
                  items: baseline.items,
                  readonly: true,
                })
                setLoadedIdeaId(routeIdeaId)
                setLocalIdeaVersion(workingVersion)
              }
            } catch (baselineError) {
              if (!cancelled) {
                const message =
                  baselineError instanceof Error
                    ? baselineError.message
                    : 'Failed to load frozen baseline.'
                setErrorMessage(message)
                toast.error(message)
              }
            } finally {
              if (!cancelled) setLoading(false)
            }
            return
          }

          try {
            const envelope = await bootstrapScopeDraft(routeIdeaId, {
              version: activeIdea.version,
            })
            // ... rest of existing bootstrap code unchanged ...
```

**Step 2: Add `getScopeBaseline` import**

At the top of the file (~line 9-17), add `getScopeBaseline` to the imports from `../../lib/api`:

```typescript
import {
  ApiError,
  bootstrapScopeDraft,
  createScopeNewVersion,
  freezeScope,
  getScopeDraft,
  getScopeBaseline,
  patchScopeDraft,
  postIdeaScopedAgent,
} from '../../lib/api'
```

**Step 3: Add `context` to the useEffect dependency array**

The current dependency array at ~line 345 is:

```typescript
  }, [activeIdea, canOpen, hydrateDraftIfEmpty, loadedIdeaId, routeIdeaId, setIdeaVersion])
```

Add `context.scope_frozen` and `context.current_scope_baseline_id`:

```typescript
  }, [activeIdea, canOpen, context.scope_frozen, context.current_scope_baseline_id, hydrateDraftIfEmpty, loadedIdeaId, routeIdeaId, setIdeaVersion])
```

**Step 4: Add "Edit Scope" button in the render section**

In the JSX, when `draft?.readonly` is `true` AND `draft?.baseline.status === 'frozen'`, show an "Edit Scope" button that calls `createScopeNewVersion`. Find the section where `Freeze Baseline` button is rendered and add a sibling:

After the existing freeze/continue buttons, add:

```tsx
{
  readonly && draft?.baseline.status === 'frozen' && (
    <button
      type="button"
      onClick={handleEditScope}
      className="rounded-xl border border-[#1e1e1e]/15 bg-white px-4 py-2 text-sm font-medium text-[#1e1e1e]/70 transition hover:bg-[#f5f5f5]"
    >
      Edit Scope (New Draft)
    </button>
  )
}
```

**Step 5: Add `handleEditScope` handler**

Add this handler function inside the component (after the existing `handleMoveItem` or similar handlers):

```typescript
const handleEditScope = async () => {
  if (!routeIdeaId || !activeIdea) return
  const currentVersion = ideaVersion ?? activeIdea.version
  if (!currentVersion) return

  setLoading(true)
  setErrorMessage(null)
  try {
    const envelope = await createScopeNewVersion(routeIdeaId, { version: currentVersion })
    setDraft(envelope.data)
    setIdeaVersion(routeIdeaId, envelope.idea_version)
    setLocalIdeaVersion(envelope.idea_version)
    // Sync context from server since scope_frozen is now false
    await syncContextFromServer(envelope.idea_version)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to create new scope draft.'
    setErrorMessage(message)
    toast.error(message)
  } finally {
    setLoading(false)
  }
}
```

**Step 6: Run frontend tests**

```bash
pnpm test:web 2>&1 | tail -30
```

Check for failures in scope-related tests. Fix any that assume auto-bootstrap behavior.

**Step 7: Commit**

```bash
git add frontend/components/scope/ScopeFreezePage.tsx
git commit -m "fix(scope): stop auto-bootstrap when frozen baseline exists, add Edit Scope button"
```

---

### Final Verification

After all 9 tasks are complete:

**Step 1: Run all backend tests**

```bash
cd backend && python -m pytest tests/ -v --timeout=60 2>&1 | tail -30
```

**Step 2: Run all frontend tests**

```bash
pnpm test:web 2>&1 | tail -30
```

**Step 3: Manual Playwright smoke test**

Open browser and verify:

1. Login page loads without icon.svg errors
2. Navigate to Ideas -> Idea Canvas -> Feasibility (check 3 unique plan IDs)
3. Scope Freeze shows frozen baseline in read-only mode (no auto-bootstrap)
4. PRD page loads (no "context not ready" error)
5. Settings page shows masked API keys

**Step 4: Review all commits**

```bash
git log --oneline main..HEAD
```

Expected: 9 commits, one per bug fix.
