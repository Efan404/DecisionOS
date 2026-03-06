from __future__ import annotations

import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END
from app.core import ai_gateway
from app.core.time import utc_now_iso


class PatternLearnerState(TypedDict):
    user_id: str
    decision_history: list[dict]
    learned_preferences: dict
    agent_thoughts: Annotated[list[dict], operator.add]


def _load_history(state: PatternLearnerState) -> dict:
    history = state.get("decision_history", [])
    thought = {
        "agent": "history_loader",
        "action": "loaded_history",
        "detail": f"Loaded {len(history)} decision records for pattern analysis",
        "timestamp": utc_now_iso(),
    }
    return {"agent_thoughts": [thought]}


def _extract_patterns(state: PatternLearnerState) -> dict:
    history = state.get("decision_history", [])

    if not history:
        return {
            "learned_preferences": {},
            "agent_thoughts": [{
                "agent": "pattern_extractor",
                "action": "no_history",
                "detail": "No decision history available yet",
                "timestamp": utc_now_iso(),
            }],
        }

    history_text = "\n".join(
        f"- Stage: {d.get('stage')}, Choice: {d.get('choice')}, Idea: {d.get('idea')}"
        for d in history
    )

    try:
        raw = ai_gateway.generate_text(
            task="opportunity",
            user_prompt=(
                "Analyze this user's product decision history and identify 2-3 patterns:\n"
                f"{history_text}\n\n"
                "Return a JSON object with keys: 'business_model_preference', 'risk_tolerance', "
                "'focus_area', 'decision_style'. Each value is a short string description."
            ),
        )
        import json
        try:
            preferences = json.loads(raw.strip().strip("`").strip())
        except json.JSONDecodeError:
            preferences = {"raw_analysis": raw.strip()}
    except Exception:
        preferences = {"analysis_status": "failed"}

    thought = {
        "agent": "pattern_extractor",
        "action": "extracted_patterns",
        "detail": f"Identified preferences: {', '.join(f'{k}={v}' for k, v in list(preferences.items())[:3])}",
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
