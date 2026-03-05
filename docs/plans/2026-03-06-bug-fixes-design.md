# Bug Fixes Design - 2026-03-06

Fixes for 10 bugs discovered via Playwright E2E testing + code review.
See `docs/bug-report-2026-03-06.md` for full bug descriptions.

---

## BUG-001: Feasibility Plan ID Duplicate (Critical)

**Strategy:** Backend forces plan ID after LLM generation, ignoring LLM-returned ID.

**Changes:**

- `backend/app/core/llm.py` — `generate_single_plan()`: after `ai_gateway.generate_structured()` returns, overwrite `plan.id = f"plan{plan_index + 1}"` before returning.
- No prompt changes needed. The prompt example IDs become irrelevant since we override.

**Why not fix the prompt:** LLM compliance is never guaranteed. Hard-coding the ID post-generation is 100% reliable.

---

## BUG-002: Scope Freeze Page Breaks PRD Access (Critical)

**Strategy:** Frontend stops auto-bootstrapping when a frozen baseline already exists. User must explicitly click "Edit Scope" to create a new draft.

**Changes:**

- `frontend/components/scope/ScopeFreezePage.tsx`:
  - On mount, call `getScopeDraft()` first.
  - If 404 AND a frozen baseline exists (`scope_frozen === true` in context), show the frozen baseline in read-only mode with an "Edit Scope" button instead of auto-bootstrapping.
  - "Edit Scope" button triggers `createScopeNewVersion()` which creates a new draft (and resets `scope_frozen`). This is the intentional user action.
  - If 404 AND no frozen baseline, bootstrap as before (first-time flow).

**Result:** Simply viewing Scope Freeze page no longer resets `scope_frozen`. PRD remains accessible.

**BUG-008 (Continue to PRD disabled):** Resolved automatically by this fix.

---

## BUG-003: /icon.svg 500 Error (High)

**Strategy:** Delete the duplicate file.

**Changes:**

- Delete `frontend/public/icon.svg` (keep `frontend/app/icon.svg` for Next.js App Router convention).

---

## BUG-004: API Key Plaintext Exposure (High)

**Strategy:** Backend masks API keys in GET responses. PATCH ignores masked values.

**Changes:**

- `backend/app/db/repo_ai.py` — `to_schema()` or a new helper: mask `api_key` to show first 4 + `****` + last 4 chars (e.g. `sk-o****1ee8`). Keys shorter than 12 chars show `****`.
- `backend/app/routes/ai_settings.py` — `patch_ai_settings()`: before saving, if a provider's `api_key` matches the mask pattern (contains `****`), preserve the existing key from the database instead of overwriting.
- `backend/app/schemas/ai_settings.py` — no schema changes needed; `api_key` remains `str | None`.

---

## BUG-005: Path Summary Silent Failure (High)

**Strategy:** Add `allow_conflict_retry=True` to the background task's `apply_agent_update` call.

**Changes:**

- `backend/app/routes/idea_dag.py` — `_fill_path_summary_background()`: add `allow_conflict_retry=True` to the `apply_agent_update()` call (~line 341).

---

## BUG-006: HTTPException.detail Type Unsafe (Medium)

**Strategy:** Add type guard before accessing `.get()`.

**Changes:**

- `backend/app/routes/idea_agents.py` (~line 448): wrap with `isinstance(exc.detail, dict)` check. If detail is a string, use it directly as the error message with a generic code.

---

## BUG-007: Non-standard `enable_thinking` Field (Medium)

**Strategy:** Remove the field from request bodies.

**Changes:**

- `backend/app/core/ai_gateway.py:92` — remove `"enable_thinking": False` from `_invoke_provider_text` body.
- `backend/app/core/ai_gateway.py:287` — remove `"enable_thinking": False` from `_call_openai_compatible_provider` body.

---

## BUG-009: Missing Input Length Validation (Low)

**Strategy:** Add `max_length` constraint to the schema.

**Changes:**

- `backend/app/routes/idea_dag.py` — `UserExpandRequest.description`: add `Field(max_length=2000)`.

---

## BUG-010: Missing Error Boundaries (Low)

**Strategy:** Create a reusable `PageErrorBoundary` component and wrap key pages.

**Changes:**

- Create `frontend/components/common/PageErrorBoundary.tsx` — a class component that catches JS errors and renders a fallback UI with retry button.
- Wrap `PrdPage` and `ScopeFreezePage` with `PageErrorBoundary` in their respective page files.

---

## Implementation Order

Fixes are ordered by risk (lowest risk first) to minimize breakage:

1. BUG-003 — delete one file
2. BUG-007 — delete two lines
3. BUG-009 — add one field constraint
4. BUG-006 — add type guard
5. BUG-005 — add one parameter
6. BUG-001 — one-line ID override
7. BUG-004 — API key masking (backend only)
8. BUG-010 — new component + wrapping
9. BUG-002 — scope freeze page logic change (most complex)

## Testing Strategy

- Run existing `vitest` tests after each fix to ensure no regression.
- Manual Playwright smoke test after all fixes: login -> ideas -> idea-canvas -> feasibility -> scope-freeze -> PRD.
- Verify icon.svg no longer 500s, console errors reduced.
