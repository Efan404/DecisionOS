from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, HTTPException

from app.db.repo_ideas import IdeaRepository
from app.db.repo_scope import (
    ScopeDraftItemInput,
    ScopeBaselineRecord,
    ScopeBaselineItemRecord,
    ScopeMutationResult,
    ScopeRepository,
)
from app.schemas.scope import (
    ScopeBaselineItemOut,
    ScopeBaselineOut,
    ScopeBootstrapDraftRequest,
    ScopeFreezeRequest,
    ScopeMutationResponse,
    ScopeNewVersionRequest,
    ScopePatchDraftRequest,
)

router = APIRouter(prefix="/ideas/{idea_id}/scope", tags=["idea-scope"])
_repo = ScopeRepository()
_idea_repo = IdeaRepository()


@router.get("/draft", response_model=ScopeBaselineOut)
async def get_scope_draft(idea_id: str) -> ScopeBaselineOut:
    _require_idea(idea_id)
    draft = _repo.get_draft(idea_id)
    if draft is None:
        _raise_scope_draft_not_found()
    return _to_baseline_out(draft)


@router.post("/draft/bootstrap", response_model=ScopeMutationResponse)
async def bootstrap_scope_draft(
    idea_id: str,
    payload: ScopeBootstrapDraftRequest,
) -> ScopeMutationResponse:
    result = _repo.bootstrap_draft(
        idea_id,
        version=payload.version,
        items=[_to_repo_item(item.lane, item.content) for item in payload.items],
    )
    return _to_mutation_response(idea_id, result)


@router.patch("/draft", response_model=ScopeMutationResponse)
async def patch_scope_draft(idea_id: str, payload: ScopePatchDraftRequest) -> ScopeMutationResponse:
    result = _repo.patch_draft(
        idea_id,
        version=payload.version,
        items=[_to_repo_item(item.lane, item.content) for item in payload.items],
    )
    return _to_mutation_response(idea_id, result)


@router.post("/freeze", response_model=ScopeMutationResponse)
async def freeze_scope_draft(idea_id: str, payload: ScopeFreezeRequest) -> ScopeMutationResponse:
    result = _repo.freeze_draft(idea_id, version=payload.version)
    return _to_mutation_response(idea_id, result)


@router.post("/new-version", response_model=ScopeMutationResponse)
async def create_new_scope_version(
    idea_id: str,
    payload: ScopeNewVersionRequest,
) -> ScopeMutationResponse:
    result = _repo.new_version(idea_id, version=payload.version)
    return _to_mutation_response(idea_id, result)


@router.get("/baselines/{baseline_id}", response_model=ScopeBaselineOut)
async def get_scope_baseline(idea_id: str, baseline_id: str) -> ScopeBaselineOut:
    _require_idea(idea_id)
    baseline = _repo.get_baseline(idea_id, baseline_id)
    if baseline is None:
        _raise_scope_baseline_not_found()
    return _to_baseline_out(baseline)


def _to_mutation_response(idea_id: str, result: ScopeMutationResult) -> ScopeMutationResponse:
    if result.kind == "ok" and result.baseline is not None and result.idea_version is not None:
        return ScopeMutationResponse(
            idea_id=idea_id,
            idea_version=result.idea_version,
            data=_to_baseline_out(result.baseline),
        )

    if result.kind == "not_found":
        _raise_idea_not_found(idea_id)

    if result.kind == "archived":
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEA_ARCHIVED", "message": "Idea is archived"},
        )

    if result.kind == "conflict":
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEA_VERSION_CONFLICT", "message": "Idea version conflict"},
        )

    if result.kind == "draft_not_found":
        _raise_scope_draft_not_found()

    _raise_scope_baseline_not_found()


def _to_repo_item(lane: str, content: str) -> ScopeDraftItemInput:
    if lane not in ("in", "out"):
        raise ValueError(f"Unsupported lane {lane!r}")
    return ScopeDraftItemInput(lane=lane, content=content)


def _to_baseline_out(record: ScopeBaselineRecord) -> ScopeBaselineOut:
    return ScopeBaselineOut(
        id=record.id,
        idea_id=record.idea_id,
        version=record.version,
        status=record.status,
        source_baseline_id=record.source_baseline_id,
        created_at=record.created_at,
        frozen_at=record.frozen_at,
        items=[_to_item_out(item) for item in record.items],
    )


def _to_item_out(record: ScopeBaselineItemRecord) -> ScopeBaselineItemOut:
    return ScopeBaselineItemOut(
        id=record.id,
        baseline_id=record.baseline_id,
        lane=record.lane,
        content=record.content,
        display_order=record.display_order,
        created_at=record.created_at,
    )


def _require_idea(idea_id: str) -> None:
    idea = _idea_repo.get_idea(idea_id)
    if idea is None:
        _raise_idea_not_found(idea_id)


def _raise_idea_not_found(idea_id: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={"code": "IDEA_NOT_FOUND", "message": f"Idea {idea_id} not found"},
    )


def _raise_scope_draft_not_found() -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={"code": "SCOPE_DRAFT_NOT_FOUND", "message": "Scope draft not found"},
    )


def _raise_scope_baseline_not_found() -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={"code": "SCOPE_BASELINE_NOT_FOUND", "message": "Scope baseline not found"},
    )
