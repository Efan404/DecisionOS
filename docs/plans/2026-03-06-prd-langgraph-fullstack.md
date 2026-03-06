# PRD LangGraph Full-Stack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current single-LLM-call PRD generation with a proper LangGraph graph that runs requirements + markdown in true parallel fan-out, then generates backlog after fan-in, streams every node transition as SSE events, and re-enables the Requirements/Backlog/Sections tabs on the frontend.

**Architecture:**
The new `stream_prd` endpoint builds a `DecisionOSState` (the **same shared state class** used by opportunity, feasibility, and scope subgraphs — do NOT introduce a new `PrdLangGraphState`), compiles `build_prd_graph()`, and calls `.astream(state, stream_mode="updates")`. Each node update is translated to an SSE event (`agent_thought`, `requirements`, `backlog`, `progress`, `done`). The graph uses LangGraph's `Send` API for true parallel fan-out of the requirements and markdown writer nodes, then a reducer fan-in before the backlog node fires.

**State design decision — DecisionOSState, not a separate PrdLangGraphState:**
All idea-workflow subgraphs (opportunity, feasibility, prd) share `DecisionOSState` so nodes like `context_loader_node` and `memory_writer_node` can be reused without adapter code. Proactive agents (`PatternLearnerState`, `CrossIdeaState`, `NewsMonitorState`) use their own state types because they are cross-user/cross-idea and have no overlap with the per-idea workflow. PRD fits the per-idea pattern — use `DecisionOSState`, extend it with the new typed fields listed in Task 1.

**No SqliteSaver / no checkpoint resume in this plan:**
`SqliteSaver` requires a defined `thread_id` strategy, a `resume` entry point, and alignment with `idea.version` CAS — none of which are specified here. The graph runs as a one-shot `.astream()` call. Checkpointing can be added in a future plan once the thread_id/resume contract is defined.

**SSE event structure — must align with existing frontend handler:**
The existing frontend SSE handler in `PrdPage` already processes `progress`, `agent_thought`, and `done` events. The new events `requirements` (payload: `{ requirements: [...] }`) and `backlog` (payload: `{ items: [...] }`) are **additive** — the frontend handler is extended in Task 6 (Step 8) to handle them. Do not rename or restructure existing event types.

**Tab restoration order — backend contract must be verified first:**
Restore frontend tabs (Task 6) only after backend tests pass (Task 5). Do not restore tabs until `requirements` and `backlog` SSE events are confirmed working in LLM mock mode.

**Tech Stack:** Python 3.12, LangGraph ≥0.3, FastAPI SSE via `sse_starlette`, asyncio, Next.js 14 App Router, React, TypeScript.

**Key files to understand before starting:**

- `backend/app/agents/graphs/prd_subgraph.py` — existing partial graph (needs full rewrite)
- `backend/app/agents/state.py` — `DecisionOSState` (needs new fields)
- `backend/app/routes/idea_agents.py:536-684` — current `stream_prd` route (needs replacement)
- `backend/app/core/llm.py:125-166` — `generate_prd_requirements`, `generate_prd_markdown`, `generate_prd_backlog`
- `backend/app/schemas/prd.py` — `PRDRequirementsOutput`, `PRDMarkdownOutput`, `PRDBacklogOutput`, `PRDOutput`
- `frontend/components/prd/PrdView.tsx` — all three tabs are commented out, need to be restored
- `frontend/components/prd/PrdBacklogPanel.tsx` — already complete, just needs to be re-imported
- `frontend/lib/schemas.ts:172-420` — Zod schemas for PRD types (already complete)

---

## Task 1: Extend DecisionOSState with PRD-specific fields

**Files:**

- Modify: `backend/app/agents/state.py`

The current `DecisionOSState` has `prd_output: dict | None` as a generic dict. We need typed fields for the three parallel-stage outputs and a review result.

**Step 1: Read the file**

```bash
cat backend/app/agents/state.py
```

**Step 2: Replace the file content**

The new state adds four fields after `prd_output`:

- `prd_requirements: list[dict]` — populated by the requirements writer node
- `prd_sections: list[dict]` — populated by the markdown writer node
- `prd_markdown: str` — populated by the markdown writer node
- `prd_backlog_items: list[dict]` — populated by the backlog writer node
- `prd_review_issues: list[str]` — populated by the reviewer node

```python
# backend/app/agents/state.py
from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class AgentThought(TypedDict):
    agent: str
    action: str
    detail: str
    timestamp: str


class DecisionOSState(TypedDict):
    idea_id: str
    idea_seed: str
    current_stage: str
    opportunity_output: dict | None
    dag_path: dict | None
    feasibility_output: dict | None
    selected_plan_id: str | None
    scope_output: dict | None
    # Generic PRD output dict (stored in DB context_json as before)
    prd_output: dict | None
    # Typed intermediate PRD fields populated by the graph nodes
    prd_slim_context: dict | None        # built once in context_loader, shared by all writers
    prd_requirements: list[dict]          # from requirements_writer node
    prd_markdown: str                     # from markdown_writer node
    prd_sections: list[dict]              # from markdown_writer node
    prd_backlog_items: list[dict]         # from backlog_writer node
    prd_review_issues: list[str]          # from reviewer node
    agent_thoughts: Annotated[list[AgentThought], operator.add]
    retrieved_patterns: list[dict]
    retrieved_similar_ideas: list[dict]
    user_preferences: dict | None
```

**Step 3: Run tests to verify nothing broken**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all pass (state is a TypedDict, no runtime breakage).

**Step 4: Commit**

```bash
git add backend/app/agents/state.py
git commit -m "feat(prd-graph): extend DecisionOSState with typed PRD intermediate fields"
```

---

## Task 2: Rewrite prd_subgraph.py with LangGraph fan-out

**Files:**

- Modify: `backend/app/agents/graphs/prd_subgraph.py`

This is the core architectural change. The graph topology is:

```
START
  └─► context_loader          (loads vector memory + builds slim_context)
        ├─► requirements_writer  (parallel, via Send)
        └─► markdown_writer      (parallel, via Send)
              fan-in (both write to state via reducer)
        └─► backlog_writer       (sequential, reads requirement IDs)
              └─► prd_reviewer   (checks scope coverage)
                    └─► memory_writer  (writes idea summary to vector store)
                          └─► END
```

LangGraph parallel fan-out uses a conditional edge that emits two `Send` objects pointing to the same or different nodes. Both nodes run concurrently. The fan-in happens naturally when both branches write to state fields that are merged.

**Step 1: Write the new prd_subgraph.py**

```python
# backend/app/agents/graphs/prd_subgraph.py
from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.agents.state import DecisionOSState, AgentThought
from app.agents.nodes.context_loader import context_loader_node
from app.agents.nodes.memory_writer import memory_writer_node
from app.core import ai_gateway, prompts
from app.core.time import utc_now_iso
from app.schemas.prd import PRDRequirementsOutput, PRDMarkdownOutput, PRDBacklogOutput

logger = logging.getLogger(__name__)


# ── Node: requirements_writer ─────────────────────────────────────────────────

def _requirements_writer_node(state: DecisionOSState) -> dict[str, object]:
    """Stage-A parallel: generate 6-12 structured requirements."""
    slim_ctx = state.get("prd_slim_context") or {}
    similar = state.get("retrieved_similar_ideas", [])
    patterns = state.get("retrieved_patterns", [])

    prompt = prompts.build_prd_requirements_prompt(context=slim_ctx)
    if patterns:
        prompt += "\n\nUser decision patterns:\n" + "\n".join(
            f"- {p.get('description', '')[:120]}" for p in patterns[:2]
        )

    result: PRDRequirementsOutput = ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompt,
        schema_model=PRDRequirementsOutput,
    )

    thought: AgentThought = {
        "agent": "requirements_writer",
        "action": "generated_requirements",
        "detail": f"Generated {len(result.requirements)} requirements",
        "timestamp": utc_now_iso(),
    }
    return {
        "prd_requirements": [r.model_dump() for r in result.requirements],
        "agent_thoughts": [thought],
    }


# ── Node: markdown_writer ─────────────────────────────────────────────────────

def _markdown_writer_node(state: DecisionOSState) -> dict[str, object]:
    """Stage-A parallel: generate full markdown narrative + sections."""
    slim_ctx = state.get("prd_slim_context") or {}
    similar = state.get("retrieved_similar_ideas", [])

    prompt = prompts.build_prd_markdown_prompt(context=slim_ctx)
    if similar:
        prompt += "\n\nSimilar past ideas for reference:\n" + "\n".join(
            f"- {s.get('summary', '')[:100]}" for s in similar[:2]
        )

    result: PRDMarkdownOutput = ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompt,
        schema_model=PRDMarkdownOutput,
    )

    thought: AgentThought = {
        "agent": "markdown_writer",
        "action": "generated_markdown",
        "detail": f"Generated PRD markdown ({len(result.markdown)} chars, {len(result.sections)} sections)",
        "timestamp": utc_now_iso(),
    }
    return {
        "prd_markdown": result.markdown,
        "prd_sections": [s.model_dump() for s in result.sections],
        "agent_thoughts": [thought],
    }


# ── Node: backlog_writer ──────────────────────────────────────────────────────

def _backlog_writer_node(state: DecisionOSState) -> dict[str, object]:
    """Stage-B sequential: generate backlog items that reference requirement IDs."""
    slim_ctx = state.get("prd_slim_context") or {}
    requirements = state.get("prd_requirements", [])
    requirement_ids = [r.get("id", "") for r in requirements if r.get("id")]

    if not requirement_ids:
        thought: AgentThought = {
            "agent": "backlog_writer",
            "action": "skipped",
            "detail": "No requirement IDs available — skipping backlog generation",
            "timestamp": utc_now_iso(),
        }
        return {"prd_backlog_items": [], "agent_thoughts": [thought]}

    result: PRDBacklogOutput = ai_gateway.generate_structured(
        task="prd",
        user_prompt=prompts.build_prd_backlog_prompt(
            context=slim_ctx, requirement_ids=requirement_ids
        ),
        schema_model=PRDBacklogOutput,
    )

    thought: AgentThought = {
        "agent": "backlog_writer",
        "action": "generated_backlog",
        "detail": f"Generated {len(result.backlog.items)} backlog items",
        "timestamp": utc_now_iso(),
    }
    return {
        "prd_backlog_items": [item.model_dump() for item in result.backlog.items],
        "agent_thoughts": [thought],
    }


# ── Node: prd_reviewer ────────────────────────────────────────────────────────

def _prd_reviewer_node(state: DecisionOSState) -> dict[str, object]:
    """Quality review: check scope coverage and requirement count."""
    markdown = state.get("prd_markdown", "")
    requirements = state.get("prd_requirements", [])
    scope = state.get("scope_output") or {}
    in_scope = scope.get("in_scope", [])

    issues: list[str] = []
    if len(markdown) < 200:
        issues.append("PRD markdown is unusually short (<200 chars)")
    if len(requirements) < 4:
        issues.append(f"Too few requirements: {len(requirements)} (expected ≥6)")
    if in_scope:
        scope_titles = {item.get("title", "").lower() for item in in_scope if isinstance(item, dict)}
        md_lower = markdown.lower()
        missing = [t for t in scope_titles if t and t not in md_lower]
        if missing:
            issues.append(f"{len(missing)} scope items not mentioned in PRD: {', '.join(missing[:3])}")

    detail = (
        f"Review found {len(issues)} issues: {'; '.join(issues)}"
        if issues
        else f"PRD passed quality review: {len(requirements)} requirements, all scope items covered"
    )
    thought: AgentThought = {
        "agent": "prd_reviewer",
        "action": "quality_review",
        "detail": detail,
        "timestamp": utc_now_iso(),
    }
    return {"prd_review_issues": issues, "agent_thoughts": [thought]}


# ── Fan-out router ────────────────────────────────────────────────────────────

def _fan_out_to_parallel_writers(state: DecisionOSState) -> list[Send]:
    """After context_loader: dispatch requirements_writer and markdown_writer in parallel."""
    return [
        Send("requirements_writer", state),
        Send("markdown_writer", state),
    ]


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_prd_graph() -> object:
    """
    PRD graph topology:
        START → context_loader
                  ├─(Send)→ requirements_writer ─┐
                  └─(Send)→ markdown_writer      ─┤ (fan-in)
                                                  └─► backlog_writer
                                                          └─► prd_reviewer
                                                                  └─► memory_writer → END
    """
    graph = StateGraph(DecisionOSState)

    graph.add_node("context_loader", context_loader_node)
    graph.add_node("requirements_writer", _requirements_writer_node)
    graph.add_node("markdown_writer", _markdown_writer_node)
    graph.add_node("backlog_writer", _backlog_writer_node)
    graph.add_node("prd_reviewer", _prd_reviewer_node)
    graph.add_node("memory_writer", memory_writer_node)

    # context_loader fans out to parallel writers
    graph.add_edge(START, "context_loader")
    graph.add_conditional_edges("context_loader", _fan_out_to_parallel_writers, ["requirements_writer", "markdown_writer"])

    # Both parallel branches feed into backlog_writer (fan-in via state merge)
    graph.add_edge("requirements_writer", "backlog_writer")
    graph.add_edge("markdown_writer", "backlog_writer")

    graph.add_edge("backlog_writer", "prd_reviewer")
    graph.add_edge("prd_reviewer", "memory_writer")
    graph.add_edge("memory_writer", END)

    return graph.compile()
```

**Step 2: Run the PRD graph test (write a quick smoke test first)**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/python -c "
from app.agents.graphs.prd_subgraph import build_prd_graph
g = build_prd_graph()
print('Graph compiled OK, nodes:', list(g.nodes))
"
```

Expected: prints node names without ImportError.

**Step 3: Run all tests to check no regression**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_prd_graph.py -v --tb=short
```

Expected: existing tests pass.

**Step 4: Commit**

```bash
git add backend/app/agents/graphs/prd_subgraph.py
git commit -m "feat(prd-graph): rewrite with LangGraph fan-out (requirements+markdown parallel, backlog sequential)"
```

---

## Task 3: Update context_loader_node to build prd_slim_context

**Files:**

- Modify: `backend/app/agents/nodes/context_loader.py`

The context_loader currently retrieves vector memory. We need it to also build `prd_slim_context` when `current_stage == "prd"`, so the parallel writer nodes don't each have to re-derive it.

**Step 1: Read existing context_loader**

```bash
cat backend/app/agents/nodes/context_loader.py
```

**Step 2: Add slim_context building to context_loader_node**

```python
# backend/app/agents/nodes/context_loader.py
from __future__ import annotations

from datetime import datetime, timezone

from app.agents.memory.vector_store import get_vector_store
from app.agents.state import AgentThought, DecisionOSState
from app.core import llm as llm_module


def context_loader_node(state: DecisionOSState) -> dict[str, object]:
    """Load similar ideas and decision patterns from vector memory.
    When stage is 'prd', also build the slim context dict shared by writer nodes.
    """
    idea_seed = state["idea_seed"]
    idea_id = state["idea_id"]
    stage = state.get("current_stage", "")

    vs = get_vector_store()
    similar_ideas = vs.search_similar_ideas(query=idea_seed, n_results=3, exclude_id=idea_id)
    patterns = vs.search_patterns(query=idea_seed, n_results=3)

    updates: dict[str, object] = {
        "retrieved_similar_ideas": similar_ideas,
        "retrieved_patterns": patterns,
    }

    # Build slim PRD context once so parallel writer nodes share it
    if stage == "prd":
        dag_path = state.get("dag_path") or {}
        feasibility = state.get("feasibility_output") or {}
        scope = state.get("scope_output") or {}
        selected_plan_id = state.get("selected_plan_id", "")
        plans = feasibility.get("plans", [])
        selected_plan = next(
            (p for p in plans if p.get("id") == selected_plan_id),
            plans[0] if plans else {},
        )
        slim_ctx = {
            "idea_seed": idea_seed,
            "confirmed_path_summary": dag_path.get("path_summary", ""),
            "leaf_node_content": dag_path.get("leaf_node_content", idea_seed),
            "selected_plan": {
                "name": selected_plan.get("name", ""),
                "summary": selected_plan.get("summary", ""),
                "score_overall": selected_plan.get("score_overall", 0),
                "recommended_positioning": selected_plan.get("recommended_positioning", ""),
            },
            "in_scope": scope.get("in_scope", []),
            "out_scope": scope.get("out_scope", []),
        }
        updates["prd_slim_context"] = slim_ctx

    thought: AgentThought = {
        "agent": "context_loader",
        "action": "memory_retrieval",
        "detail": (
            f"Retrieved {len(similar_ideas)} similar ideas and "
            f"{len(patterns)} decision patterns from vector memory."
            + (f" Built PRD slim context for stage '{stage}'." if stage == "prd" else "")
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    updates["agent_thoughts"] = [thought]
    return updates
```

**Step 3: Run tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all pass.

**Step 4: Commit**

```bash
git add backend/app/agents/nodes/context_loader.py
git commit -m "feat(prd-graph): context_loader builds prd_slim_context for parallel writers"
```

---

## Task 4: Rewrite stream_prd route to use LangGraph astream

**Files:**

- Modify: `backend/app/routes/idea_agents.py` (function `stream_prd` at line ~536)

The new implementation:

1. Builds `DecisionOSState` from the same `PrdContextPack` as before
2. Calls `graph.astream(state, stream_mode="updates")` (async generator)
3. Translates each node's `agent_thoughts` update into `agent_thought` SSE events
4. Translates `prd_requirements` update into a `requirements` SSE event
5. Translates `prd_backlog_items` update into a `backlog` SSE event
6. After graph completes, assembles `PRDOutput`, saves to DB, emits `done`

**Step 1: Read the current stream_prd function**

```bash
sed -n '536,684p' backend/app/routes/idea_agents.py
```

**Step 2: Replace the stream_prd function body**

Locate the function at line ~537 (`async def stream_prd`) and replace its body:

```python
@router.post("/prd/stream")
async def stream_prd(idea_id: str, payload: PRDIdeaRequest) -> EventSourceResponse:
    """LangGraph PRD generation over SSE.

    Graph: context_loader → [requirements_writer ‖ markdown_writer] → backlog_writer → prd_reviewer → memory_writer
    SSE events: agent_thought | requirements | backlog | progress | done | error
    """
    _logger.info(
        "agent.prd.stream.start idea_id=%s version=%s baseline_id=%s",
        idea_id, payload.version, payload.baseline_id,
    )

    from app.agents.graphs.prd_subgraph import build_prd_graph

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        yield _sse_event("progress", {"step": "validating", "pct": 5})

        # ── Validation (same as before) ───────────────────────────────────────
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
            detail = exc.detail
            code = detail.get("code", "ERROR") if isinstance(detail, dict) else "ERROR"
            message = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
            yield _sse_event("error", {"code": code, "message": message})
            return

        fingerprint = _context_pack_fingerprint(pack)
        yield _sse_event("progress", {"step": "building_context", "pct": 10})

        # ── Build LangGraph state from PrdContextPack ─────────────────────────
        from app.agents.state import DecisionOSState
        selected_plan = pack.step3_feasibility.selected_plan
        initial_state: DecisionOSState = {
            "idea_id": idea_id,
            "idea_seed": pack.idea_seed,
            "current_stage": "prd",
            "opportunity_output": None,
            "dag_path": {
                "path_summary": pack.step2_path.path_summary,
                "leaf_node_content": pack.step2_path.leaf_node_content,
            },
            "feasibility_output": {
                "plans": [
                    {
                        "id": selected_plan.id,
                        "name": selected_plan.name,
                        "summary": selected_plan.summary,
                        "score_overall": selected_plan.score_overall,
                        "recommended_positioning": selected_plan.recommended_positioning,
                    }
                ]
            },
            "selected_plan_id": selected_plan.id,
            "scope_output": {
                "in_scope": [item.model_dump() for item in pack.step4_scope.in_scope],
                "out_scope": [item.model_dump() for item in pack.step4_scope.out_scope],
            },
            "prd_output": None,
            "prd_slim_context": None,
            "prd_requirements": [],
            "prd_markdown": "",
            "prd_sections": [],
            "prd_backlog_items": [],
            "prd_review_issues": [],
            "agent_thoughts": [],
            "retrieved_patterns": [],
            "retrieved_similar_ideas": [],
            "user_preferences": None,
        }

        yield _sse_event("progress", {"step": "running_graph", "pct": 15})

        # ── Stream LangGraph node updates ─────────────────────────────────────
        try:
            graph = build_prd_graph()
            final_state: DecisionOSState | None = None

            loop = asyncio.get_running_loop()

            # LangGraph's astream yields {node_name: state_updates} dicts
            async for chunk in graph.astream(initial_state, stream_mode="updates"):
                for node_name, updates in chunk.items():
                    if not isinstance(updates, dict):
                        continue

                    # Emit each agent thought as a dedicated SSE event
                    for thought in updates.get("agent_thoughts", []):
                        yield _sse_agent_thought(
                            thought.get("agent", node_name),
                            thought.get("detail", ""),
                        )

                    # Emit requirements as soon as they're ready (progressive render)
                    if "prd_requirements" in updates and updates["prd_requirements"]:
                        yield _sse_event("requirements", {
                            "requirements": updates["prd_requirements"]
                        })
                        yield _sse_event("progress", {"step": "requirements_done", "pct": 45})

                    # Emit backlog as soon as it's ready
                    if "prd_backlog_items" in updates and updates["prd_backlog_items"]:
                        yield _sse_event("backlog", {
                            "items": updates["prd_backlog_items"]
                        })
                        yield _sse_event("progress", {"step": "backlog_done", "pct": 75})

                    # Track final state accumulation
                    if final_state is None:
                        final_state = dict(initial_state)  # type: ignore[assignment]
                    for k, v in updates.items():
                        if k == "agent_thoughts":
                            final_state["agent_thoughts"] = (  # type: ignore[index]
                                list(final_state.get("agent_thoughts", [])) + list(v)  # type: ignore[call-overload]
                            )
                        else:
                            final_state[k] = v  # type: ignore[literal-required]

        except Exception as exc:
            _raise_if_no_provider(exc)
            _logger.exception("agent.prd.stream.graph.failed idea_id=%s", idea_id)
            yield _sse_event("error", {
                "code": "PRD_GENERATION_FAILED",
                "message": f"PRD graph failed: {exc}",
            })
            return

        if final_state is None:
            yield _sse_event("error", {"code": "PRD_GENERATION_FAILED", "message": "Graph produced no state"})
            return

        yield _sse_event("progress", {"step": "saving", "pct": 90})

        # ── Assemble PRDOutput from graph's final state ───────────────────────
        from app.schemas.prd import (
            PRDOutput, PRDSection, PRDRequirement, PRDBacklog,
            PRDBacklogItem, PRDGenerationMeta,
        )

        try:
            provider_info = llm._get_active_provider_info()
        except RuntimeError:
            provider_info = {"id": None, "model": None}

        merged_output = PRDOutput(
            markdown=final_state.get("prd_markdown", ""),
            sections=[PRDSection(**s) for s in final_state.get("prd_sections", [])],
            requirements=[PRDRequirement(**r) for r in final_state.get("prd_requirements", [])],
            backlog=PRDBacklog(
                items=[PRDBacklogItem(**item) for item in final_state.get("prd_backlog_items", [])]
            ),
            generation_meta=PRDGenerationMeta(
                provider_id=provider_info.get("id"),
                model=provider_info.get("model"),
                confirmed_path_id=pack.step2_path.path_id,
                selected_plan_id=pack.step3_feasibility.selected_plan.id,
                baseline_id=pack.step4_scope.baseline_meta.baseline_id,
            ),
        )

        bundle = PrdBundle(
            baseline_id=pack.step4_scope.baseline_meta.baseline_id,
            context_fingerprint=fingerprint,
            generated_at=llm.utc_now_iso() if hasattr(llm, "utc_now_iso") else "",
            generation_meta=merged_output.generation_meta,
            output=merged_output,
        )

        context_update = _apply_prd(parse_context_strict(idea.context), pack, bundle)
        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            context_update=context_update,
        )
        if err := _sse_error_payload(result):
            yield _sse_event("error", err)
            return

        yield _sse_event("done", {
            "version": _unwrap_update(result),
            "output": merged_output.model_dump(mode="json"),
        })

    return EventSourceResponse(event_generator())
```

Note: also add `from app.core.time import utc_now_iso` import at the top of `idea_agents.py` if not already present (check line ~1-20).

**Step 3: Run the PRD-specific tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_prd_graph.py tests/test_api_ideas_and_agents.py -v --tb=short 2>&1 | tail -30
```

Expected: all pass. The graph runs in LLM mock mode.

**Step 4: Commit**

```bash
git add backend/app/routes/idea_agents.py
git commit -m "feat(prd-graph): stream_prd now drives LangGraph astream, emits requirements/backlog SSE events"
```

---

## Task 5: Write backend tests for the new graph

**Files:**

- Modify: `backend/tests/test_prd_graph.py`

**Step 1: Read existing test file**

```bash
cat backend/tests/test_prd_graph.py
```

**Step 2: Add tests for fan-out and node isolation**

Add these test cases to the file:

```python
def test_prd_graph_has_expected_nodes():
    """Graph must contain all six nodes."""
    from app.agents.graphs.prd_subgraph import build_prd_graph
    g = build_prd_graph()
    assert "context_loader" in g.nodes
    assert "requirements_writer" in g.nodes
    assert "markdown_writer" in g.nodes
    assert "backlog_writer" in g.nodes
    assert "prd_reviewer" in g.nodes
    assert "memory_writer" in g.nodes


def test_prd_graph_compiles_without_error():
    """build_prd_graph() should not raise."""
    from app.agents.graphs.prd_subgraph import build_prd_graph
    g = build_prd_graph()
    assert g is not None


def test_requirements_writer_node_uses_slim_context(monkeypatch):
    """requirements_writer_node should call generate_structured with requirements schema."""
    from app.agents.graphs import prd_subgraph
    from app.schemas.prd import PRDRequirementsOutput, PRDRequirement

    mock_req = PRDRequirement(
        id="req-001", title="T", description="D", rationale="R",
        acceptance_criteria=["AC1", "AC2"], source_refs=["step2"],
    )
    monkeypatch.setattr(
        "app.agents.graphs.prd_subgraph.ai_gateway.generate_structured",
        lambda **_: PRDRequirementsOutput(requirements=[mock_req] * 6),
    )
    state = {
        "idea_id": "i1", "idea_seed": "test", "current_stage": "prd",
        "prd_slim_context": {"idea_seed": "test", "in_scope": [], "out_scope": []},
        "retrieved_patterns": [], "retrieved_similar_ideas": [],
        "agent_thoughts": [],
    }
    result = prd_subgraph._requirements_writer_node(state)
    assert len(result["prd_requirements"]) == 6
    assert result["prd_requirements"][0]["id"] == "req-001"


def test_backlog_writer_skips_when_no_requirements():
    """backlog_writer should skip gracefully when prd_requirements is empty."""
    from app.agents.graphs.prd_subgraph import _backlog_writer_node
    state = {
        "idea_id": "i1", "idea_seed": "test", "current_stage": "prd",
        "prd_slim_context": {}, "prd_requirements": [], "agent_thoughts": [],
    }
    result = _backlog_writer_node(state)
    assert result["prd_backlog_items"] == []
    assert "skipped" in result["agent_thoughts"][0]["action"]
```

**Step 3: Run the new tests**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/test_prd_graph.py -v --tb=short
```

Expected: all 4 new tests pass.

**Step 4: Commit**

```bash
git add backend/tests/test_prd_graph.py
git commit -m "test(prd-graph): add node isolation and fan-out graph structure tests"
```

---

## Task 6: Frontend — restore Requirements, Sections, Backlog tabs in PrdView

**Files:**

- Modify: `frontend/components/prd/PrdView.tsx`

The frontend already has all the commented-out code. This task un-comments and re-enables it.

**Step 1: Restore the MainTab type**

In `PrdView.tsx` around line 207, replace:

```typescript
// DISABLED: multi-tab type — only markdown tab is active
// type MainTab = 'markdown' | 'requirements' | 'sections'
type MainTab = 'markdown'
```

With:

```typescript
type MainTab = 'markdown' | 'requirements' | 'sections'
```

**Step 2: Restore the requirement selection state (around line 227)**

Replace:

```typescript
// DISABLED: requirement selection state (used by Requirements tab and Backlog panel)
// const [selectedRequirementIdInput, setSelectedRequirementIdInput] = useState<string | null>(null)
const [activeTab, setActiveTab] = useState<MainTab>('markdown')

// DISABLED: requirement selection logic
// const selectedRequirementId = output?.requirements.some(
//   (item) => item.id === selectedRequirementIdInput
// )
//   ? selectedRequirementIdInput
//   : (output?.requirements[0]?.id ?? null)

// DISABLED: requirements lookup map (used by right-column requirement filter)
// const requirementsById = useMemo(
//   () =>
//     Object.fromEntries(
//       (output?.requirements ?? []).map((item) => [item.id, item.title] as const)
//     ),
//   [output]
// )
```

With:

```typescript
const [selectedRequirementIdInput, setSelectedRequirementIdInput] = useState<string | null>(null)
const [activeTab, setActiveTab] = useState<MainTab>('markdown')

const selectedRequirementId = output?.requirements.some(
  (item) => item.id === selectedRequirementIdInput
)
  ? selectedRequirementIdInput
  : (output?.requirements[0]?.id ?? null)

const requirementsById = useMemo(
  () =>
    Object.fromEntries((output?.requirements ?? []).map((item) => [item.id, item.title] as const)),
  [output]
)
```

**Step 3: Restore the tabs array (around line 249)**

Replace:

```typescript
// DISABLED: Requirements and Sections tabs
// const tabs: { id: MainTab; label: string; count?: number }[] = output
//   ? [
//       { id: 'markdown', label: 'PRD' },
//       { id: 'requirements', label: 'Requirements', count: output.requirements.length },
//       { id: 'sections', label: 'Sections', count: output.sections.length },
//     ]
//   : []
const tabs: { id: MainTab; label: string }[] = output ? [{ id: 'markdown', label: 'PRD' }] : []
```

With:

```typescript
const tabs: { id: MainTab; label: string; count?: number }[] = output
  ? [
      { id: 'markdown', label: 'PRD' },
      { id: 'requirements', label: 'Requirements', count: output.requirements.length },
      { id: 'sections', label: 'Sections', count: output.sections.length },
    ]
  : []
```

**Step 4: Restore Requirements tab content (around line 350)**

Replace the entire `{/* DISABLED: Requirements tab content */}` comment block (lines ~350-393) with the uncommented JSX:

```typescript
          {activeTab === 'requirements' ? (
            <ul className="space-y-2">
              {output.requirements.map((item) => {
                const active = selectedRequirementId === item.id
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedRequirementIdInput(item.id)}
                      className={`w-full cursor-pointer rounded-xl border px-4 py-3.5 text-left transition-all duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400 ${
                        active
                          ? 'border-indigo-300 bg-indigo-50 shadow-sm'
                          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <span
                          className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] font-bold ${
                            active ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-500'
                          }`}
                        >
                          {item.id}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm leading-5 font-semibold text-slate-900">{item.title}</p>
                          <p className="mt-1 text-xs leading-5 text-slate-500">{item.description}</p>
                          {item.rationale ? (
                            <p className="mt-1.5 border-l-2 border-slate-200 pl-2 text-xs text-slate-400 italic">
                              {item.rationale}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : null}
```

**Step 5: Restore Sections tab content (around line 397)**

Replace the `{/* DISABLED: Sections tab content */}` block with:

```typescript
          {activeTab === 'sections' ? (
            <ul className="space-y-2">
              {output.sections.map((section, idx) => (
                <li key={section.id} className="rounded-xl border border-slate-200 bg-white px-4 py-4">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 shrink-0 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    <div>
                      <p className="text-xs font-semibold tracking-widest text-slate-500 uppercase">
                        {section.title}
                      </p>
                      <p className="mt-1.5 text-sm leading-6 text-slate-700">{section.content}</p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
```

**Step 6: Restore imports at the top of PrdView.tsx**

Change:

```typescript
import { useState, useCallback } from 'react'
```

To:

```typescript
import { useState, useCallback, useMemo } from 'react'
```

And restore the PrdBacklogPanel and PrdFeedbackCard imports (lines ~15-16):

```typescript
import { PrdBacklogPanel } from './PrdBacklogPanel'
import { PrdFeedbackCard } from './PrdFeedbackCard'
```

**Step 7: Restore right-side column (around line 421)**

Replace the `{/* DISABLED: Right column */}` comment block with:

```typescript
          <div className="space-y-4">
            {selectedRequirementId ? (
              <div className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2">
                <span className="shrink-0 rounded bg-indigo-100 px-1.5 py-0.5 font-mono text-[10px] font-bold text-indigo-700">
                  {selectedRequirementId}
                </span>
                <span className="truncate text-xs text-slate-600">
                  {requirementsById[selectedRequirementId] ?? ''}
                </span>
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-400">
                Select a requirement to filter linked backlog items.
              </p>
            )}
            <PrdBacklogPanel
              items={output.backlog.items}
              selectedRequirementId={selectedRequirementId}
              onSelectRequirement={setSelectedRequirementIdInput}
            />
            {baselineId && onSubmitFeedback ? (
              <PrdFeedbackCard
                key={`${baselineId}:${feedbackLatest?.submitted_at ?? 'draft'}`}
                baselineId={baselineId}
                latest={feedbackLatest}
                disabled={feedbackSubmitting}
                submitting={feedbackSubmitting}
                errorMessage={feedbackError}
                onSubmit={onSubmitFeedback}
              />
            ) : null}
          </div>
```

**Step 8: Update SSE handler in PrdPage to accept new events**

File: `frontend/app/ideas/[ideaId]/prd/page.tsx` (or wherever `streamPost` is called for PRD).

Find the `onEvent` / `onDone` callback and add handlers for `requirements` and `backlog`:

```typescript
// In the streamPost call for PRD:
onEvent: (event: string, data: unknown) => {
  if (event === 'requirements') {
    const d = data as { requirements: PrdRequirement[] }
    setStreamPartials((prev) => ({ ...prev, requirements: d.requirements }))
  }
  if (event === 'backlog') {
    const d = data as { items: PrdBacklogItem[] }
    setStreamPartials((prev) => ({ ...prev, backlog: { items: d.items } }))
  }
  // ... existing progress/agent_thought handlers
}
```

**Step 9: Build frontend to verify no TypeScript errors**

```bash
cd frontend
pnpm tsc --noEmit 2>&1 | head -30
```

Expected: no errors related to PrdView.

**Step 10: Commit**

```bash
git add frontend/components/prd/PrdView.tsx
git commit -m "feat(prd-frontend): restore Requirements, Sections, Backlog tabs; wire progressive SSE events"
```

---

## Task 7: Update CLAUDE.md to reflect restored features

**Files:**

- Modify: `CLAUDE.md`

**Step 1: Read CLAUDE.md**

```bash
cat CLAUDE.md
```

**Step 2: Remove/update the "Intentionally Disabled Code" section**

The section describing PRD two-stage parallel generation and disabled frontend tabs should be updated or removed now that the features are restored.

Replace the PRD-related disabled code descriptions with a note that these features are now active via LangGraph.

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md — PRD Requirements/Backlog tabs restored via LangGraph graph"
```

---

## Task 8: End-to-end smoke test

**Step 1: Start backend**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  LLM_MODE=mock \
  UV_CACHE_DIR=../.uv-cache uv run --python .venv/bin/python \
  uvicorn app.main:app --reload --port 8000
```

**Step 2: Start frontend**

```bash
cd frontend
pnpm dev
```

**Step 3: Manual test flow**

1. Login at `http://localhost:3000/login`
2. Create an idea, complete Idea Canvas → Feasibility → Scope Freeze
3. Navigate to PRD page — click Generate
4. Verify SSE events fire in browser DevTools Network tab:
   - `agent_thought` events appear
   - `requirements` event fires (Requirements tab count updates)
   - `backlog` event fires (Backlog panel populates)
   - `done` event fires
5. Switch between PRD / Requirements / Sections tabs — all should render content

**Step 4: Run full backend test suite**

```bash
cd backend
DECISIONOS_SEED_ADMIN_USERNAME=admin DECISIONOS_SEED_ADMIN_PASSWORD=admin \
  PYTHONPATH=. .venv/bin/pytest tests/ -q 2>&1 | tail -15
```

Expected: all pass.

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat(prd): complete LangGraph PRD graph + frontend tabs restoration"
```
