from __future__ import annotations

import asyncio
import json
import logging
from functools import partial

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.ai_gateway import generate_structured
from app.db.repo_ideas import IdeaRepository
from app.db.repo_market_insights import MarketInsightRepository
from app.db.repo_market_signals import MarketSignalRepository
from app.db.repo_notifications import NotificationRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ideas", tags=["market-insight"])

_idea_repo = IdeaRepository()
_insight_repo = MarketInsightRepository()
_signal_repo = MarketSignalRepository()
_notif_repo = NotificationRepository()


class MarketInsightOutput(BaseModel):
    summary: str
    decision_impact: str
    recommended_actions: list[str]


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_insight(idea_id: str):
    yield _sse("progress", {"pct": 10, "msg": "Loading idea context..."})

    idea = _idea_repo.get_idea(idea_id)
    if not idea:
        yield _sse("error", {"message": "Idea not found"})
        return

    yield _sse("progress", {"pct": 30, "msg": "Loading linked market signals..."})

    signal_links = _signal_repo.list_signals_for_idea(idea_id)
    signals_text_parts: list[str] = []
    for link in signal_links[:10]:
        signal = _signal_repo.get_signal(link.entity_id)
        if signal:
            signals_text_parts.append(
                f"- [{signal.signal_type}] {signal.title}: {signal.summary} (severity: {signal.severity})"
            )

    signals_text = (
        "\n".join(signals_text_parts)
        if signals_text_parts
        else "No market signals have been detected yet for this idea."
    )

    yield _sse("progress", {"pct": 50, "msg": "Analyzing with AI..."})

    idea_seed = getattr(idea, "idea_seed", None) or idea.title
    prompt = (
        f"You are a product strategist analyzing market signals for an idea.\n\n"
        f"Idea: {idea.title}\n"
        f"Context: {idea_seed}\n\n"
        f"Recent Market Signals:\n{signals_text}\n\n"
        "Analyze these signals and provide:\n"
        "1. A concise summary (2-3 sentences) of the current market landscape relevant to this idea\n"
        "2. The decision impact: how do these signals affect this idea's direction? (2-3 sentences)\n"
        "3. Exactly 3 specific, actionable recommended actions the founder should take\n\n"
        "Be specific and actionable. Focus on what matters for decision-making."
    )

    try:
        loop = asyncio.get_event_loop()
        output: MarketInsightOutput = await loop.run_in_executor(
            None,
            partial(
                generate_structured,
                task="opportunity",
                user_prompt=prompt,
                schema_model=MarketInsightOutput,
            ),
        )
    except Exception as exc:
        logger.warning("market_insight.generate_failed idea_id=%s exc=%s", idea_id, exc)
        yield _sse("error", {"message": f"AI analysis failed: {exc}"})
        return

    yield _sse("progress", {"pct": 80, "msg": "Saving insight..."})

    record = _insight_repo.create(
        idea_id=idea_id,
        summary=output.summary,
        decision_impact=output.decision_impact,
        recommended_actions=output.recommended_actions,
        signal_count=len(signal_links),
    )

    _notif_repo.create(
        type="market_insight",
        title=f"Market insight ready: {idea.title[:50]}",
        body=output.summary[:200],
        metadata={
            "idea_id": idea_id,
            "insight_id": record.id,
            "action_url": f"/insights?idea={idea_id}",
        },
    )

    yield _sse("progress", {"pct": 100, "msg": "Done"})
    yield _sse("done", {
        "insight_id": record.id,
        "summary": output.summary,
        "decision_impact": output.decision_impact,
        "recommended_actions": output.recommended_actions,
        "signal_count": record.signal_count,
        "generated_at": record.generated_at,
    })


@router.post("/{idea_id}/agents/market-insight/stream")
async def stream_market_insight(idea_id: str) -> StreamingResponse:
    return StreamingResponse(
        _stream_insight(idea_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{idea_id}/insights")
async def list_idea_insights(idea_id: str) -> dict:
    insights = _insight_repo.list_for_idea(idea_id)
    return {
        "insights": [
            {
                "id": r.id,
                "summary": r.summary,
                "decision_impact": r.decision_impact,
                "recommended_actions": r.recommended_actions,
                "signal_count": r.signal_count,
                "generated_at": r.generated_at,
            }
            for r in insights
        ]
    }
