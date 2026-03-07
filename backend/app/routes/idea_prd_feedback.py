from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, HTTPException

from app.core.time import utc_now_iso
from app.db.repo_ideas import IdeaRepository, UpdateIdeaResult
from app.schemas.ideas import DecisionContext, PRDFeedbackRequest, PRDFeedbackResponse
from app.schemas.prd import PrdFeedbackLatest

router = APIRouter(prefix="/ideas/{idea_id}/prd", tags=["idea-prd-feedback"])
_repo = IdeaRepository()


@dataclass
class _FeedbackStateError(Exception):
    code: str
    message: str


@router.post("/feedback", response_model=PRDFeedbackResponse)
async def post_prd_feedback(idea_id: str, payload: PRDFeedbackRequest) -> PRDFeedbackResponse:
    feedback = PrdFeedbackLatest(
        baseline_id=payload.baseline_id,
        submitted_at=utc_now_iso(),
        rating_overall=payload.rating_overall,
        rating_dimensions=payload.rating_dimensions,
        comment=payload.comment,
    )
    try:
        result = _repo.apply_agent_update(
            idea_id,
            version=payload.version,
            mutate_context=lambda context: _apply_feedback(context, payload, feedback),
        )
    except _FeedbackStateError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    idea_version = _unwrap_update(result)
    return PRDFeedbackResponse(idea_id=idea_id, idea_version=idea_version, data=feedback)


def _apply_feedback(
    context: DecisionContext,
    payload: PRDFeedbackRequest,
    feedback: PrdFeedbackLatest,
) -> DecisionContext:
    if context.prd_bundle is None:
        raise _FeedbackStateError(
            code="PRD_NOT_GENERATED",
            message="Generate PRD before submitting feedback",
        )
    if context.prd_bundle.baseline_id != payload.baseline_id:
        raise _FeedbackStateError(
            code="PRD_FEEDBACK_BASELINE_MISMATCH",
            message="Feedback baseline does not match latest PRD baseline",
        )

    context.prd_feedback_latest = feedback
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
