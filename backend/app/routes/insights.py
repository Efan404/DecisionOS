from __future__ import annotations

import logging

from fastapi import APIRouter

from app.agents.graphs.proactive.news_monitor import build_news_monitor_graph
from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph
from app.db.repo_notifications import NotificationRepository

router = APIRouter(prefix="/insights", tags=["insights"])
_notif_repo = NotificationRepository()
_logger = logging.getLogger(__name__)


@router.post("/news-scan")
async def trigger_news_scan():
    """Trigger news monitoring agent (for manual testing/demo)."""
    graph = build_news_monitor_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_summaries": [],
        "notifications": [],
        "agent_thoughts": [],
    })

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
    graph = build_cross_idea_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_summaries": [],
        "insights": [],
        "agent_thoughts": [],
    })

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
            body=insight.get("analysis", "These ideas share common themes."),
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
    graph = build_pattern_learner_graph()
    result = graph.invoke({
        "user_id": "default",
        "decision_history": [
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "AI code review tool"},
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "Developer dashboard"},
            {"stage": "scope", "choice": "minimal_mvp", "idea": "AI code review tool"},
            {"stage": "opportunity", "choice": "B2B_focus", "idea": "Meeting summarizer"},
        ],
        "learned_preferences": {},
        "agent_thoughts": [],
    })

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


@router.get("/user-patterns")
async def get_user_patterns():
    """Get learned user patterns (for settings page display)."""
    graph = build_pattern_learner_graph()
    result = graph.invoke({
        "user_id": "default",
        "decision_history": [
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "AI code review tool"},
            {"stage": "feasibility", "choice": "bootstrapped", "idea": "Developer dashboard"},
            {"stage": "scope", "choice": "minimal_mvp", "idea": "AI code review tool"},
        ],
        "learned_preferences": {},
        "agent_thoughts": [],
    })
    return {"preferences": result.get("learned_preferences", {})}
