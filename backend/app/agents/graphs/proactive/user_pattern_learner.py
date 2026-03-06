from __future__ import annotations

import json
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core import ai_gateway
from app.core.time import utc_now_iso
from app.db.repo_decision_events import DecisionEventRepository
from app.db.repo_profile import ProfileRepository


class PatternLearnerState(TypedDict):
    user_id: str
    current_event_count: int  # real DB total, passed in at graph.invoke time
    decision_history: list[dict]
    learned_preferences: dict
    agent_thoughts: Annotated[list[dict], operator.add]


_event_repo = DecisionEventRepository()
_profile_repo = ProfileRepository()


def _load_history(state: PatternLearnerState) -> dict[str, object]:
    """Load real decision events from DB for the user."""
    user_id = state.get("user_id", "default")
    events = _event_repo.list_for_user(user_id=user_id, limit=50)

    history = []
    for e in events:
        payload = e.payload
        history.append({
            "stage": e.event_type,
            "choice": payload.get("plan_name") or payload.get("path_id") or e.event_type,
            "idea": e.idea_id or "",
            "detail": payload,
        })

    thought = {
        "agent": "history_loader",
        "action": "loaded_history",
        "detail": f"Loaded {len(history)} real decision events from DB for user '{user_id}'",
        "timestamp": utc_now_iso(),
    }
    return {"decision_history": history, "agent_thoughts": [thought]}


def _extract_patterns(state: PatternLearnerState) -> dict[str, object]:
    """Use LLM to extract preference patterns from real history."""
    history = state.get("decision_history", [])
    user_id = state.get("user_id", "default")
    event_count = state.get("current_event_count", 0)

    if not history:
        return {
            "learned_preferences": {},
            "agent_thoughts": [{
                "agent": "pattern_extractor",
                "action": "no_history",
                "detail": "No decision history available yet — returning empty preferences",
                "timestamp": utc_now_iso(),
            }],
        }

    history_text = "\n".join(
        f"- Event: {d.get('stage')}, Choice: {d.get('choice')}, Idea: {d.get('idea')}"
        for d in history[:30]  # cap at 30 to avoid token overflow
    )

    try:
        raw = ai_gateway.generate_text(
            task="opportunity",
            user_prompt=(
                "Analyze this user's product decision history and identify key patterns.\n\n"
                f"Decision history:\n{history_text}\n\n"
                "Return a JSON object with these keys:\n"
                "- business_model_preference: short description (e.g. 'Bootstrapped, minimal investment')\n"
                "- risk_tolerance: short description (e.g. 'Low — prefers incremental MVPs')\n"
                "- focus_area: product domain pattern (e.g. 'Developer tools and AI productivity')\n"
                "- decision_style: how they make choices (e.g. 'Data-driven, iterative')\n"
                "Each value must be a specific, evidence-based string of <=15 words.\n"
                "Return only valid JSON."
            ),
        )
        try:
            preferences = json.loads(raw.strip().strip("`").strip())
            if not isinstance(preferences, dict):
                preferences = {"raw_analysis": str(preferences)}
        except json.JSONDecodeError:
            preferences = {"raw_analysis": raw.strip()[:200]}
    except Exception as exc:
        preferences = {"analysis_status": f"failed: {exc}"}

    # Persist to DB using real DB event_count for accurate cache invalidation
    _profile_repo.save_learned_patterns(
        user_id=user_id,
        patterns=preferences,
        event_count=event_count,
    )

    thought = {
        "agent": "pattern_extractor",
        "action": "extracted_patterns",
        "detail": f"Extracted {len(preferences)} pattern keys from {len(history)} real events",
        "timestamp": utc_now_iso(),
    }
    return {"learned_preferences": preferences, "agent_thoughts": [thought]}


def build_pattern_learner_graph():
    graph = StateGraph(PatternLearnerState)
    graph.add_node("load_history", _load_history)
    graph.add_node("extract_patterns", _extract_patterns)
    graph.add_edge(START, "load_history")
    graph.add_edge("load_history", "extract_patterns")
    graph.add_edge("extract_patterns", END)
    return graph.compile()
