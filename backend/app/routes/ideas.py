from __future__ import annotations

import base64
import binascii
from typing import Final, NoReturn, cast

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from app.db.repo_ideas import IdeaRecord, IdeaRepository, UpdateIdeaResult
from app.schemas.ideas import (
    CreateIdeaRequest,
    DecisionContext,
    IdeaDetail,
    IdeaListResponse,
    IdeaStatus,
    IdeaSummary,
    PatchIdeaContextRequest,
    PatchIdeaRequest,
)

router = APIRouter(prefix="/ideas", tags=["ideas"])
_repo = IdeaRepository()

_ALLOWED_STATUSES: Final[set[str]] = {"draft", "active", "frozen", "archived"}
_DEFAULT_STATUSES: Final[list[IdeaStatus]] = ["draft", "active", "frozen"]


@router.get("", response_model=IdeaListResponse)
async def list_ideas(
    status: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
) -> IdeaListResponse:
    statuses = _parse_statuses(status)
    cursor_pair = _decode_cursor(cursor) if cursor is not None else None

    items, next_cursor = _repo.list_ideas(statuses=statuses, limit=limit, cursor=cursor_pair)

    return IdeaListResponse(
        items=[_to_idea_summary(item) for item in items],
        next_cursor=_encode_cursor(next_cursor) if next_cursor is not None else None,
    )


@router.post("", response_model=IdeaDetail, status_code=201)
async def create_idea(payload: CreateIdeaRequest) -> IdeaDetail:
    created = _repo.create_idea(title=payload.title, idea_seed=payload.idea_seed)
    return _to_idea_detail(created)


@router.get("/{idea_id}", response_model=IdeaDetail)
async def get_idea(idea_id: str) -> IdeaDetail:
    idea = _repo.get_idea(idea_id)
    if idea is None:
        _raise_not_found(idea_id)

    return _to_idea_detail(idea)


@router.patch("/{idea_id}", response_model=IdeaDetail)
async def patch_idea(idea_id: str, payload: PatchIdeaRequest) -> IdeaDetail:
    result = _repo.update_idea(
        idea_id,
        version=payload.version,
        title=payload.title,
        status=payload.status,
    )
    updated = _unwrap_update_result(result, idea_id)
    return _to_idea_detail(updated)


@router.patch("/{idea_id}/context", response_model=IdeaDetail)
async def patch_idea_context(idea_id: str, payload: PatchIdeaContextRequest) -> IdeaDetail:
    try:
        context = DecisionContext.model_validate(payload.context)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "IDEA_CONTEXT_INVALID", "message": str(exc)},
        ) from exc

    result = _repo.update_context(
        idea_id,
        version=payload.version,
        context=context.model_dump(mode="python", exclude_none=True),
    )
    updated = _unwrap_update_result(result, idea_id)
    return _to_idea_detail(updated)


@router.delete("/{idea_id}", status_code=204)
async def delete_idea(idea_id: str) -> None:
    try:
        _repo.delete_idea(idea_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={"code": "IDEA_NOT_FOUND", "message": f"Idea {idea_id} not found"},
        )


def _parse_statuses(raw: list[str] | None) -> list[IdeaStatus]:
    if raw is None or len(raw) == 0:
        return list(_DEFAULT_STATUSES)

    candidates: list[str] = []
    for item in raw:
        for segment in item.replace("|", ",").split(","):
            normalized = segment.strip().lower()
            if normalized:
                candidates.append(normalized)

    if not candidates:
        return list(_DEFAULT_STATUSES)

    unknown = [value for value in candidates if value not in _ALLOWED_STATUSES]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "IDEA_STATUS_INVALID",
                "message": f"Unsupported status filter: {unknown[0]}",
            },
        )

    deduped: list[IdeaStatus] = []
    for value in candidates:
        status_value = cast(IdeaStatus, value)  # safe after whitelist check
        if status_value not in deduped:
            deduped.append(status_value)
    return deduped


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        updated_at, idea_id = decoded.split("|", 1)
        if not updated_at or not idea_id:
            raise ValueError("cursor segments empty")
        return updated_at, idea_id
    except (UnicodeDecodeError, ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "IDEA_CURSOR_INVALID", "message": "Invalid cursor"},
        ) from exc


def _encode_cursor(cursor_pair: tuple[str, str]) -> str:
    payload = f"{cursor_pair[0]}|{cursor_pair[1]}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _to_idea_summary(record: IdeaRecord) -> IdeaSummary:
    return IdeaSummary(
        id=record.id,
        workspace_id=record.workspace_id,
        title=record.title,
        idea_seed=record.idea_seed,
        stage=record.stage,
        status=record.status,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
        archived_at=record.archived_at,
    )


def _to_idea_detail(record: IdeaRecord) -> IdeaDetail:
    return IdeaDetail(
        **_to_idea_summary(record).model_dump(),
        context=DecisionContext.model_validate(record.context),
    )


def _unwrap_update_result(result: UpdateIdeaResult, idea_id: str) -> IdeaRecord:
    if result.kind == "ok" and result.idea is not None:
        return result.idea

    if result.kind == "not_found":
        _raise_not_found(idea_id)

    if result.kind == "archived":
        raise HTTPException(
            status_code=409,
            detail={"code": "IDEA_ARCHIVED", "message": "Idea is archived"},
        )

    raise HTTPException(
        status_code=409,
        detail={"code": "IDEA_VERSION_CONFLICT", "message": "Idea version conflict"},
    )


def _raise_not_found(idea_id: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail={"code": "IDEA_NOT_FOUND", "message": f"Idea {idea_id} not found"},
    )
