from __future__ import annotations

import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END
from app.agents.memory.vector_store import get_vector_store
from app.core import ai_gateway
from app.core.time import utc_now_iso


class CrossIdeaState(TypedDict):
    user_id: str
    idea_summaries: list[dict]
    insights: list[dict]
    agent_thoughts: Annotated[list[dict], operator.add]


def _collect_ideas(state: CrossIdeaState) -> dict[str, object]:
    summaries = state.get("idea_summaries", [])
    thought = {
        "agent": "idea_collector",
        "action": "collected_ideas",
        "detail": f"Analyzing {len(summaries)} ideas for cross-idea patterns",
        "timestamp": utc_now_iso(),
    }
    return {"agent_thoughts": [thought]}


def _detect_patterns(state: CrossIdeaState) -> dict[str, object]:
    summaries = state.get("idea_summaries", [])
    vs = get_vector_store()
    insights: list[dict] = []

    for i, idea_a in enumerate(summaries):
        similar = vs.search_similar_ideas(
            query=idea_a.get("summary", ""),
            n_results=3,
            exclude_id=idea_a.get("idea_id"),
        )
        for match in similar:
            if match.get("distance", 1.0) < 0.4:
                insights.append({
                    "type": "similar_ideas",
                    "idea_a_id": idea_a["idea_id"],
                    "idea_b_id": match["idea_id"],
                    "similarity": 1.0 - match.get("distance", 0),
                    "idea_a_summary": idea_a.get("summary", "")[:100],
                    "idea_b_summary": match.get("summary", "")[:100],
                })

    thought = {
        "agent": "pattern_detector",
        "action": "detected_patterns",
        "detail": f"Found {len(insights)} cross-idea relationships",
        "timestamp": utc_now_iso(),
    }
    return {"insights": insights, "agent_thoughts": [thought]}


def _generate_cross_insights(state: CrossIdeaState) -> dict[str, object]:
    insights = state.get("insights", [])
    enriched: list[dict] = []

    for insight in insights[:5]:
        try:
            raw = ai_gateway.generate_text(
                task="opportunity",
                user_prompt=(
                    f"Two product ideas are similar:\n"
                    f"Idea A: {insight.get('idea_a_summary', '')}\n"
                    f"Idea B: {insight.get('idea_b_summary', '')}\n"
                    "In 1-2 sentences, explain what they have in common and suggest how the user "
                    "could combine or differentiate them. Return plain text."
                ),
            )
            insight["analysis"] = raw.strip()
        except Exception:
            insight["analysis"] = "These ideas share common themes and could be combined."
        enriched.append(insight)

    thought = {
        "agent": "insight_generator",
        "action": "generated_cross_insights",
        "detail": f"Generated analysis for {len(enriched)} idea relationships",
        "timestamp": utc_now_iso(),
    }
    return {"insights": enriched, "agent_thoughts": [thought]}


def build_cross_idea_graph():
    graph = StateGraph(CrossIdeaState)
    graph.add_node("collect_ideas", _collect_ideas)
    graph.add_node("detect_patterns", _detect_patterns)
    graph.add_node("generate_insights", _generate_cross_insights)
    graph.add_edge(START, "collect_ideas")
    graph.add_edge("collect_ideas", "detect_patterns")
    graph.add_edge("detect_patterns", "generate_insights")
    graph.add_edge("generate_insights", END)
    return graph.compile()
