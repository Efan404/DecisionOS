from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.email import send_notification_email
from app.db.repo_notifications import NotificationRepository
from app.db.repo_profile import ProfileRepository

logger = logging.getLogger(__name__)

_notif_repo = NotificationRepository()
_profile_repo = ProfileRepository()


async def run_proactive_agents(trigger_type: str = "scheduled") -> None:
    """Run all proactive agents and email results to opted-in users.

    trigger_type: "scheduled" (APScheduler) or "event" (future event-driven trigger).
    """
    logger.info("scheduler.proactive_agents.start trigger=%s", trigger_type)

    from app.agents.memory.vector_store import get_vector_store
    from app.agents.graphs.proactive.news_monitor import build_news_monitor_graph
    from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
    from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph

    vs = get_vector_store()
    created_notifications: list = []

    # ── News monitor ─────────────────────────────────────────────────────────
    try:
        graph = build_news_monitor_graph()
        result = graph.invoke({
            "user_id": "default",
            "idea_ids": [],
            "notifications": [],
            "agent_thoughts": [],
        })
        for notif in result.get("notifications", []):
            record = _notif_repo.create(
                type="news_match",
                title=f"News: {notif.get('news_title', 'Untitled')}",
                body=notif.get("insight", "Relevant news detected."),
                metadata=notif,
            )
            created_notifications.append(record)
    except Exception:
        logger.warning("scheduler.news_monitor.failed", exc_info=True)

    # ── Cross-idea analyzer ───────────────────────────────────────────────────
    try:
        all_ideas = vs._ideas.get(include=["documents", "metadatas"])
        summaries = [
            {"idea_id": id_, "summary": doc}
            for id_, doc in zip(all_ideas["ids"], all_ideas["documents"])
        ]
        graph = build_cross_idea_graph()
        result = graph.invoke({
            "user_id": "default",
            "idea_summaries": summaries,
            "insights": [],
            "agent_thoughts": [],
        })
        for insight in result.get("insights", []):
            record = _notif_repo.create(
                type="cross_idea_insight",
                title=f"Ideas '{insight.get('idea_a_id', '')}' and '{insight.get('idea_b_id', '')}' are related",
                body=insight.get("analysis", "These ideas share common themes."),
                metadata=insight,
            )
            created_notifications.append(record)
    except Exception:
        logger.warning("scheduler.cross_idea.failed", exc_info=True)

    # ── User pattern learner ─────────────────────────────────────────────────
    try:
        graph = build_pattern_learner_graph()
        result = graph.invoke({
            "user_id": "default",
            "decision_history": [],
            "learned_preferences": {},
            "agent_thoughts": [],
        })
        prefs = result.get("learned_preferences", {})
        if prefs:
            record = _notif_repo.create(
                type="pattern_learned",
                title="Updated your preference profile",
                body=f"Learned patterns: {', '.join(f'{k}: {v}' for k, v in list(prefs.items())[:3])}",
                metadata={"preferences": prefs},
            )
            created_notifications.append(record)
    except Exception:
        logger.warning("scheduler.pattern_learner.failed", exc_info=True)

    logger.info("scheduler.proactive_agents.done notifications_created=%d", len(created_notifications))

    # ── Email dispatch ────────────────────────────────────────────────────────
    for record in created_notifications:
        try:
            notifiable_users = _profile_repo.list_notifiable(record.type)
            for user_prefs in notifiable_users:
                if user_prefs.email:
                    send_notification_email(to=user_prefs.email, notification=record)
        except Exception:
            logger.warning("scheduler.email_dispatch.failed notification_id=%s", record.id, exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance. Does not start it."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_proactive_agents,
        trigger="interval",
        hours=6,
        id="proactive_agents",
        replace_existing=True,
        kwargs={"trigger_type": "scheduled"},
    )
    return scheduler
