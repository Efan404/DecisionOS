from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository
from app.db.repo_ideas import IdeaRepository
from app.schemas.cross_idea_insights import CrossIdeaInsightOut

router = APIRouter(tags=["cross-idea-insights"])
_insight_repo = CrossIdeaInsightRepository()
_idea_repo = IdeaRepository()
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CrossInsightListResponse(BaseModel):
    idea_id: str
    data: list[CrossIdeaInsightOut]


class CrossInsightSyncResponse(BaseModel):
    idea_id: str
    data: list[CrossIdeaInsightOut]
    status: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/ideas/{idea_id}/cross-insights",
    response_model=CrossInsightListResponse,
)
async def list_cross_insights(idea_id: str) -> CrossInsightListResponse:
    """List persisted cross-idea insights for one idea."""
    records = _insight_repo.list_for_idea(idea_id)

    # Build a cache of idea titles to avoid repeated DB lookups
    idea_ids = set()
    for r in records:
        idea_ids.add(r.idea_a_id)
        idea_ids.add(r.idea_b_id)

    title_cache: dict[str, str | None] = {}
    for iid in idea_ids:
        idea = _idea_repo.get_idea(iid)
        title_cache[iid] = idea.title if idea else None

    items: list[CrossIdeaInsightOut] = []
    for r in records:
        out = CrossIdeaInsightOut(
            id=r.id,
            workspace_id=r.workspace_id,
            idea_a_id=r.idea_a_id,
            idea_b_id=r.idea_b_id,
            insight_type=r.insight_type,
            summary=r.summary,
            why_it_matters=r.why_it_matters,
            recommended_action=r.recommended_action,
            confidence=r.confidence,
            similarity_score=r.similarity_score,
            evidence_json=r.evidence_json,
            fingerprint=r.fingerprint,
            created_at=r.created_at,
            updated_at=r.updated_at,
            idea_a_title=title_cache.get(r.idea_a_id),
            idea_b_title=title_cache.get(r.idea_b_id),
        )
        items.append(out)

    return CrossInsightListResponse(idea_id=idea_id, data=items)


@router.post(
    "/ideas/{idea_id}/cross-insights/sync",
    response_model=CrossInsightSyncResponse,
)
async def sync_cross_insights(idea_id: str) -> CrossInsightSyncResponse:
    """Trigger cross-idea analysis for one idea."""
    try:
        from app.services.cross_idea_insights_service import (
            CrossIdeaInsightsService,
        )

        service = CrossIdeaInsightsService()
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, service.analyze_anchor_idea, idea_id
        )

        # Look up titles for results
        idea_ids = set()
        for r in results:
            idea_ids.add(r.idea_a_id)
            idea_ids.add(r.idea_b_id)

        title_cache: dict[str, str | None] = {}
        for iid in idea_ids:
            idea = _idea_repo.get_idea(iid)
            title_cache[iid] = idea.title if idea else None

        items = [
            CrossIdeaInsightOut(
                id=r.id,
                workspace_id=r.workspace_id,
                idea_a_id=r.idea_a_id,
                idea_b_id=r.idea_b_id,
                insight_type=r.insight_type,
                summary=r.summary,
                why_it_matters=r.why_it_matters,
                recommended_action=r.recommended_action,
                confidence=r.confidence,
                similarity_score=r.similarity_score,
                evidence_json=r.evidence_json,
                fingerprint=r.fingerprint,
                created_at=r.created_at,
                updated_at=r.updated_at,
                idea_a_title=title_cache.get(r.idea_a_id),
                idea_b_title=title_cache.get(r.idea_b_id),
            )
            for r in results
        ]

        return CrossInsightSyncResponse(
            idea_id=idea_id, data=items, status="synced"
        )
    except (ImportError, AttributeError, Exception) as exc:
        _logger.info("cross-insights sync not available: %s", exc)
        return CrossInsightSyncResponse(
            idea_id=idea_id, data=[], status="not_implemented"
        )
