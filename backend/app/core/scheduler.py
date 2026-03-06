from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from functools import partial

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

    from app.agents.graphs.proactive.news_monitor import build_news_monitor_graph
    from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph
    from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph

    created_notifications: list = []

    loop = asyncio.get_event_loop()

    # -- News monitor ---------------------------------------------------------
    try:
        graph = build_news_monitor_graph()
        result = await loop.run_in_executor(
            None,
            partial(graph.invoke, {
                "user_id": "default",
                "idea_summaries": [],
                "notifications": [],
                "agent_thoughts": [],
            }),
        )
        for notif in result.get("notifications", []):
            news_id = notif.get("news_id", "")
            idea_id = notif.get("idea_id", "")
            # Deduplicate: composite key (news_id, idea_id) -- same story can match multiple ideas
            if news_id and idea_id and _notif_repo.exists_news_match(news_id=news_id, idea_id=idea_id):
                continue
            record = _notif_repo.create(
                type="news_match",
                title=f"News: {notif.get('news_title', 'Untitled')}",
                body=notif.get("insight", "Relevant news detected."),
                metadata=notif,
            )
            created_notifications.append(record)
    except Exception:
        logger.warning("scheduler.news_monitor.failed", exc_info=True)

    # -- Cross-idea analyzer --------------------------------------------------
    try:
        graph = build_cross_idea_graph()
        result = await loop.run_in_executor(
            None,
            partial(graph.invoke, {
                "user_id": "default",
                "idea_summaries": [],
                "insights": [],
                "agent_thoughts": [],
            }),
        )
        for insight in result.get("insights", []):
            idea_a_id = insight.get("idea_a_id", "")
            idea_b_id = insight.get("idea_b_id", "")
            # Deduplicate: sorted pair so (a,b) == (b,a)
            if idea_a_id and idea_b_id and _notif_repo.exists_cross_idea(idea_a_id, idea_b_id):
                continue
            record = _notif_repo.create(
                type="cross_idea_insight",
                title="Related ideas detected",
                body=insight.get("analysis", "These ideas share common themes."),
                metadata=insight,
            )
            created_notifications.append(record)
    except Exception:
        logger.warning("scheduler.cross_idea.failed", exc_info=True)

    # -- User pattern learner -------------------------------------------------
    try:
        from app.db.repo_decision_events import DecisionEventRepository
        _event_repo = DecisionEventRepository()
        current_event_count = _event_repo.count_for_user(user_id="default")
        graph = build_pattern_learner_graph()
        result = await loop.run_in_executor(
            None,
            partial(graph.invoke, {
                "user_id": "default",
                "current_event_count": current_event_count,
                "decision_history": [],
                "learned_preferences": {},
                "agent_thoughts": [],
            }),
        )
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

    # -- Email dispatch -------------------------------------------------------
    for record in created_notifications:
        try:
            notifiable_users = _profile_repo.list_notifiable(record.type)
            for user_prefs in notifiable_users:
                if user_prefs.email:
                    send_notification_email(to=user_prefs.email, notification=record)
        except Exception:
            logger.warning("scheduler.email_dispatch.failed notification_id=%s", record.id, exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance. Does not start it.

    Uses trigger="date" with run_date=now+60s for the startup job to prevent
    the job from firing immediately when scheduler.start() is called (before
    the app is fully ready).
    """
    scheduler = AsyncIOScheduler()

    # IMPORTANT: compute run_date before scheduler.start() is called.
    # trigger="date", run_date=None fires immediately (before app is ready).
    # Using now+60s ensures the app is fully initialized when the job runs.
    startup_run_time = datetime.now(timezone.utc) + timedelta(seconds=60)

    scheduler.add_job(
        run_proactive_agents,
        trigger="date",
        run_date=startup_run_time,  # 60s from registration time, not None
        id="proactive_agents_startup",
        replace_existing=True,
        kwargs={"trigger_type": "startup"},
    )
    # Recurring every 6 hours
    scheduler.add_job(
        run_proactive_agents,
        trigger="interval",
        hours=6,
        id="proactive_agents",
        replace_existing=True,
        kwargs={"trigger_type": "scheduled"},
    )
    return scheduler
