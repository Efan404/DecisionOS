from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.core import llm
from app.db.repo_ideas import IdeaRepository, UpdateIdeaResult
from app.schemas.feasibility import FeasibilityOutput, Plan
from app.schemas.idea import OpportunityOutput
from app.schemas.prd import PRDOutput
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
from app.schemas.scope import ScopeOutput

router = APIRouter(prefix="/ideas/{idea_id}/agents", tags=["idea-agents"])
_repo = IdeaRepository()


def _sse_event(event: str, payload: dict[str, object]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


@router.post("/opportunity", response_model=OpportunityAgentResponse)
async def post_opportunity(idea_id: str, payload: OpportunityIdeaRequest) -> OpportunityAgentResponse:
    output = llm.generate_opportunity(payload)
    result = _repo.apply_agent_update(
        idea_id,
        version=payload.version,
        mutate_context=lambda context: _apply_opportunity(context, payload, output),
    )
    idea_version = _unwrap_update(result)
    return OpportunityAgentResponse(idea_id=idea_id, idea_version=idea_version, data=output)


@router.post("/feasibility", response_model=FeasibilityAgentResponse)
async def post_feasibility(idea_id: str, payload: FeasibilityIdeaRequest) -> FeasibilityAgentResponse:
    output = llm.generate_feasibility(payload)
    result = _repo.apply_agent_update(
        idea_id,
        version=payload.version,
        mutate_context=lambda context: _apply_feasibility(context, payload, output),
    )
    idea_version = _unwrap_update(result)
    return FeasibilityAgentResponse(idea_id=idea_id, idea_version=idea_version, data=output)


@router.post("/scope", response_model=ScopeAgentResponse)
async def post_scope(idea_id: str, payload: ScopeIdeaRequest) -> ScopeAgentResponse:
    output = llm.generate_scope(payload)
    result = _repo.apply_agent_update(
        idea_id,
        version=payload.version,
        mutate_context=lambda context: _apply_scope(context, payload, output),
    )
    idea_version = _unwrap_update(result)
    return ScopeAgentResponse(idea_id=idea_id, idea_version=idea_version, data=output)


@router.post("/prd", response_model=PRDAgentResponse)
async def post_prd(idea_id: str, payload: PRDIdeaRequest) -> PRDAgentResponse:
    output = llm.generate_prd(payload)
    result = _repo.apply_agent_update(
        idea_id,
        version=payload.version,
        mutate_context=lambda context: _apply_prd(context, payload, output),
    )
    idea_version = _unwrap_update(result)
    return PRDAgentResponse(idea_id=idea_id, idea_version=idea_version, data=output)


@router.post("/opportunity/stream")
async def stream_opportunity(idea_id: str, payload: OpportunityIdeaRequest) -> EventSourceResponse:
    output = llm.generate_opportunity(payload)

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
            yield _sse_event("error", error_payload)
            return

        assert result.idea is not None
        yield _sse_event(
            "done",
            {
                "idea_id": idea_id,
                "idea_version": result.idea.version,
                "data": output.model_dump(),
            },
        )

    return EventSourceResponse(event_generator())


@router.post("/feasibility/stream")
async def stream_feasibility(idea_id: str, payload: FeasibilityIdeaRequest) -> EventSourceResponse:
    output = llm.generate_feasibility(payload)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        yield _sse_event("progress", {"step": "received_request", "pct": 5})

        for index, plan in enumerate(output.plans, start=1):
            await asyncio.sleep(0.2)
            pct = 20 + index * 25
            yield _sse_event("progress", {"step": f"plan_{index}", "pct": min(95, pct)})
            yield _sse_event("partial", {"plan": _plan_payload(plan)})

        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            mutate_context=lambda context: _apply_feasibility(context, payload, output),
        )
        error_payload = _sse_error_payload(result)
        if error_payload is not None:
            yield _sse_event("error", error_payload)
            return

        assert result.idea is not None
        yield _sse_event(
            "done",
            {
                "idea_id": idea_id,
                "idea_version": result.idea.version,
                "data": output.model_dump(),
            },
        )

    return EventSourceResponse(event_generator())


def _plan_payload(plan: Plan) -> dict[str, object]:
    return plan.model_dump()


def _apply_opportunity(
    context: DecisionContext,
    payload: OpportunityIdeaRequest,
    output: OpportunityOutput,
) -> DecisionContext:
    context.idea_seed = payload.idea_seed
    context.opportunity = output
    context.selected_direction_id = None
    context.path_id = None
    context.feasibility = None
    context.selected_plan_id = None
    context.scope = None
    context.scope_frozen = False
    context.prd = None
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
    return context


def _apply_prd(
    context: DecisionContext,
    payload: PRDIdeaRequest,
    output: PRDOutput,
) -> DecisionContext:
    context.idea_seed = payload.idea_seed
    context.confirmed_dag_path_id = payload.confirmed_path_id
    context.confirmed_dag_node_id = payload.confirmed_node_id
    context.confirmed_dag_node_content = payload.confirmed_node_content
    context.confirmed_dag_path_summary = payload.confirmed_path_summary
    context.selected_plan_id = payload.selected_plan_id
    if _scope_has_content(payload.scope) or context.scope is None:
        context.scope = payload.scope
    context.prd = output
    return context


def _scope_has_content(scope: ScopeOutput) -> bool:
    return len(scope.in_scope) > 0 or len(scope.out_scope) > 0


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
