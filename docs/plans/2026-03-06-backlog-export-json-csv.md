# Backlog JSON/CSV Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a low-risk export flow that lets users download PRD backlog data as JSON or CSV from the idea-scoped PRD page.

**Architecture:** Keep SQLite-backed `idea.context_json` as the only source of truth. The backend exposes a read-only idea-scoped export endpoint that reads persisted `prd_bundle.output.backlog.items` and serializes it to either JSON or CSV. The frontend adds two explicit download actions on the PRD page and never reconstructs export data from transient stream state.

**Tech Stack:** FastAPI, Pydantic, SQLite-backed idea context, Next.js App Router, TypeScript, Vitest, backend API tests.

---

## 0. Product Decisions

- Export source is persisted PRD output only:
  - use `context.prd_bundle.output.backlog.items` when available
  - fallback to `context.prd.backlog.items` only for backward compatibility
- Supported formats in this iteration:
  - `json`
  - `csv`
- Export scope in this iteration:
  - backlog items only
  - no requirements export
  - no third-party integrations
- CSV is a flat transport format:
  - array fields are joined with ` | `
  - one backlog item per row
- If the idea has no PRD or no backlog items:
  - return `409`
  - stable error code: `PRD_BACKLOG_NOT_READY`

## 1. API Contract

### 1.1 Route

- `GET /ideas/{idea_id}/prd/export?format=json|csv`

### 1.2 Request Rules

- `idea_id` only in route
- format defaults to `json` if omitted
- archived idea is rejected

### 1.3 Success Response

- `json`:
  - `200 application/json`
  - payload:

```json
{
  "idea_id": "uuid",
  "baseline_id": "baseline-id",
  "exported_at": "2026-03-06T12:00:00Z",
  "item_count": 8,
  "items": [
    {
      "id": "bl-001",
      "title": "Ship MVP intake",
      "requirement_id": "req-001",
      "priority": "P0",
      "type": "story",
      "summary": "Create initial intake flow",
      "acceptance_criteria": ["...", "..."],
      "source_refs": ["step4"],
      "depends_on": []
    }
  ]
}
```

- `csv`:
  - `200 text/csv; charset=utf-8`
  - attachment filename:
    - `decisionos-backlog-<idea_id>.csv`

### 1.4 Error Response

- `404 IDEA_NOT_FOUND`
- `409 IDEA_ARCHIVED`
- `409 PRD_BACKLOG_NOT_READY`
- `422 EXPORT_FORMAT_INVALID`

## 2. Export Shape

### 2.1 JSON

Return the full backlog structure with no lossy transformation on array fields.

### 2.2 CSV Columns

Use this exact column order:

1. `id`
2. `title`
3. `type`
4. `priority`
5. `summary`
6. `requirement_id`
7. `acceptance_criteria`
8. `source_refs`
9. `depends_on`

Serialization rules:

- `acceptance_criteria`: join with ` | `
- `source_refs`: join with ` | `
- `depends_on`: join with ` | `
- preserve commas/newlines by using proper CSV quoting, not manual string concatenation

## 3. Backend Plan

### Task 1: Add backend export contract tests

**Files:**
- Modify: `backend/tests/test_api_ideas_and_agents.py`

**Important test constraint**

Do **not** rely on the current `_generate_prd(...)` helper to supply backlog items.
In the current mainline repo state, PRD generation may still persist an empty backlog in demo mode, which would make export tests pass without validating real serialized content.

For success-path export tests:

- create an idea normally
- write a persisted `prd_bundle` (or legacy `context.prd`) directly into idea context with a non-empty `backlog.items`
- then call the export route

Reserve `_generate_prd(...)` for "not ready" or route wiring checks only.

**Step 1: Add a failing JSON export test with persisted backlog fixture**

Add a test that:

- creates an idea
- patches idea context with a handcrafted persisted `prd_bundle.output.backlog.items`
- calls `GET /ideas/{idea_id}/prd/export?format=json`
- asserts:
  - `200`
  - `item_count` matches injected backlog length
  - `items[0]` includes `requirement_id`

Skeleton:

```python
def test_prd_backlog_export_json(self) -> None:
    idea_id, version = self._create_idea("Export JSON Idea")
    context_payload = self._build_context_with_persisted_backlog(
        baseline_id="baseline-export-1",
        item_count=2,
    )
    patch_status, patched = self.client.request_json(
        "PATCH",
        f"/ideas/{idea_id}/context",
        {"version": version, "context": context_payload},
    )
    self.assertEqual(patch_status, 200)
    assert patched is not None

    status, body, headers = self.client.request_json_with_headers(
        "GET",
        f"/ideas/{idea_id}/prd/export?format=json",
    )
    self.assertEqual(status, 200)
    assert body is not None
    self.assertEqual(body["idea_id"], idea_id)
    self.assertEqual(body["item_count"], 2)
    self.assertEqual(body["items"][0]["requirement_id"], "req-001")
```

**Step 2: Add a failing CSV export test with persisted backlog fixture**

Assert:

- `200`
- `content-type` includes `text/csv`
- response text contains header row
- response text contains at least one backlog item title

**Step 3: Add a failing not-ready test**

Assert that requesting export before PRD generation returns:

- `409`
- `detail.code == "PRD_BACKLOG_NOT_READY"`

This test should use a newly created idea with no persisted PRD backlog at all.

**Step 4: Add a small test helper for persisted backlog context**

Add a local helper in the test file that returns a valid `DecisionContext` payload containing:

- minimal existing context fields
- `prd_bundle`
- `prd_bundle.output.backlog.items` with 1-2 representative items
- optional `context.prd` mirror only if legacy fallback coverage is desired

Keep this helper local to the export tests. Do not broaden existing PRD helpers unless necessary.

**Step 5: Run only the new export tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_api_ideas_and_agents.py -k "prd_backlog_export" -v --tb=short
```

Expected: FAIL because the route does not exist yet.

**Step 6: Commit**

```bash
git add backend/tests/test_api_ideas_and_agents.py
git commit -m "test(export): add PRD backlog export API contract tests"
```

### Task 2: Add export schemas and serialization helpers

**Files:**
- Modify: `backend/app/schemas/prd.py`
- Modify: `backend/app/routes/idea_prd_feedback.py` only if shared helpers are useful
- Prefer creating helper in: `backend/app/routes/idea_prd_export.py`

**Step 1: Add lightweight response schema for JSON export**

Add to `backend/app/schemas/prd.py`:

```python
class PRDBacklogExportJson(BaseModel):
    idea_id: str = Field(min_length=1)
    baseline_id: str = Field(min_length=1)
    exported_at: str = Field(min_length=1)
    item_count: int = Field(ge=0)
    items: list[PRDBacklogItem] = Field(default_factory=list)
```

**Step 2: Add helper functions for export conversion**

Create pure helpers:

- `_resolve_backlog_output(context: DecisionContext) -> tuple[str, list[PRDBacklogItem]]`
- `_serialize_backlog_csv(items: list[PRDBacklogItem]) -> str`

Rules:

- prefer `context.prd_bundle.output`
- fallback to `context.prd`
- raise a route-level state error if no backlog is available
- use Python `csv` module with `io.StringIO`

**Step 3: Run schema/import checks**

```bash
cd backend
PYTHONPATH=. .venv/bin/python -c "from app.schemas.prd import PRDBacklogExportJson; print('ok')"
```

Expected: `ok`

**Step 4: Commit**

```bash
git add backend/app/schemas/prd.py
git commit -m "feat(export): add PRD backlog export schema and serializer helpers"
```

### Task 3: Implement idea-scoped PRD export route

**Files:**
- Create: `backend/app/routes/idea_prd_export.py`
- Modify: `backend/app/main.py`

**Step 1: Create the new router**

Use:

- prefix: `/ideas/{idea_id}/prd`
- tag: `idea-prd-export`

Implement:

```python
@router.get("/export")
async def export_prd_backlog(idea_id: str, format: str = Query(default="json")):
    ...
```

Route behavior:

- load idea with `IdeaRepository`
- reject not found / archived
- parse context via `parse_context_strict`
- validate `format in {"json", "csv"}`
- resolve backlog from persisted PRD data
- return either `JSONResponse` or `Response`

For CSV response:

- `media_type="text/csv; charset=utf-8"`
- set `Content-Disposition` attachment header

**Step 2: Register the router**

In `backend/app/main.py`, include:

```python
from app.routes.idea_prd_export import router as idea_prd_export_router
```

and:

```python
app.include_router(idea_prd_export_router, dependencies=protected_dependencies)
```

**Step 3: Run targeted tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_api_ideas_and_agents.py -k "prd_backlog_export" -v --tb=short
```

Expected: PASS

**Step 4: Run broader API regression slice**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_api_ideas_and_agents.py -k "prd or ideas" -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routes/idea_prd_export.py backend/app/main.py
git commit -m "feat(export): add idea-scoped PRD backlog export route"
```

## 4. Frontend Plan

### Task 4: Add export API helpers

**Files:**
- Modify: `frontend/lib/api.ts`

**Step 1: Add a small download helper**

Add:

- `downloadPrdBacklogExport(ideaId: string, format: 'json' | 'csv'): Promise<void>`

Implementation approach:

- build URL: `/ideas/${ideaId}/prd/export?format=${format}`
- use the existing authenticated fetch pattern from `frontend/lib/api.ts`
- preserve cookie-based auth by reusing the repo's current fetch wrapper / `credentials: 'include'` behavior
- do **not** manually add an `Authorization` header
- if response is not ok:
  - parse API error
  - throw `ApiError`
- read `blob()`
- create object URL
- trigger download through a temporary anchor

Filename rules:

- JSON: `decisionos-backlog-${ideaId}.json`
- CSV: `decisionos-backlog-${ideaId}.csv`

**Step 2: Add a tiny type for JSON export only if needed**

Do not over-model unless the frontend actually renders the JSON payload.

**Step 3: Run typecheck**

```bash
pnpm tsc --noEmit
```

Expected: PASS

**Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(export): add frontend backlog export download helper"
```

### Task 5: Add export actions to the PRD page

**Files:**
- Modify: `frontend/components/prd/PrdPage.tsx`
- Modify: `frontend/components/prd/PrdView.tsx`
- Optional Test: `frontend/components/prd/__tests__/PrdPageBaseline.test.tsx`

**Step 1: Decide placement**

Recommended placement:

- top toolbar area of `PrdView`
- two explicit actions:
  - `Export JSON`
  - `Export CSV`

Do not hide these in a complex menu for this iteration.

**Step 2: Add props**

Add to `PrdViewProps`:

- `onExportJson?: () => Promise<void> | void`
- `onExportCsv?: () => Promise<void> | void`
- `exporting?: boolean`

**Step 3: Wire page logic**

In `PrdPage.tsx`:

- create `exporting` state
- guard on `activeIdeaId`
- call `downloadPrdBacklogExport(activeIdeaId, 'json')` or `'csv'`
- show toast on success/failure

Important:

- export must work from persisted PRD state
- export buttons stay available even if generation is not currently loading
- disable buttons when there is no `context.prd_bundle?.output` and no `context.prd`

**Step 4: Add a focused frontend test**

Update or add a test that:

- mocks the download helper
- renders PRD page with persisted bundle
- clicks `Export CSV`
- asserts helper called with active idea id and `csv`

Because current PRD tests are already stale, do not broaden scope. Keep the test narrow and aligned with the real `streamPost` implementation.

**Step 5: Run frontend test**

```bash
pnpm vitest run frontend/components/prd/__tests__/PrdPageBaseline.test.tsx
```

Expected: PASS after test alignment

**Step 6: Run frontend typecheck**

```bash
pnpm tsc --noEmit
```

Expected: PASS

**Step 7: Commit**

```bash
git add frontend/components/prd/PrdPage.tsx frontend/components/prd/PrdView.tsx frontend/components/prd/__tests__/PrdPageBaseline.test.tsx
git commit -m "feat(export): add PRD backlog export actions to the PRD page"
```

## 5. Edge Cases

- No PRD generated yet:
  - backend returns `409 PRD_BACKLOG_NOT_READY`
  - frontend shows toast error
- PRD exists but backlog is empty:
  - JSON returns `item_count: 0`
  - CSV returns header row only
- Archived idea:
  - reject with `409 IDEA_ARCHIVED`
- Unsupported format:
  - reject with `422 EXPORT_FORMAT_INVALID`
- CSV escaping:
  - titles and summaries may contain commas or newlines
  - must rely on CSV library quoting

## 6. Out of Scope

- Linear export
- Jira export
- requirements export
- bundled ZIP export
- custom CSV column mapping
- export history / audit log
- background export jobs

## 7. Verification Checklist

- `GET /ideas/{idea_id}/prd/export?format=json` returns persisted backlog JSON
- `GET /ideas/{idea_id}/prd/export?format=csv` downloads valid CSV
- export works after page refresh
- export does not depend on in-memory SSE partials
- archived and missing-PRD states return stable API errors
- frontend buttons are disabled when no PRD exists

## 8. Follow-Up

If this ships cleanly, the next low-risk extension is:

1. add `requirements` export alongside backlog
2. add provider-specific CSV presets
3. only then consider Linear/Jira direct integrations
