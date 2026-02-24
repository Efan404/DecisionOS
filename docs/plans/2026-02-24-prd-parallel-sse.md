# PRD Parallel Split + SSE Streaming Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the single blocking PRD LLM call with a two-stage parallel approach streamed over SSE, so users see content appearing progressively instead of waiting 30-60s for a blank screen.

**Architecture:**

- New endpoint `POST /ideas/{idea_id}/agents/prd/stream` emits SSE events.
- Stage A: two parallel LLM calls — `generate_requirements` + `generate_markdown_sections` — both start immediately.
- Stage B: once Stage A completes, `generate_backlog` fires (needs requirement IDs) while markdown result is already emitted.
- Frontend `PrdPage` switches from `postIdeaScopedAgent` to `streamPost`, showing a skeleton while loading and filling in content as SSE events arrive.
- Old `POST /ideas/{idea_id}/agents/prd` is kept intact (backward compat, used by existing tests).

**Tech Stack:** Python asyncio + ThreadPoolExecutor (same pattern as feasibility/stream), Pydantic v2, FastAPI SSE via `sse_starlette`, React + fetch-event-stream (existing `streamPost` util in `lib/sse.ts`).

---

## Task 1: New Pydantic schemas for split LLM calls

**Files:**

- Modify: `backend/app/schemas/prd.py`

Split `PRDOutput` into sub-schemas so each parallel call has a tight schema. No change to `PRDOutput` itself (stays as the merged result stored in DB).

**Step 1: Add sub-schemas after existing imports in `prd.py`**

Add these three classes right after the `PRDGenerationMeta` class (before `PRDOutput`):

```python
class PRDRequirementsOutput(BaseModel):
    """Output of the parallel requirements LLM call."""
    requirements: list[PRDRequirement] = Field(min_length=6, max_length=12)


class PRDMarkdownOutput(BaseModel):
    """Output of the parallel markdown+sections LLM call."""
    markdown: str
    sections: list[PRDSection] = Field(min_length=6)


class PRDBacklogOutput(BaseModel):
    """Output of the Stage-B backlog LLM call (requires requirement IDs)."""
    backlog: PRDBacklog
```

**Step 2: Run existing tests to make sure nothing broke**

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=AIHackathon20250225! \
  PYTHONPATH=. .venv/bin/pytest tests/ -v --tb=short -q
```

Expected: all tests pass (no schema changes to PRDOutput).

**Step 3: Commit**

```bash
git add backend/app/schemas/prd.py
git commit -m "feat(prd): add PRDRequirementsOutput, PRDMarkdownOutput, PRDBacklogOutput sub-schemas"
```

---

## Task 2: New split prompt builders

**Files:**

- Modify: `backend/app/core/prompts.py`

Add three focused prompt functions. Each is smaller than the current monolithic PRD prompt because it only asks for one part.

**Step 1: Add the three new functions at the end of `prompts.py`**

```python
def build_prd_requirements_prompt(*, context: dict[str, object]) -> str:
    """Prompt for Stage-A parallel call: generate requirements only."""
    return (
        "You are a senior PM. Given the product context below, generate 6-12 well-defined "
        "product requirements. Each requirement needs: id (req-001...), title, description, "
        "rationale, 2-8 acceptance_criteria (list of strings), "
        "source_refs (list of step2/step3/step4).\n"
        f"context={json.dumps(context, ensure_ascii=False)}\n"
        "Return JSON: {\"requirements\": [...]}"
    )


def build_prd_markdown_prompt(*, context: dict[str, object]) -> str:
    """Prompt for Stage-A parallel call: generate markdown narrative + sections only."""
    return (
        "You are a senior PM. Given the product context below, write a delivery-ready PRD "
        "as markdown with 6-12 named sections (executive summary, personas, capabilities, etc). "
        "Be concrete and implementation-ready.\n"
        f"context={json.dumps(context, ensure_ascii=False)}\n"
        "Return JSON: {\"markdown\": \"...\", \"sections\": [{\"id\":\"...\",\"title\":\"...\",\"content\":\"...\"}]}"
    )


def build_prd_backlog_prompt(
    *,
    context: dict[str, object],
    requirement_ids: list[str],
) -> str:
    """Prompt for Stage-B call: generate backlog items referencing requirement IDs."""
    return (
        "You are a senior PM. Given the product context and requirement IDs below, "
        "generate 8-15 executable backlog items. Each item needs: id (bl-001...), title, summary, "
        "requirement_id (must be one of the provided IDs), priority (P0/P1/P2), "
        "type (epic/story/task), 2-8 acceptance_criteria, "
        "source_refs (step2/step3/step4), depends_on (list of bl-ids, may be empty). "
        "Out-of-scope items must not be P0.\n"
        f"context={json.dumps(context, ensure_ascii=False)}\n"
        f"requirement_ids={json.dumps(requirement_ids)}\n"
        "Return JSON: {\"backlog\": {\"items\": [...]}}"
    )
```

**Step 2: Run tests**

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=AIHackathon20250225! \
  PYTHONPATH=. .venv/bin/pytest tests/ -v --tb=short -q
```

Expected: all pass (new functions, no behavioural change).

**Step 3: Commit**

```bash
git add backend/app/core/prompts.py
git commit -m "feat(prd): add split prompt builders for requirements, markdown, backlog"
```

---

## Task 3: New LLM functions for split calls

**Files:**

- Modify: `backend/app/core/llm.py`

**Step 1: Add imports at top of llm.py**

Add to the existing imports block:

```python
from app.schemas.prd import (
    PRDOutput, PrdContextPack,
    PRDRequirementsOutput, PRDMarkdownOutput, PRDBacklogOutput,
)
```

(Replace the existing `from app.schemas.prd import PRDOutput, PrdContextPack` line.)

**Step 2: Add three new functions after `generate_prd_strict`**

```python
def generate_prd_requirements(context: dict[str, object]) -> PRDRequirementsOutput:
    """Stage-A parallel call: requirements only."""
    return ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompts.build_prd_requirements_prompt(context=context),
        schema_model=PRDRequirementsOutput,
    )


def generate_prd_markdown(context: dict[str, object]) -> PRDMarkdownOutput:
    """Stage-A parallel call: markdown + sections only."""
    return ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompts.build_prd_markdown_prompt(context=context),
        schema_model=PRDMarkdownOutput,
    )


def generate_prd_backlog(
    context: dict[str, object],
    requirement_ids: list[str],
) -> PRDBacklogOutput:
    """Stage-B call: backlog items (requires requirement IDs from Stage A)."""
    return ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompts.build_prd_backlog_prompt(
            context=context, requirement_ids=requirement_ids
        ),
        schema_model=PRDBacklogOutput,
    )
```

**Step 3: Build a slim context helper** (shared by both old and new paths)

Add this private helper right before `generate_prd_strict`:

```python
def _build_slim_prd_context(pack: PrdContextPack) -> dict[str, object]:
    """Return a trimmed context dict for PRD prompts (no path_json, no alt plans)."""
    full = pack.model_dump(mode="python")
    step2: dict = full.get("step2_path", {})
    step3: dict = full.get("step3_feasibility", {})
    step4: dict = full.get("step4_scope", {})
    selected_plan: dict = step3.get("selected_plan", {})
    return {
        "idea_seed": full.get("idea_seed"),
        "confirmed_path_summary": step2.get("path_summary"),
        "leaf_node_content": step2.get("leaf_node_content"),
        "selected_plan": {
            "name": selected_plan.get("name"),
            "summary": selected_plan.get("summary"),
            "score_overall": selected_plan.get("score_overall"),
            "recommended_positioning": selected_plan.get("recommended_positioning"),
        },
        "in_scope": [
            {"title": i.get("title"), "desc": i.get("desc"), "priority": i.get("priority")}
            for i in step4.get("in_scope", [])
        ],
        "out_scope": [
            {"title": i.get("title"), "reason": i.get("reason")}
            for i in step4.get("out_scope", [])
        ],
    }
```

And update `generate_prd_strict` to use it (keeping backward compat):

```python
def generate_prd_strict(context_pack: PrdContextPack) -> PRDOutput:
    try:
        return ai_gateway.generate_structured(
            task="prd",
            user_prompt=prompts.build_prd_prompt(
                context_pack=_build_slim_prd_context(context_pack),
            ),
            schema_model=PRDOutput,
        )
    except Exception as exc:
        raise PRDGenerationError("Failed to generate PRD output from provider") from exc
```

Note: `build_prd_prompt` in prompts.py already expects the slim dict (we changed it earlier), so this just makes the slim building explicit and reusable.

**Step 4: Run tests**

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=AIHackathon20250225! \
  PYTHONPATH=. .venv/bin/pytest tests/ -v --tb=short -q
```

Expected: all pass.

**Step 5: Commit**

```bash
git add backend/app/core/llm.py
git commit -m "feat(prd): add split LLM functions generate_prd_requirements/markdown/backlog"
```

---

## Task 4: Write failing tests for the new stream endpoint

**Files:**

- Modify: `backend/tests/test_api_ideas_and_agents.py`

Before implementing the endpoint, write tests that will fail until the endpoint exists.

**Step 1: Find the PRD test class** — search for `class.*Prd` or `post_prd` in the test file to locate the right class.

**Step 2: Add a new test class for PRD stream** — add after the existing PRD test class:

```python
class TestPrdStream(_TestBase):
    """Tests for POST /ideas/{id}/agents/prd/stream SSE endpoint."""

    def setUp(self) -> None:
        super().setUp()
        # Patch all three split LLM calls
        from app.schemas.prd import (
            PRDRequirementsOutput, PRDMarkdownOutput, PRDBacklogOutput,
            PRDRequirement, PRDSection, PRDBacklog, PRDBacklogItem,
        )
        from app.schemas.common import PriorityLevel

        mock_req = PRDRequirementsOutput(requirements=[
            PRDRequirement(
                id="req-001", title="Core Engine", description="Core AI engine",
                rationale="Needed", acceptance_criteria=["AC1", "AC2"],
                source_refs=["step4"],
            )
        ])
        mock_md = PRDMarkdownOutput(
            markdown="# Test PRD\n\nTest content.",
            sections=[PRDSection(id="s1", title="Summary", content="Summary content")],
        )
        mock_bl = PRDBacklogOutput(backlog=PRDBacklog(items=[
            PRDBacklogItem(
                id="bl-001", title="Build Engine", requirement_id="req-001",
                priority="P0", type="epic", summary="Build it",
                acceptance_criteria=["AC1", "AC2"], source_refs=["step4"],
            ),
            PRDBacklogItem(
                id="bl-002", title="Deploy Engine", requirement_id="req-001",
                priority="P1", type="story", summary="Deploy it",
                acceptance_criteria=["AC1", "AC2"], source_refs=["step4"],
            ),
            PRDBacklogItem(
                id="bl-003", title="Test Engine", requirement_id="req-001",
                priority="P1", type="task", summary="Test it",
                acceptance_criteria=["AC1", "AC2"], source_refs=["step4"],
            ),
            PRDBacklogItem(
                id="bl-004", title="Document Engine", requirement_id="req-001",
                priority="P2", type="task", summary="Document it",
                acceptance_criteria=["AC1", "AC2"], source_refs=["step4"],
            ),
            PRDBacklogItem(
                id="bl-005", title="Monitor Engine", requirement_id="req-001",
                priority="P2", type="task", summary="Monitor it",
                acceptance_criteria=["AC1", "AC2"], source_refs=["step4"],
            ),
            PRDBacklogItem(
                id="bl-006", title="Optimize Engine", requirement_id="req-001",
                priority="P2", type="task", summary="Optimize it",
                acceptance_criteria=["AC1", "AC2"], source_refs=["step4"],
            ),
            PRDBacklogItem(
                id="bl-007", title="Scale Engine", requirement_id="req-001",
                priority="P2", type="task", summary="Scale it",
                acceptance_criteria=["AC1", "AC2"], source_refs=["step4"],
            ),
            PRDBacklogItem(
                id="bl-008", title="Secure Engine", requirement_id="req-001",
                priority="P2", type="task", summary="Secure it",
                acceptance_criteria=["AC1", "AC2"], source_refs=["step4"],
            ),
        ]))

        self._patch_req = patch("app.core.llm.generate_prd_requirements", return_value=mock_req)
        self._patch_md = patch("app.core.llm.generate_prd_markdown", return_value=mock_md)
        self._patch_bl = patch("app.core.llm.generate_prd_backlog", return_value=mock_bl)
        self._patch_req.start()
        self._patch_md.start()
        self._patch_bl.start()

    def tearDown(self) -> None:
        self._patch_req.stop()
        self._patch_md.stop()
        self._patch_bl.stop()
        super().tearDown()

    def _setup_ready_idea(self) -> tuple[str, str]:
        """Create idea through all steps up to frozen scope, return (idea_id, baseline_id)."""
        # (copy setup logic from existing TestPrdAgent._setup_ready_idea if it exists,
        #  or create a helper that does: create idea → set context → freeze scope)
        # ... implementation depends on existing test helpers ...
        pass

    def test_prd_stream_emits_requirements_then_backlog_then_done(self) -> None:
        idea_id, baseline_id = self._setup_ready_idea()
        # POST to stream endpoint, collect SSE events
        with self.client.stream(
            "POST",
            f"/ideas/{idea_id}/agents/prd/stream",
            json={"baseline_id": baseline_id, "version": 1},
            headers=self._auth_headers(),
        ) as resp:
            self.assertEqual(resp.status_code, 200)
            events = list(_collect_sse_events(resp))

        event_types = [e["event"] for e in events]
        self.assertIn("requirements", event_types)
        self.assertIn("backlog", event_types)
        self.assertIn("done", event_types)
        self.assertNotIn("error", event_types)

        # requirements event has full list
        req_event = next(e for e in events if e["event"] == "requirements")
        self.assertGreaterEqual(len(req_event["data"]["requirements"]), 1)

        # backlog event has full list
        bl_event = next(e for e in events if e["event"] == "backlog")
        self.assertGreaterEqual(len(bl_event["data"]["items"]), 1)
```

Also add a helper at module level (near other helpers):

```python
def _collect_sse_events(response) -> list[dict]:
    """Parse SSE response body into list of {event, data} dicts."""
    import json as _json
    events = []
    current_event = "message"
    for line in response.iter_lines():
        line = line.strip()
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            raw = line[len("data:"):].strip()
            try:
                data = _json.loads(raw)
            except Exception:
                data = raw
            events.append({"event": current_event, "data": data})
            current_event = "message"
    return events
```

**Step 3: Run tests to confirm they FAIL** (endpoint doesn't exist yet):

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=AIHackathon20250225! \
  PYTHONPATH=. .venv/bin/pytest tests/ -k "TestPrdStream" -v --tb=short
```

Expected: FAIL with 404 or attribute errors.

**Step 4: Commit the failing tests**

```bash
git add backend/tests/test_api_ideas_and_agents.py
git commit -m "test(prd): add failing tests for prd/stream SSE endpoint"
```

---

## Task 5: Implement the stream endpoint

**Files:**

- Modify: `backend/app/routes/idea_agents.py`

**Step 1: Add the new endpoint after `post_prd` (around line 244)**

```python
@router.post("/prd/stream")
async def stream_prd(idea_id: str, payload: PRDIdeaRequest) -> EventSourceResponse:
    """Two-stage parallel PRD generation over SSE.

    Stage A (parallel): requirements + markdown/sections
    Stage B (sequential after A): backlog items (needs requirement IDs)
    SSE events: progress → requirements → progress → backlog → done | error
    """
    _logger.info(
        "agent.prd.stream.start idea_id=%s version=%s baseline_id=%s",
        idea_id, payload.version, payload.baseline_id,
    )

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        yield _sse_event("progress", {"step": "validating", "pct": 5})

        # ── Validate idea & build context pack ──────────────────────────────
        idea = _repo.get_idea(idea_id)
        if idea is None:
            yield _sse_event("error", {"code": "IDEA_NOT_FOUND", "message": "Idea not found"})
            return
        if idea.status == "archived":
            yield _sse_event("error", {"code": "IDEA_ARCHIVED", "message": "Idea is archived"})
            return
        if idea.version != payload.version:
            yield _sse_event("error", {
                "code": "IDEA_VERSION_CONFLICT",
                "message": f"Version conflict: expected {idea.version}, got {payload.version}",
            })
            return

        try:
            pack = _build_prd_context_pack(
                idea_id=idea_id,
                baseline_id=payload.baseline_id,
                context=parse_context_strict(idea.context),
            )
        except HTTPException as exc:
            yield _sse_event("error", {
                "code": _http_error_code(exc),
                "message": str(exc.detail),
            })
            return

        slim_ctx = llm._build_slim_prd_context(pack)
        fingerprint = _context_pack_fingerprint(pack)

        # ── Stage A: parallel requirements + markdown ────────────────────────
        yield _sse_event("progress", {"step": "generating_requirements", "pct": 15})

        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_req = loop.run_in_executor(pool, llm.generate_prd_requirements, slim_ctx)
            fut_md = loop.run_in_executor(pool, llm.generate_prd_markdown, slim_ctx)
            try:
                req_result, md_result = await asyncio.gather(fut_req, fut_md)
            except Exception as exc:
                _raise_if_no_provider(exc)
                _logger.exception("agent.prd.stream.stage_a_failed idea_id=%s", idea_id)
                yield _sse_event("error", {
                    "code": "PRD_GENERATION_FAILED",
                    "message": "Failed to generate requirements or markdown.",
                })
                return

        # Emit requirements immediately — frontend can render them while backlog loads
        yield _sse_event("requirements", {
            "requirements": [r.model_dump() for r in req_result.requirements],
        })
        yield _sse_event("progress", {"step": "generating_backlog", "pct": 60})

        # ── Stage B: backlog (needs requirement IDs from Stage A) ────────────
        requirement_ids = [r.id for r in req_result.requirements]
        try:
            bl_result = await loop.run_in_executor(
                None, llm.generate_prd_backlog, slim_ctx, requirement_ids
            )
        except Exception as exc:
            _raise_if_no_provider(exc)
            _logger.exception("agent.prd.stream.stage_b_failed idea_id=%s", idea_id)
            yield _sse_event("error", {
                "code": "PRD_GENERATION_FAILED",
                "message": "Failed to generate backlog.",
            })
            return

        yield _sse_event("backlog", {
            "items": [item.model_dump() for item in bl_result.backlog.items],
        })
        yield _sse_event("progress", {"step": "saving", "pct": 90})

        # ── Merge into PRDOutput and persist ─────────────────────────────────
        from app.schemas.prd import PRDGenerationMeta
        provider = llm._get_active_provider_info()
        merged_output = PRDOutput(
            markdown=md_result.markdown,
            sections=md_result.sections,
            requirements=req_result.requirements,
            backlog=bl_result.backlog,
            generation_meta=PRDGenerationMeta(
                provider_id=provider["id"],
                model=provider["model"],
                confirmed_path_id=pack.step2_path.path_id,
                selected_plan_id=pack.step3_feasibility.selected_plan.id,
                baseline_id=payload.baseline_id,
            ),
        )
        bundle = PrdBundle(
            baseline_id=payload.baseline_id,
            context_fingerprint=fingerprint,
            generated_at=utc_now_iso(),
            generation_meta=merged_output.generation_meta,
            output=merged_output,
        )
        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            mutate_context=lambda ctx: _apply_prd(ctx, pack, bundle),
        )
        error_payload = _sse_error_payload(result)
        if error_payload is not None:
            _logger.warning(
                "agent.prd.stream.failed idea_id=%s version=%s code=%s",
                idea_id, payload.version, error_payload.get("code"),
            )
            yield _sse_event("error", error_payload)
            return

        assert result.idea is not None
        _logger.info(
            "agent.prd.stream.done idea_id=%s idea_version=%s",
            idea_id, result.idea.version,
        )
        yield _sse_event("done", {
            "idea_id": idea_id,
            "idea_version": result.idea.version,
            "generation_meta": merged_output.generation_meta.model_dump(),
        })

    return EventSourceResponse(event_generator())
```

**Step 2: Add `_get_active_provider_info` helper to `llm.py`** — a thin wrapper that exposes provider metadata without leaking the full config object:

```python
def _get_active_provider_info() -> dict[str, str | None]:
    """Return {id, model} of the active provider for generation_meta."""
    provider = ai_gateway._get_active_provider()
    return {"id": provider.id, "model": provider.model}
```

**Step 3: Run the failing tests — they should now pass**

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor/backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=AIHackathon20250225! \
  PYTHONPATH=. .venv/bin/pytest tests/ -k "TestPrdStream" -v --tb=short
```

Expected: PASS.

**Step 4: Run full test suite**

```bash
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=AIHackathon20250225! \
  PYTHONPATH=. .venv/bin/pytest tests/ -v --tb=short -q
```

Expected: all pass.

**Step 5: Commit**

```bash
git add backend/app/routes/idea_agents.py backend/app/core/llm.py
git commit -m "feat(prd): add /agents/prd/stream SSE endpoint with two-stage parallel generation"
```

---

## Task 6: Frontend — switch PrdPage to SSE stream

**Files:**

- Modify: `frontend/components/prd/PrdPage.tsx`

**Step 1: Add partial state types at the top of the component**

Add after existing imports:

```typescript
type PrdStreamPartials = {
  requirements: PrdOutput['requirements'] | null
  backlog: PrdOutput['backlog'] | null
}
```

**Step 2: Add state for partial results** inside `PrdPage`:

```typescript
const [streamPartials, setStreamPartials] = useState<PrdStreamPartials>({
  requirements: null,
  backlog: null,
})
```

**Step 3: Replace the `postIdeaScopedAgent` call with `streamPost`**

Replace the `run` async function inside the `useEffect` (lines ~102-146):

```typescript
const run = async () => {
  // Reset partials for fresh generation
  setStreamPartials({ requirements: null, backlog: null })
  try {
    let donePayload: unknown = null
    await streamPost(
      `/ideas/${activeIdeaId}/agents/prd/stream`,
      { baseline_id: baselineId, version: activeIdea.version },
      {
        onEvent: (event) => {
          if (cancelled) return
          if (event.event === 'requirements') {
            const data = event.data as { requirements: PrdOutput['requirements'] }
            setStreamPartials((prev) => ({ ...prev, requirements: data.requirements }))
          } else if (event.event === 'backlog') {
            const data = event.data as { items: PrdOutput['backlog']['items'] }
            setStreamPartials((prev) => ({ ...prev, backlog: { items: data.items } }))
          } else if (event.event === 'done') {
            donePayload = event.data
          }
        },
      }
    )
    if (!cancelled && donePayload) {
      const envelope = donePayload as {
        idea_id: string
        idea_version: number
        generation_meta: unknown
      }
      setIdeaVersion(activeIdeaId, envelope.idea_version)
      const detail = await loadIdeaDetail(activeIdeaId)
      if (detail) {
        replaceContext(detail.context)
      }
      setRetryNonce(0)
      setStreamPartials({ requirements: null, backlog: null })
    }
  } catch (error) {
    if (inFlightGenerationKeyRef.current === requestKey) {
      inFlightGenerationKeyRef.current = null
    }
    if (!cancelled) {
      const message = error instanceof Error ? error.message : 'Request failed. Please try again.'
      setErrorMessage(message)
      toast.error(message)
    }
  } finally {
    if (inFlightGenerationKeyRef.current === requestKey) {
      inFlightGenerationKeyRef.current = null
    }
    globalPrdGenerationRequests.delete(requestKey)
    if (!cancelled) {
      setLoading(false)
    }
  }
}
```

**Step 4: Add `streamPost` import**

Change:

```typescript
import { ApiError, postIdeaScopedAgent, postPrdFeedback } from '../../lib/api'
```

To:

```typescript
import { ApiError, postPrdFeedback } from '../../lib/api'
import { streamPost } from '../../lib/sse'
```

**Step 5: Pass `streamPartials` down to `PrdView`**

Update the JSX:

```tsx
<PrdView
  prd={context.prd_bundle?.output ?? context.prd}
  bundle={context.prd_bundle}
  streamPartials={loading ? streamPartials : null}
  ...rest unchanged...
/>
```

**Step 6: Update `PrdView` props to accept `streamPartials`**

In `frontend/components/prd/PrdView.tsx`, add to the props type:

```typescript
streamPartials?: PrdStreamPartials | null
```

And in the requirements/backlog display sections, when `streamPartials` is set, render streamed data with a "generating..." indicator for the part not yet arrived.

**Step 7: Check TypeScript compiles**

```bash
cd /Users/efan404/Codes/indie_dev/pm-cursor
pnpm exec tsc --noEmit --project frontend/tsconfig.json
```

Expected: no errors.

**Step 8: Manual smoke test via Playwright**

- Navigate to `http://localhost:3001`
- Log in as `test / test`
- Open an existing idea with frozen scope (or create new one)
- Go to Step 5 PRD
- Observe: requirements section populates ~15s before backlog section appears
- Both sections eventually fill in, "Generating PRD and backlog…" disappears

**Step 9: Commit**

```bash
git add frontend/components/prd/PrdPage.tsx frontend/components/prd/PrdView.tsx
git commit -m "feat(prd): switch frontend to SSE stream with progressive requirements/backlog rendering"
```

---

## Task 7: Push and verify CI

**Step 1: Push**

```bash
git push origin main
```

**Step 2: Check CI**

```bash
gh run list --limit 3
gh run watch  # or check GitHub Actions tab
```

Expected: Backend tests pass, Frontend type-check + build pass.

**Step 3: If CI fails** — check `gh run view <run-id> --log-failed` and fix.

---

## Summary of SSE Events

```
POST /ideas/{id}/agents/prd/stream

event: progress     {"step": "validating", "pct": 5}
event: progress     {"step": "generating_requirements", "pct": 15}
event: requirements {"requirements": [...]}          ← Stage A done: frontend renders requirements
event: progress     {"step": "generating_backlog", "pct": 60}
event: backlog      {"items": [...]}                 ← Stage B done: frontend renders backlog
event: progress     {"step": "saving", "pct": 90}
event: done         {"idea_id": "...", "idea_version": N, "generation_meta": {...}}

On error at any stage:
event: error        {"code": "...", "message": "..."}
```

## Timing Improvement

| Before                                 | After                                               |
| -------------------------------------- | --------------------------------------------------- |
| Single LLM call, ~30-60s, blank screen | Stage A parallel: ~15-25s until requirements appear |
| User sees nothing until complete       | Stage B: backlog arrives ~10-15s after requirements |
| Timeout risk on large outputs          | Smaller per-call outputs → less truncation risk     |
