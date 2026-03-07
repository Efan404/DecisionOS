from __future__ import annotations

import asyncio
import logging
from functools import partial

from fastapi import APIRouter

from app.agents.graphs.proactive.news_monitor import build_news_monitor_graph
from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph
from app.db.repo_notifications import NotificationRepository
from app.db.repo_profile import ProfileRepository

router = APIRouter(prefix="/insights", tags=["insights"])
_notif_repo = NotificationRepository()
_profile_repo = ProfileRepository()
_logger = logging.getLogger(__name__)


@router.post("/news-scan")
async def trigger_news_scan():
    """Trigger news monitoring agent (for manual testing/demo)."""
    loop = asyncio.get_event_loop()
    graph = build_news_monitor_graph()
    result = await loop.run_in_executor(None, partial(graph.invoke, {
        "user_id": "default",
        "idea_summaries": [],
        "notifications": [],
        "agent_thoughts": [],
    }))

    created = []
    for notif in result.get("notifications", []):
        news_id = notif.get("news_id", "")
        idea_id = notif.get("idea_id", "")
        # Deduplicate: skip if we already have a notification for this (news_id, idea_id) pair
        if news_id and idea_id and _notif_repo.exists_news_match(news_id=news_id, idea_id=idea_id):
            continue
        record = _notif_repo.create(
            type="news_match",
            title=f"News: {notif.get('news_title', 'Untitled')}",
            body=notif.get("insight", "Relevant news detected."),
            metadata=notif,
        )
        created.append(record.id)

    return {
        "notifications_created": len(created),
        "agent_thoughts": result.get("agent_thoughts", []),
    }


@router.post("/cross-idea-analysis")
async def trigger_cross_idea_analysis():
    """Trigger cross-idea analysis agent (for manual testing/demo).

    Applies the same dedup as the scheduler — manual triggers and scheduled
    runs share the same notification table, so without dedup a manual trigger
    right before the scheduled run would create duplicate notifications.
    """
    loop = asyncio.get_event_loop()
    graph = build_cross_idea_graph()
    result = await loop.run_in_executor(None, partial(graph.invoke, {
        "workspace_id": "default",
        "idea_summaries": [],
        "insights": [],
        "agent_thoughts": [],
    }))

    created = []
    for insight in result.get("insights", []):
        idea_a_id = insight.get("idea_a_id", "")
        idea_b_id = insight.get("idea_b_id", "")
        # Deduplicate: skip if this pair already has a cross_idea_insight notification
        # (order-independent: (a,b) == (b,a))
        if idea_a_id and idea_b_id and _notif_repo.exists_cross_idea(idea_a_id, idea_b_id):
            continue
        record = _notif_repo.create(
            type="cross_idea_insight",
            title=f"Related ideas: {idea_a_id[:8]} <-> {idea_b_id[:8]}",
            body=insight.get("summary", "These ideas share common themes."),
            metadata=insight,
        )
        created.append(record.id)

    return {
        "notifications_created": len(created),
        "insights": result.get("insights", []),
        "agent_thoughts": result.get("agent_thoughts", []),
    }


@router.post("/learn-patterns")
async def trigger_pattern_learning():
    """Trigger user pattern learning agent (for demo)."""
    loop = asyncio.get_event_loop()
    graph = build_pattern_learner_graph()
    result = await loop.run_in_executor(None, partial(graph.invoke, {
        "user_id": "default",
        "decision_history": [
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "AI code review tool"},
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "Developer dashboard"},
            {"stage": "scope", "choice": "minimal_mvp", "idea": "AI code review tool"},
            {"stage": "opportunity", "choice": "B2B_focus", "idea": "Meeting summarizer"},
        ],
        "learned_preferences": {},
        "agent_thoughts": [],
    }))

    prefs = result.get("learned_preferences", {})
    if prefs:
        _notif_repo.create(
            type="pattern_learned",
            title="Updated your preference profile",
            body=f"Learned patterns: {', '.join(f'{k}: {v}' for k, v in list(prefs.items())[:3])}",
            metadata={"preferences": prefs},
        )

    return {
        "learned_preferences": prefs,
        "agent_thoughts": result.get("agent_thoughts", []),
    }


@router.post("/signal-monitor/trigger")
async def trigger_signal_monitor():
    """Manually trigger the signal monitor (market evidence layer).

    Fetches HN stories, creates MarketSignal records, and links them to
    ideas (by vector similarity) and competitors (by URL domain match).
    """
    from app.agents.graphs.proactive.signal_monitor import build_signal_monitor_graph

    loop = asyncio.get_event_loop()
    graph = build_signal_monitor_graph()
    result = await loop.run_in_executor(None, partial(graph.invoke, {
        "workspace_id": "default",
        "idea_summaries": [],
        "signals_created": [],
        "links_created": [],
        "agent_thoughts": [],
    }))

    return {
        "signals_created": len(result.get("signals_created", [])),
        "links_created": len(result.get("links_created", [])),
        "agent_thoughts": result.get("agent_thoughts", []),
    }


@router.get("/cross-idea")
async def get_cross_idea_insights():
    """Return cross-idea insights from both notification table and structured insight table."""
    import json as _json
    from app.db.repo_ideas import IdeaRepository
    from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository

    _idea_repo = IdeaRepository()
    _insight_repo = CrossIdeaInsightRepository()

    # Build id->title lookup
    all_ideas, _ = _idea_repo.list_ideas(statuses=["draft", "active", "frozen"], limit=100)
    title_map = {idea.id: idea.title for idea in all_ideas}

    # Track seen pairs to avoid duplicates between the two sources
    seen_pairs: set[frozenset[str]] = set()
    insights = []

    # Source 1: V2 structured insights from cross_idea_insight table
    try:
        structured = _insight_repo.list_recent_for_workspace("default")
        for rec in structured:
            pair = frozenset({rec.idea_a_id, rec.idea_b_id})
            seen_pairs.add(pair)
            insights.append({
                "idea_a_id": rec.idea_a_id,
                "idea_b_id": rec.idea_b_id,
                "idea_a_title": title_map.get(rec.idea_a_id, ""),
                "idea_b_title": title_map.get(rec.idea_b_id, ""),
                "insight_type": rec.insight_type,
                "summary": rec.summary,
                "why_it_matters": rec.why_it_matters,
                "recommended_action": rec.recommended_action,
                "confidence": rec.confidence,
                "similarity_score": rec.similarity_score,
                "analysis": rec.summary,  # backward compat
            })
    except Exception:
        _logger.warning("get_cross_idea_insights: failed to read structured insights", exc_info=True)

    # Source 2: Legacy notification-based insights
    records = _notif_repo.list_by_type("cross_idea_insight")
    for r in records:
        try:
            meta = _json.loads(r.metadata_json) if r.metadata_json else {}
        except Exception:
            meta = {}
        idea_a_id = meta.get("idea_a_id", "")
        idea_b_id = meta.get("idea_b_id", "")
        pair = frozenset({idea_a_id, idea_b_id})
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        insights.append({
            "idea_a_id": idea_a_id,
            "idea_b_id": idea_b_id,
            "idea_a_title": title_map.get(idea_a_id, ""),
            "idea_b_title": title_map.get(idea_b_id, ""),
            "analysis": meta.get("analysis") or meta.get("summary") or r.body,
        })
    return {"insights": insights}


from app.db.repo_market_insights import MarketInsightRepository as _MIRepo
_mi_repo = _MIRepo()


@router.get("/market-insights")
async def list_all_market_insights() -> dict:
    insights = _mi_repo.list_all(limit=50)
    return {
        "insights": [
            {
                "id": r.id,
                "idea_id": r.idea_id,
                "summary": r.summary,
                "decision_impact": r.decision_impact,
                "recommended_actions": r.recommended_actions,
                "signal_count": r.signal_count,
                "generated_at": r.generated_at,
            }
            for r in insights
        ]
    }


@router.get("/user-patterns")
async def get_user_patterns():
    """Get learned user patterns from DB cache (written by scheduler / POST learn-patterns)."""
    patterns, _ = _profile_repo.get_learned_patterns(user_id="default")
    if not patterns:
        # Fallback: check all user_preferences rows for any with non-empty patterns
        patterns, _ = _profile_repo.get_any_learned_patterns()
    return {"preferences": patterns}
