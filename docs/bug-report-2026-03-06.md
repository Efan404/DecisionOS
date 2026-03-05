# Bug Report - 2026-03-06

Discovered via Playwright E2E testing + code review on `dev/bug-hunting` branch.

---

## CRITICAL

### BUG-001: Feasibility Plan ID all duplicate as "plan1"

- **Location:** `backend/app/core/prompts.py:89`
- **Root cause:** `build_single_plan_prompt()` tells LLM to use `"plan1", "plan2", "plan3"` as example IDs, but 3 plans are generated in parallel via independent LLM calls. Each call only sees its own prompt and almost always returns `"plan1"`.
- **Symptoms:**
  - React key collision warning: `Encountered two children with the same key, plan1` (in `PlanCards.tsx:58`)
  - All 3 "View Detail" links point to `/feasibility/plan1` — only the first plan's detail is viewable
  - `selected_plan_id` is always `"plan1"`, making plan selection meaningless
- **Evidence:** localStorage `feasibility_plan_ids: ["plan1", "plan1", "plan1"]`
- **Affected files:**
  - `backend/app/core/prompts.py:89` (prompt template)
  - `backend/app/core/llm.py:50-63` (no ID dedup after generation)
  - `frontend/components/feasibility/PlanCards.tsx:58` (React key)

### BUG-002: Visiting Scope Freeze page breaks PRD access

- **Location:** `backend/app/db/repo_scope.py:140, :290`
- **Root cause:** Both `bootstrap_scope_draft` and `new_version` set `scope_frozen = false` when creating a new draft. When a user navigates to the Scope Freeze page, the frontend calls `getScopeDraft` -> 404 -> `bootstrapScopeDraft`, which creates a new draft and resets `scope_frozen` to `false`.
- **Symptoms:**
  - `canOpenPrd()` returns `false` (requires `scope_frozen === true`)
  - PRD page shows "PRD context not ready" even when PRD was already generated
  - Step 5 PRD nav link becomes unclickable (`<span>` instead of `<Link>`)
- **Evidence:** Backend API and localStorage both show `scope_frozen: false` while `prd_bundle` exists
- **Affected files:**
  - `backend/app/db/repo_scope.py:136-141` (bootstrap sets scope_frozen=false)
  - `backend/app/db/repo_scope.py:286-291` (new_version sets scope_frozen=false)
  - `frontend/lib/guards.ts:23-25` (`canOpenPrd` guard)
  - `frontend/components/layout/AppShell.tsx:149-155` (step locked logic)

---

## HIGH

### BUG-003: /icon.svg returns 500 Internal Server Error

- **Location:** `frontend/app/icon.svg` + `frontend/public/icon.svg`
- **Root cause:** Next.js 14 detects a conflict between App Router file convention (`app/icon.svg`) and public directory (`public/icon.svg`) for the same path.
- **Symptoms:** 4-6 console errors per page load, favicon not displayed
- **Evidence:** `curl http://127.0.0.1:3000/icon.svg` -> 500, error message: "A conflicting public file and page file was found for path /icon.svg"
- **Affected files:**
  - `frontend/app/icon.svg` (keep this one)
  - `frontend/public/icon.svg` (remove this one)

### BUG-004: GET /settings/ai returns full API keys in plaintext

- **Location:** `backend/app/routes/ai_settings.py:19-20`, `backend/app/schemas/ai_settings.py:16`
- **Root cause:** `AISettingsDetail` response model includes `api_key` field without masking. The `GET /settings/ai` endpoint returns full API keys to any authenticated user.
- **Symptoms:** API keys for third-party services (OpenRouter, ModelScope) visible in network responses
- **Risk:** Any user with valid login credentials can extract API keys
- **Affected files:**
  - `backend/app/routes/ai_settings.py:19-20`
  - `backend/app/schemas/ai_settings.py:11-16`
  - `backend/app/db/repo_ai.py` (to_schema function)

### BUG-005: Background path summary generation silently fails

- **Location:** `backend/app/routes/idea_dag.py:309-348`
- **Root cause:** `_fill_path_summary_background` runs in a FastAPI BackgroundTask. All exceptions are caught and logged as warnings. `apply_agent_update` is called without `allow_conflict_retry=True`, so version conflicts cause silent failure.
- **Symptoms:** Path summary may never populate in the context; user is never notified
- **Affected files:**
  - `backend/app/routes/idea_dag.py:309-348`

---

## MEDIUM

### BUG-006: stream_prd HTTPException.detail type unsafe access

- **Location:** `backend/app/routes/idea_agents.py:448`
- **Root cause:** Code calls `.get("code")` on `exc.detail` assuming it's a dict, but FastAPI's `HTTPException.detail` can be a plain string.
- **Symptoms:** `AttributeError` in certain PRD generation error paths
- **Affected files:**
  - `backend/app/routes/idea_agents.py:440-451`

### BUG-007: `enable_thinking: False` sent to non-supporting providers

- **Location:** `backend/app/core/ai_gateway.py:92, :287`
- **Root cause:** All OpenAI-compatible provider calls include `"enable_thinking": False`, which is not a standard OpenAI API field.
- **Symptoms:** Strict providers may reject requests with unknown fields
- **Affected files:**
  - `backend/app/core/ai_gateway.py:85-93` (\_invoke_provider_text)
  - `backend/app/core/ai_gateway.py:280-289` (\_call_openai_compatible_provider)

### BUG-008: Scope Freeze "Continue to PRD" button permanently disabled

- **Location:** Related to BUG-002
- **Root cause:** Same root cause — bootstrap resets `scope_frozen`, so the "Continue to PRD" button condition is never met after page load.
- **Symptoms:** User must re-freeze the baseline every time they visit Scope Freeze to proceed to PRD

---

## LOW

### BUG-009: UserExpandRequest.description lacks length validation

- **Location:** `backend/app/routes/idea_dag.py:119-150`
- **Root cause:** No `max_length` constraint on user input description field
- **Symptoms:** Excessively long inputs could cause expensive LLM calls or failures

### BUG-010: No React Error Boundary on major page components

- **Location:** `frontend/components/prd/PrdPage.tsx`, `frontend/components/scope/ScopeFreezePage.tsx`
- **Root cause:** Missing error boundaries around async-heavy components
- **Symptoms:** Unexpected JS errors during async operations could cause white screen
