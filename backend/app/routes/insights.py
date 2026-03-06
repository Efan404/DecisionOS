from __future__ import annotations

import logging

from fastapi import APIRouter

from app.agents.graphs.proactive.news_monitor import build_news_monitor_graph
from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph
from app.agents.memory.vector_store import get_vector_store
from app.db.repo_notifications import NotificationRepository

router = APIRouter(prefix="/insights", tags=["insights"])
_notif_repo = NotificationRepository()
_logger = logging.getLogger(__name__)


@router.post("/news-scan")
async def trigger_news_scan():
    """Trigger news monitoring agent (for demo)."""
    graph = build_news_monitor_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_ids": [],
        "notifications": [],
        "agent_thoughts": [],
    })

    created = []
    for notif in result.get("notifications", []):
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
    """Trigger cross-idea analysis agent (for demo)."""
    vs = get_vector_store()
    all_ideas = vs._ideas.get(include=["documents", "metadatas"])
    ids = all_ideas.get("ids") or []
    documents = all_ideas.get("documents") or []
    summaries = [
        {"idea_id": id_, "summary": doc}
        for id_, doc in zip(ids, documents)
    ]

    graph = build_cross_idea_graph()
    result = graph.invoke({
        "user_id": "default",
        "idea_summaries": summaries,
        "insights": [],
        "agent_thoughts": [],
    })

    for insight in result.get("insights", []):
        _notif_repo.create(
            type="cross_idea_insight",
            title=f"Ideas '{insight.get('idea_a_id', '')}' and '{insight.get('idea_b_id', '')}' are related",
            body=insight.get("analysis", "These ideas share common themes."),
            metadata=insight,
        )

    return {
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
