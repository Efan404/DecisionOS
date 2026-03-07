from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.repo_competitors import CompetitorRepository
from app.db.repo_market_signals import MarketSignalRepository
from app.schemas.market_evidence import (
    CompetitorOut,
    CompetitorSnapshotOut,
    IdeaEvidenceLinkOut,
    MarketSignalOut,
)

router = APIRouter(prefix="/ideas/{idea_id}/evidence", tags=["market-evidence"])
_comp_repo = CompetitorRepository()
_sig_repo = MarketSignalRepository()
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class CompetitorWithSnapshot(BaseModel):
    competitor: CompetitorOut
    latest_snapshot: CompetitorSnapshotOut | None = None
    link: IdeaEvidenceLinkOut


class CompetitorListResponse(BaseModel):
    idea_id: str
    data: list[CompetitorWithSnapshot]


class SignalListResponse(BaseModel):
    idea_id: str
    data: list[MarketSignalOut]


class DiscoverRequest(BaseModel):
    search_query: str | None = None


class ActionResponse(BaseModel):
    idea_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/competitors", response_model=CompetitorListResponse)
async def list_competitors(idea_id: str) -> CompetitorListResponse:
    """List competitors linked to this idea with their latest snapshots."""
    links = _sig_repo.list_linked_competitors_for_idea(idea_id)
    items: list[CompetitorWithSnapshot] = []
    for link in links:
        comp = _comp_repo.get_competitor(link.entity_id)
        if comp is None:
            continue
        snapshot = _comp_repo.get_latest_snapshot(comp.id)
        items.append(
            CompetitorWithSnapshot(
                competitor=CompetitorOut.model_validate(comp),
                latest_snapshot=CompetitorSnapshotOut.model_validate(snapshot) if snapshot else None,
                link=IdeaEvidenceLinkOut.model_validate(link),
            )
        )
    return CompetitorListResponse(idea_id=idea_id, data=items)


@router.get("/signals", response_model=SignalListResponse)
async def list_signals(idea_id: str) -> SignalListResponse:
    """List signals linked to this idea."""
    links = _sig_repo.list_signals_for_idea(idea_id)
    signals: list[MarketSignalOut] = []
    for link in links:
        signal = _sig_repo.get_signal(link.entity_id)
        if signal is None:
            continue
        signals.append(MarketSignalOut.model_validate(signal))
    return SignalListResponse(idea_id=idea_id, data=signals)


@router.post("/competitors/discover", response_model=ActionResponse)
async def discover_competitors(idea_id: str, body: DiscoverRequest | None = None) -> ActionResponse:
    """Trigger competitor discovery for an idea (V1 placeholder)."""
    return ActionResponse(
        idea_id=idea_id,
        status="discovery_triggered",
        message="Competitor discovery initiated",
    )


@router.post("/insights/sync", response_model=ActionResponse)
async def sync_insights(idea_id: str) -> ActionResponse:
    """Trigger one-shot insight synthesis (V1 placeholder)."""
    return ActionResponse(
        idea_id=idea_id,
        status="sync_triggered",
        message="Insight synthesis initiated",
    )
