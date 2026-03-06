from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.core import llm
from app.core.contexts import parse_context_strict
from app.core.time import utc_now_iso
from app.db import repo_dag
from app.db.repo_ideas import IdeaRepository, UpdateIdeaResult
from app.db.repo_scope import ScopeBaselineRecord, ScopeRepository
from app.schemas.feasibility import FeasibilityOutput, Plan
from app.schemas.idea import OpportunityOutput
from app.schemas.prd import (
    PRDBacklog,
    PRDGenerationMeta,
    PRDOutput,
    PrdBaselineMeta,
    PrdBundle,
    PrdContextPack,
    PrdPlanBrief,
    PrdStep2Path,
    PrdStep3Feasibility,
    PrdStep4Scope,
)
from app.schemas.ideas import (
    DecisionContext,
    FeasibilityAgentResponse,
    FeasibilityIdeaRequest,
    OpportunityAgentResponse,
    OpportunityIdeaRequest,
    PRDAgentResponse,
    PRDIdeaRequest,
    ScopeAgentResponse,
    ScopeIdeaRequest,
)
from app.schemas.scope import InScopeItem, OutScopeItem, ScopeOutput

router = APIRouter(prefix="/ideas/{idea_id}/agents", tags=["idea-agents"])
_repo = IdeaRepository()
_scope_repo = ScopeRepository()
_logger = logging.getLogger(__name__)


def _raise_if_no_provider(exc: Exception) -> None:
    """Re-raise RuntimeError from missing AI provider as HTTP 503."""
    msg = str(exc)
    if isinstance(exc, RuntimeError) and "No AI provider" in msg:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AI_PROVIDER_NOT_CONFIGURED",
                "message": msg,
            },
        ) from exc


def _sse_event(event: str, payload: dict[str, object]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


@router.post("/opportunity", response_model=OpportunityAgentResponse)
async def post_opportunity(idea_id: str, payload: OpportunityIdeaRequest) -> OpportunityAgentResponse:
    _logger.info("agent.opportunity.start idea_id=%s version=%s", idea_id, payload.version)
    try:
        output = llm.generate_opportunity(payload)
        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            mutate_context=lambda context: _apply_opportunity(context, payload, output),
        )
        idea_version = _unwrap_update(result)
    except HTTPException as exc:
        _logger.warning(
            "agent.opportunity.failed idea_id=%s version=%s code=%s",
            idea_id,
            payload.version,
            _http_error_code(exc),
        )
        raise
    except Exception as exc:
        _raise_if_no_provider(exc)
        _logger.exception(
            "agent.opportunity.failed idea_id=%s version=%s code=UNHANDLED_ERROR",
            idea_id,
            payload.version,
        )
        raise
    _logger.info("agent.opportunity.done idea_id=%s idea_version=%s", idea_id, idea_version)
    return OpportunityAgentResponse(idea_id=idea_id, idea_version=idea_version, data=output)


@router.post("/feasibility", response_model=FeasibilityAgentResponse)
async def post_feasibility(idea_id: str, payload: FeasibilityIdeaRequest) -> FeasibilityAgentResponse:
    _logger.info("agent.feasibility.start idea_id=%s version=%s", idea_id, payload.version)
    try:
        output = llm.generate_feasibility(payload)
        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            mutate_context=lambda context: _apply_feasibility(context, payload, output),
        )
        idea_version = _unwrap_update(result)
    except HTTPException as exc:
        _logger.warning(
            "agent.feasibility.failed idea_id=%s version=%s code=%s",
            idea_id,
            payload.version,
            _http_error_code(exc),
        )
        raise
    except Exception as exc:
        _raise_if_no_provider(exc)
        _logger.exception(
            "agent.feasibility.failed idea_id=%s version=%s code=UNHANDLED_ERROR",
            idea_id,
            payload.version,
        )
        raise
    _logger.info("agent.feasibility.done idea_id=%s idea_version=%s", idea_id, idea_version)
    return FeasibilityAgentResponse(idea_id=idea_id, idea_version=idea_version, data=output)


@router.post("/scope", response_model=ScopeAgentResponse)
async def post_scope(idea_id: str, payload: ScopeIdeaRequest) -> ScopeAgentResponse:
    _logger.info("agent.scope.start idea_id=%s version=%s", idea_id, payload.version)
    try:
        output = llm.generate_scope(payload)
        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            mutate_context=lambda context: _apply_scope(context, payload, output),
        )
        idea_version = _unwrap_update(result)
    except HTTPException as exc:
        _logger.warning(
            "agent.scope.failed idea_id=%s version=%s code=%s",
            idea_id,
            payload.version,
            _http_error_code(exc),
        )
        raise
    except Exception as exc:
        _raise_if_no_provider(exc)
        _logger.exception(
            "agent.scope.failed idea_id=%s version=%s code=UNHANDLED_ERROR",
            idea_id,
            payload.version,
        )
        raise
    _logger.info("agent.scope.done idea_id=%s idea_version=%s", idea_id, idea_version)
    return ScopeAgentResponse(idea_id=idea_id, idea_version=idea_version, data=output)


@router.post("/prd", response_model=PRDAgentResponse)
async def post_prd(idea_id: str, payload: PRDIdeaRequest) -> PRDAgentResponse:
    _logger.info(
        "agent.prd.start idea_id=%s version=%s baseline_id=%s",
        idea_id,
        payload.version,
        payload.baseline_id,
    )
    idea = _repo.get_idea(idea_id)
    if idea is None:
        _logger.warning(
            "agent.prd.failed idea_id=%s version=%s code=IDEA_NOT_FOUND",
            idea_id,
            payload.version,
        )
        raise HTTPException(
            status_code=404,
            detail={"code": "IDEA_NOT_FOUND", "message": "Idea not found"},
        )
    if idea.status == "archived":
        _logger.warning(
            "agent.prd.failed idea_id=%s version=%s code=IDEA_ARCHIVED",
            idea_id,
            payload.version,
        )
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEA_ARCHIVED", "message": "Idea is archived"},
        )

    try:
        pack = _build_prd_context_pack(
            idea_id=idea_id,
            baseline_id=payload.baseline_id,
            context=parse_context_strict(idea.context),
        )
    except HTTPException as exc:
        _logger.warning(
            "agent.prd.failed idea_id=%s version=%s code=%s",
            idea_id,
            payload.version,
            _http_error_code(exc),
        )
        raise
    fingerprint = _context_pack_fingerprint(pack)
    try:
        output = llm.generate_prd_strict(pack)
    except llm.PRDGenerationError as exc:
        _logger.warning(
            "agent.prd.failed idea_id=%s version=%s code=PRD_GENERATION_FAILED",
            idea_id,
            payload.version,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "PRD_GENERATION_FAILED",
                "message": "PRD generation failed. Please retry.",
            },
        ) from exc

    bundle = PrdBundle(
        baseline_id=payload.baseline_id,
        context_fingerprint=fingerprint,
        generated_at=utc_now_iso(),
        generation_meta=output.generation_meta,
        output=output,
    )
    result = _repo.apply_agent_update(
        idea_id,
        version=payload.version,
        mutate_context=lambda context: _apply_prd(context, pack, bundle),
    )
    try:
        idea_version = _unwrap_update(result)
    except HTTPException as exc:
        _logger.warning(
            "agent.prd.failed idea_id=%s version=%s code=%s",
            idea_id,
            payload.version,
            _http_error_code(exc),
        )
        raise
    _logger.info("agent.prd.done idea_id=%s idea_version=%s", idea_id, idea_version)
    return PRDAgentResponse(idea_id=idea_id, idea_version=idea_version, data=output)


@router.post("/opportunity/stream")
async def stream_opportunity(idea_id: str, payload: OpportunityIdeaRequest) -> EventSourceResponse:
    _logger.info("agent.opportunity.stream.start idea_id=%s version=%s", idea_id, payload.version)
    try:
        output = llm.generate_opportunity(payload)
    except Exception as exc:
        _raise_if_no_provider(exc)
        _logger.exception(
            "agent.opportunity.stream.failed idea_id=%s version=%s code=UNHANDLED_ERROR",
            idea_id,
            payload.version,
        )
        raise

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        yield _sse_event("progress", {"step": "received_request", "pct": 5})

        total = max(1, len(output.directions))
        for index, direction in enumerate(output.directions, start=1):
            await asyncio.sleep(0.15)
            pct = 10 + int((index / total) * 85)
            yield _sse_event("progress", {"step": f"direction_{index}", "pct": min(95, pct)})
            yield _sse_event("partial", {"direction": direction.model_dump()})

        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            mutate_context=lambda context: _apply_opportunity(context, payload, output),
        )
        error_payload = _sse_error_payload(result)
        if error_payload is not None:
            _logger.warning(
                "agent.opportunity.stream.failed idea_id=%s version=%s code=%s",
                idea_id,
                payload.version,
                error_payload.get("code", "UNKNOWN_ERROR"),
            )
            yield _sse_event("error", error_payload)
            return

        assert result.idea is not None
        _logger.info(
            "agent.opportunity.stream.done idea_id=%s idea_version=%s",
            idea_id,
            result.idea.version,
        )
        yield _sse_event(
            "done",
            {
                "idea_id": idea_id,
                "idea_version": result.idea.version,
                "data": output.model_dump(),
            },
        )

    return EventSourceResponse(event_generator())


@router.post("/opportunity/stream/v2")
async def stream_opportunity_v2(idea_id: str, payload: OpportunityIdeaRequest) -> EventSourceResponse:
    """Multi-agent opportunity generation with agent thought streaming."""
    _logger.info("agent.opportunity.stream.v2.start idea_id=%s version=%s", idea_id, payload.version)

    from app.agents.stream import run_opportunity_graph_sse

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            async for event in run_opportunity_graph_sse(
                idea_id=idea_id,
                idea_seed=payload.idea_seed,
            ):
                # For the internal done event from the graph, persist first then
                # replace it with a richer done event that includes idea_version.
                # This ensures the client never receives done before data is saved.
                if event.get("event") == "done":
                    done_data = json.loads(event["data"])
                    opp_output = done_data.get("opportunity_output")
                    if opp_output:
                        output = OpportunityOutput.model_validate(opp_output)
                        result = _repo.apply_agent_update(
                            idea_id,
                            version=payload.version,
                            mutate_context=lambda context: _apply_opportunity(context, payload, output),
                            allow_conflict_retry=True,
                        )
                        error_payload = _sse_error_payload(result)
                        if error_payload is not None:
                            yield _sse_event("error", error_payload)
                            return
                        assert result.idea is not None
                        yield _sse_event("done", {
                            "idea_id": idea_id,
                            "idea_version": result.idea.version,
                            "data": output.model_dump(),
                        })
                    continue
                yield event
        except Exception as exc:
            _raise_if_no_provider(exc)
            _logger.exception("agent.opportunity.stream.v2.failed idea_id=%s", idea_id)
            yield _sse_event("error", {"code": "AGENT_ERROR", "message": str(exc)})

    return EventSourceResponse(event_generator())


@router.post("/feasibility/stream/v2")
async def stream_feasibility_v2(idea_id: str, payload: FeasibilityIdeaRequest) -> EventSourceResponse:
    """Multi-agent feasibility generation with agent thought streaming."""
    _logger.info("agent.feasibility.stream.v2.start idea_id=%s", idea_id)

    from app.agents.stream import run_feasibility_graph_sse

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            async for event in run_feasibility_graph_sse(
                idea_id=idea_id,
                idea_seed=payload.idea_seed,
                confirmed_path_summary=payload.confirmed_path_summary or "",
                confirmed_node_content=payload.confirmed_node_content or "",
            ):
                yield event
        except Exception as exc:
            _raise_if_no_provider(exc)
            _logger.exception("agent.feasibility.stream.v2.failed idea_id=%s", idea_id)
            yield _sse_event("error", {"code": "AGENT_ERROR", "message": str(exc)})

    return EventSourceResponse(event_generator())


@router.post("/prd/stream/v2")
async def stream_prd_v2(idea_id: str, payload: PRDIdeaRequest) -> EventSourceResponse:
    """Multi-agent PRD generation with agent thought streaming."""
    _logger.info("agent.prd.stream.v2.start idea_id=%s", idea_id)

    from app.agents.stream import run_prd_graph_sse

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            # Build context from existing idea data
            idea = _repo.get_idea(idea_id)
            if idea is None:
                yield _sse_event("error", {"code": "IDEA_NOT_FOUND", "message": "Idea not found"})
                return

            context = parse_context_strict(idea.context)

            dag_path = None
            latest_path = repo_dag.get_latest_path(idea_id)
            if latest_path:
                dag_path = {
                    "path_summary": context.confirmed_dag_path_summary or "",
                    "leaf_node_content": context.confirmed_dag_node_content or context.idea_seed or "",
                }

            feasibility_output = context.feasibility.model_dump() if context.feasibility else None
            scope_output = context.scope.model_dump() if context.scope else None

            async for event in run_prd_graph_sse(
                idea_id=idea_id,
                idea_seed=context.idea_seed or "Untitled",
                dag_path=dag_path,
                feasibility_output=feasibility_output,
                selected_plan_id=context.selected_plan_id or "",
                scope_output=scope_output,
            ):
                yield event
        except Exception as exc:
            _raise_if_no_provider(exc)
            _logger.exception("agent.prd.stream.v2.failed idea_id=%s", idea_id)
            yield _sse_event("error", {"code": "AGENT_ERROR", "message": str(exc)})

    return EventSourceResponse(event_generator())


@router.post("/feasibility/stream")
async def stream_feasibility(idea_id: str, payload: FeasibilityIdeaRequest) -> EventSourceResponse:
    _logger.info("agent.feasibility.stream.start idea_id=%s version=%s", idea_id, payload.version)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        yield _sse_event("progress", {"step": "received_request", "pct": 5})

        # Check version before launching LLM calls so a stale-version request
        # gets an SSE error event rather than crashing inside the thread pool.
        current = _repo.get_idea(idea_id)
        if current is None:
            yield _sse_event("error", {"code": "IDEA_NOT_FOUND", "message": "Idea not found"})
            return
        if current.version != payload.version:
            yield _sse_event("error", {"code": "IDEA_VERSION_CONFLICT", "message": f"Version conflict: expected {current.version}, got {payload.version}"})
            return

        loop = asyncio.get_running_loop()

        # Launch all 3 plan requests concurrently in a thread pool (LLM calls are blocking I/O)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                loop.run_in_executor(pool, llm.generate_single_plan, payload, i)
                for i in range(3)
            ]

            plans: list[object] = [None, None, None]  # preserve slot order for context save
            completed = 0
            pending = list(futures)
            # Heartbeat counter: advances progress from 5→18% while LLMs are running
            heartbeat_tick = 0

            while pending:
                # Wait up to 2s for any future to complete, then yield a heartbeat if none did
                done_set, pending_set = await asyncio.wait(
                    pending, timeout=2.0, return_when=asyncio.FIRST_COMPLETED
                )
                pending = list(pending_set)

                if not done_set:
                    # No plan finished yet — emit a small heartbeat progress tick (5→18%)
                    heartbeat_tick += 1
                    heartbeat_pct = min(18, 5 + heartbeat_tick * 2)
                    yield _sse_event("progress", {"step": "waiting", "pct": heartbeat_pct})
                    continue

                for fut in done_set:
                    try:
                        plan = fut.result()
                        slot = next(
                            (i for i, p in enumerate(plans) if p is None),
                            completed,
                        )
                        plans[slot] = plan
                        completed += 1
                        pct = 20 + completed * 25
                        yield _sse_event("progress", {"step": f"plan_{completed}", "pct": min(90, pct)})
                        yield _sse_event("partial", {"plan": _plan_payload(plan)})
                    except Exception as exc:
                        _raise_if_no_provider(exc)
                        _logger.exception(
                            "agent.feasibility.stream.plan_failed idea_id=%s", idea_id, exc_info=exc
                        )
                        yield _sse_event("error", {"code": "PLAN_GENERATION_FAILED", "message": "Failed to generate one of the plans"})
                        return

        from app.schemas.feasibility import FeasibilityOutput, Plan
        output = FeasibilityOutput(plans=[p for p in plans if p is not None])  # type: ignore[arg-type]

        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            mutate_context=lambda context: _apply_feasibility(context, payload, output),
            allow_conflict_retry=True,
        )
        error_payload = _sse_error_payload(result)
        if error_payload is not None:
            _logger.warning(
                "agent.feasibility.stream.failed idea_id=%s version=%s code=%s",
                idea_id,
                payload.version,
                error_payload.get("code", "UNKNOWN_ERROR"),
            )
            yield _sse_event("error", error_payload)
            return

        assert result.idea is not None
        _logger.info(
            "agent.feasibility.stream.done idea_id=%s idea_version=%s",
            idea_id,
            result.idea.version,
        )
        yield _sse_event(
            "done",
            {
                "idea_id": idea_id,
                "idea_version": result.idea.version,
                "data": output.model_dump(),
            },
        )

    return EventSourceResponse(event_generator())


@router.post("/prd/stream")
async def stream_prd(idea_id: str, payload: PRDIdeaRequest) -> EventSourceResponse:
    """Single-call PRD generation over SSE.

    Generates markdown + sections in one LLM call.
    SSE events: progress → done | error
    """
    _logger.info(
        "agent.prd.stream.start idea_id=%s version=%s baseline_id=%s",
        idea_id, payload.version, payload.baseline_id,
    )

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        yield _sse_event("progress", {"step": "validating", "pct": 5})

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

        slim_ctx = llm._build_slim_prd_context(pack)
        fingerprint = _context_pack_fingerprint(pack)

        # Single LLM call: markdown + sections only
        yield _sse_event("progress", {"step": "generating_prd", "pct": 15})

        loop = asyncio.get_running_loop()
        try:
            md_result = await loop.run_in_executor(None, llm.generate_prd_markdown, slim_ctx)
        except Exception as exc:
            _raise_if_no_provider(exc)
            _logger.exception("agent.prd.stream.failed idea_id=%s", idea_id)
            yield _sse_event("error", {
                "code": "PRD_GENERATION_FAILED",
                "message": "PRD generation failed",
            })
            return

        # --- DISABLED: two-stage parallel generation (requirements + backlog) ---
        # Re-enable when requirements/backlog tabs are needed again.
        #
        # # ── Stage A: requirements + markdown in parallel ──
        # yield _sse_event("progress", {"step": "generating_requirements", "pct": 15})
        # with ThreadPoolExecutor(max_workers=2) as pool:
        #     fut_req = loop.run_in_executor(pool, llm.generate_prd_requirements, slim_ctx)
        #     fut_md  = loop.run_in_executor(pool, llm.generate_prd_markdown,     slim_ctx)
        #     try:
        #         req_result, md_result = await asyncio.gather(fut_req, fut_md)
        #     except Exception as exc:
        #         _raise_if_no_provider(exc)
        #         _logger.exception("agent.prd.stream.stage_a.failed idea_id=%s", idea_id)
        #         yield _sse_event("error", {"code": "PRD_GENERATION_FAILED", "message": "Stage A generation failed"})
        #         return
        # # Emit requirements for progressive rendering
        # yield _sse_event("requirements", {"requirements": [r.model_dump() for r in req_result.requirements]})
        #
        # # ── Stage B: backlog (needs requirement IDs from Stage A) ──
        # yield _sse_event("progress", {"step": "generating_backlog", "pct": 60})
        # requirement_ids = [r.id for r in req_result.requirements]
        # try:
        #     bl_result = await loop.run_in_executor(None, llm.generate_prd_backlog, slim_ctx, requirement_ids)
        # except Exception as exc:
        #     _raise_if_no_provider(exc)
        #     _logger.exception("agent.prd.stream.stage_b.failed idea_id=%s", idea_id)
        #     yield _sse_event("error", {"code": "PRD_GENERATION_FAILED", "message": "Stage B backlog generation failed"})
        #     return
        # yield _sse_event("backlog", {"items": [item.model_dump() for item in bl_result.backlog.items]})
        # --- END DISABLED ---

        yield _sse_event("progress", {"step": "saving", "pct": 90})

        try:
            provider_info = llm._get_active_provider_info()
        except RuntimeError:
            provider_info = {"id": None, "model": None}
        merged_output = PRDOutput(
            markdown=md_result.markdown,
            sections=md_result.sections,
            requirements=[],
            backlog=PRDBacklog(items=[]),
            generation_meta=PRDGenerationMeta(
                provider_id=provider_info["id"],
                model=provider_info["model"],
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
            allow_conflict_retry=True,
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


def _build_prd_context_pack(
    *,
    idea_id: str,
    baseline_id: str,
    context: DecisionContext,
) -> PrdContextPack:
    baseline = _scope_repo.get_baseline(idea_id, baseline_id)
    if baseline is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SCOPE_BASELINE_NOT_FOUND", "message": "Scope baseline not found"},
        )
    if baseline.status != "frozen":
        raise HTTPException(
            status_code=409,
            detail={"code": "SCOPE_BASELINE_NOT_FROZEN", "message": "Scope baseline is not frozen"},
        )

    latest_path = repo_dag.get_latest_path(idea_id)
    if latest_path is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PRD_CONFIRMED_PATH_REQUIRED",
                "message": "Confirmed path is required before PRD generation",
            },
        )

    selected_plan_id = context.selected_plan_id
    if not selected_plan_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PRD_SELECTED_PLAN_REQUIRED",
                "message": "Selected feasibility plan is required before PRD generation",
            },
        )
    if context.feasibility is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PRD_FEASIBILITY_REQUIRED",
                "message": "Feasibility output is required before PRD generation",
            },
        )

    selected_plan = next((plan for plan in context.feasibility.plans if plan.id == selected_plan_id), None)
    if selected_plan is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PRD_SELECTED_PLAN_NOT_FOUND",
                "message": "Selected plan id is not present in feasibility output",
            },
        )

    parsed_path_json = _parse_path_json(latest_path.path_json)
    path_summary = _resolve_path_summary(context, parsed_path_json)
    leaf_node_id, leaf_node_content = _resolve_leaf_node(context, parsed_path_json)
    mapped_scope = _scope_from_baseline(
        baseline,
        existing_scope=context.scope,
    )
    return PrdContextPack(
        idea_seed=context.idea_seed or "Untitled idea",
        step2_path=PrdStep2Path(
            path_id=latest_path.id,
            path_md=latest_path.path_md,
            path_json=parsed_path_json,
            path_summary=path_summary,
            leaf_node_id=leaf_node_id,
            leaf_node_content=leaf_node_content,
        ),
        step3_feasibility=PrdStep3Feasibility(
            selected_plan=selected_plan,
            alternatives_brief=[
                PrdPlanBrief(
                    id=plan.id,
                    name=plan.name,
                    summary=plan.summary,
                    score_overall=plan.score_overall,
                    recommended_positioning=plan.recommended_positioning,
                )
                for plan in context.feasibility.plans
                if plan.id != selected_plan.id
            ][:2],
        ),
        step4_scope=PrdStep4Scope(
            baseline_meta=PrdBaselineMeta(
                baseline_id=baseline.id,
                version=baseline.version,
                status=baseline.status,
                source_baseline_id=baseline.source_baseline_id,
            ),
            in_scope=mapped_scope.in_scope,
            out_scope=mapped_scope.out_scope,
        ),
    )


def _parse_path_json(raw_path_json: str) -> dict[str, object]:
    try:
        decoded = json.loads(raw_path_json)
        if isinstance(decoded, dict):
            return decoded
    except json.JSONDecodeError:
        return {}
    return {}


def _resolve_path_summary(context: DecisionContext, path_json: dict[str, object]) -> str:
    if context.confirmed_dag_path_summary:
        return context.confirmed_dag_path_summary
    summary = path_json.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return "No confirmed path summary provided."


def _resolve_leaf_node(context: DecisionContext, path_json: dict[str, object]) -> tuple[str, str]:
    node_chain = path_json.get("node_chain")
    if isinstance(node_chain, list) and node_chain:
        last = node_chain[-1]
        if isinstance(last, dict):
            node_id = str(last.get("id", "")).strip()
            content = str(last.get("content", "")).strip()
            if node_id and content:
                return node_id, content

    node_id = (context.confirmed_dag_node_id or "").strip()
    node_content = (context.confirmed_dag_node_content or "").strip()
    if node_id and node_content:
        return node_id, node_content
    raise HTTPException(
        status_code=409,
        detail={
            "code": "PRD_CONFIRMED_NODE_REQUIRED",
            "message": "Confirmed node details are required before PRD generation",
        },
    )


def _scope_from_baseline(
    baseline: ScopeBaselineRecord,
    *,
    existing_scope: ScopeOutput | None,
) -> ScopeOutput:
    in_scope_by_title: dict[str, InScopeItem] = {}
    out_scope_by_title: dict[str, OutScopeItem] = {}
    if existing_scope is not None:
        in_scope_by_title = {_normalize_title(item.title): item for item in existing_scope.in_scope}
        out_scope_by_title = {_normalize_title(item.title): item for item in existing_scope.out_scope}

    in_scope: list[InScopeItem] = []
    out_scope: list[OutScopeItem] = []
    for item in baseline.items:
        normalized = _normalize_title(item.content)
        if item.lane == "in":
            existing = in_scope_by_title.get(normalized)
            in_scope.append(
                InScopeItem(
                    id=item.id,
                    title=item.content,
                    desc=(existing.desc if existing is not None else ""),
                    priority=(existing.priority if existing is not None else "P1"),
                )
            )
            continue

        existing_out = out_scope_by_title.get(normalized)
        out_scope.append(
            OutScopeItem(
                id=item.id,
                title=item.content,
                desc=(existing_out.desc if existing_out is not None else ""),
                reason=(existing_out.reason if existing_out is not None else ""),
            )
        )
    return ScopeOutput(in_scope=in_scope, out_scope=out_scope)


def _normalize_title(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _context_pack_fingerprint(pack: PrdContextPack) -> str:
    serialized = json.dumps(pack.model_dump(mode="python"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _plan_payload(plan: Plan) -> dict[str, object]:
    return plan.model_dump()


def _apply_opportunity(
    context: DecisionContext,
    payload: OpportunityIdeaRequest,
    output: OpportunityOutput,
) -> DecisionContext:
    context.idea_seed = payload.idea_seed
    context.opportunity = output
    context.feasibility = None
    context.selected_plan_id = None
    context.scope = None
    context.scope_frozen = False
    context.prd = None
    context.prd_bundle = None
    context.prd_feedback_latest = None
    return context


def _apply_feasibility(
    context: DecisionContext,
    payload: FeasibilityIdeaRequest,
    output: FeasibilityOutput,
) -> DecisionContext:
    context.idea_seed = payload.idea_seed
    context.confirmed_dag_path_id = payload.confirmed_path_id
    context.confirmed_dag_node_id = payload.confirmed_node_id
    context.confirmed_dag_node_content = payload.confirmed_node_content
    context.confirmed_dag_path_summary = payload.confirmed_path_summary
    context.feasibility = output
    context.selected_plan_id = None
    context.scope = None
    context.scope_frozen = False
    context.prd = None
    context.prd_bundle = None
    context.prd_feedback_latest = None
    return context


def _apply_scope(
    context: DecisionContext,
    payload: ScopeIdeaRequest,
    output: ScopeOutput,
) -> DecisionContext:
    context.idea_seed = payload.idea_seed
    context.confirmed_dag_path_id = payload.confirmed_path_id
    context.confirmed_dag_node_id = payload.confirmed_node_id
    context.confirmed_dag_node_content = payload.confirmed_node_content
    context.confirmed_dag_path_summary = payload.confirmed_path_summary
    context.selected_plan_id = payload.selected_plan_id
    context.feasibility = payload.feasibility
    context.scope = output
    context.prd = None
    context.prd_bundle = None
    context.prd_feedback_latest = None
    return context


def _apply_prd(
    context: DecisionContext,
    pack: PrdContextPack,
    bundle: PrdBundle,
) -> DecisionContext:
    context.idea_seed = pack.idea_seed
    context.confirmed_dag_path_id = pack.step2_path.path_id
    context.confirmed_dag_node_id = pack.step2_path.leaf_node_id
    context.confirmed_dag_node_content = pack.step2_path.leaf_node_content
    context.confirmed_dag_path_summary = pack.step2_path.path_summary
    context.selected_plan_id = pack.step3_feasibility.selected_plan.id
    context.scope = ScopeOutput(
        in_scope=pack.step4_scope.in_scope,
        out_scope=pack.step4_scope.out_scope,
    )
    context.scope_frozen = True
    context.current_scope_baseline_id = pack.step4_scope.baseline_meta.baseline_id
    context.current_scope_baseline_version = pack.step4_scope.baseline_meta.version
    context.prd = bundle.output
    context.prd_bundle = bundle
    context.prd_feedback_latest = None
    return context


def _unwrap_update(result: UpdateIdeaResult) -> int:
    if result.kind == "ok" and result.idea is not None:
        return result.idea.version

    if result.kind == "not_found":
        raise HTTPException(
            status_code=404,
            detail={"code": "IDEA_NOT_FOUND", "message": "Idea not found"},
        )

    if result.kind == "archived":
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEA_ARCHIVED", "message": "Idea is archived"},
        )

    raise HTTPException(
        status_code=409,
        detail={"code": "IDEA_VERSION_CONFLICT", "message": "Idea version conflict"},
    )


def _sse_error_payload(result: UpdateIdeaResult) -> dict[str, object] | None:
    if result.kind == "ok":
        return None

    if result.kind == "not_found":
        return {"code": "IDEA_NOT_FOUND", "message": "Idea not found"}

    if result.kind == "archived":
        return {"code": "IDEA_ARCHIVED", "message": "Idea is archived"}

    return {"code": "IDEA_VERSION_CONFLICT", "message": "Idea version conflict"}


def _http_error_code(exc: HTTPException) -> str:
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code")
        if isinstance(code, str) and code:
            return code
    return "HTTP_ERROR"
