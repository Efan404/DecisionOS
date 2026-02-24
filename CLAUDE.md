# Project Notes for Claude

## Intentionally Disabled Code — Do NOT Restore

The following code has been **deliberately commented out** as part of a simplification pass (2026-02-24). Do not uncomment, restore, or re-implement these features unless explicitly asked.

### Backend: PRD two-stage parallel generation

**File:** `backend/app/routes/idea_agents.py`

The `stream_prd` endpoint previously made 3 LLM calls:

- Stage A (parallel): `generate_prd_requirements` + `generate_prd_markdown`
- Stage B (sequential): `generate_prd_backlog` (depends on Stage A requirement IDs)

This has been replaced with a **single call** to `generate_prd_markdown` only.
The Stage A/B code is preserved as comments inside `stream_prd` under the block labelled `--- DISABLED: two-stage parallel generation ---`.

`PRDOutput.requirements` is now always `[]` and `PRDOutput.backlog.items` is always `[]`.

### Frontend: Requirements, Sections, Backlog tabs

**File:** `frontend/components/prd/PrdView.tsx`

The following UI is commented out and must stay commented out:

- `Requirements` tab and its list rendering
- `Sections` tab and its list rendering
- Right-side column: requirement filter badge, `PrdBacklogPanel`, `PrdFeedbackCard`
- Stream partials preview (requirements/backlog loading states)
- `PrdBacklogPanel` and `PrdFeedbackCard` imports
- `selectedRequirementIdInput` / `selectedRequirementId` / `requirementsById` state and memos

Only the **PRD (markdown) tab** is active. The page title is "PRD" (not "PRD + Backlog").

### Why

The free model (`stepfun/step-3.5-flash:free`) is slow. Reducing from 3 LLM calls to 1 cuts generation time by ~2/3. The backlog and requirements features will be restored when a faster model is available or when explicitly re-enabled.
