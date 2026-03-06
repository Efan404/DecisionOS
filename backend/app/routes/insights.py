from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/user-patterns")
async def get_user_patterns() -> dict:
    """Return learned user patterns.

    Fast path: return cached patterns if event_count hasn't changed since last learning.
    Slow path: re-run the pattern learner graph when new events have been recorded.
    """
    from app.agents.graphs.proactive.user_pattern_learner import build_pattern_learner_graph
    from app.db.repo_decision_events import DecisionEventRepository
    from app.db.repo_profile import ProfileRepository

    profile_repo = ProfileRepository()
    event_repo = DecisionEventRepository()

    current_event_count = event_repo.count_for_user()
    cached_patterns, last_learned_count = profile_repo.get_learned_patterns()

    # Fast path: cached patterns are still valid (no new events since last learning)
    if (
        cached_patterns
        and current_event_count > 0
        and current_event_count == last_learned_count
    ):
        return {
            "preferences": cached_patterns,
            "source": "cached",
            "event_count": current_event_count,
        }

    if current_event_count == 0:
        return {"preferences": {}, "source": "no_events", "event_count": 0}

    # Slow path: new events have appeared — re-run graph and update cache
    graph = build_pattern_learner_graph()
    result = graph.invoke({
        "user_id": "default",
        "current_event_count": current_event_count,
        "decision_history": [],
        "learned_preferences": {},
        "agent_thoughts": [],
    })

    return {
        "preferences": result.get("learned_preferences", {}),
        "source": "computed",
        "event_count": current_event_count,
    }
