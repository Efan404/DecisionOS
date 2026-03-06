from __future__ import annotations

import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END

from app.core import ai_gateway
from app.core.time import utc_now_iso
from app.agents.memory.vector_store import get_vector_store

SIMILARITY_THRESHOLD = 0.40  # cosine distance: lower = more similar


class CrossIdeaState(TypedDict):
    user_id: str
    idea_summaries: list[dict]
    insights: list[dict]
    agent_thoughts: Annotated[list[dict], operator.add]


def _load_ideas(state: CrossIdeaState) -> dict[str, object]:
    """Load all ideas from the vector store."""
    vs = get_vector_store()
    data = vs._ideas.get(include=["documents", "metadatas"])
    ids = data.get("ids") or []
    docs = data.get("documents") or []

    summaries = [
        {"idea_id": id_, "summary": doc}
        for id_, doc in zip(ids, docs)
        if doc and doc.strip()
    ]
    thought = {
        "agent": "idea_loader",
        "action": "loaded_ideas",
        "detail": f"Loaded {len(summaries)} idea summaries from vector store",
        "timestamp": utc_now_iso(),
    }
    return {"idea_summaries": summaries, "agent_thoughts": [thought]}


def _find_similar_pairs(state: CrossIdeaState) -> dict[str, object]:
    """Find pairs of ideas with high vector similarity."""
    summaries = state.get("idea_summaries", [])
    if len(summaries) < 2:
        return {
            "insights": [],
            "agent_thoughts": [{
                "agent": "similarity_finder",
                "action": "insufficient_ideas",
                "detail": f"Only {len(summaries)} ideas -- need >=2 for cross-analysis",
                "timestamp": utc_now_iso(),
            }],
        }

    vs = get_vector_store()
    insights = []
    seen_pairs: set[frozenset[str]] = set()

    for entry in summaries:
        idea_a_id = entry["idea_id"]
        summary_a = entry["summary"]

        # Search for similar ideas (exclude self)
        count = vs._ideas.count()
        if count < 2:
            continue
        results = vs._ideas.query(
            query_texts=[summary_a],
            n_results=min(3, count),
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for idea_b_id, dist in zip(ids, distances):
            if idea_b_id == idea_a_id:
                continue
            pair = frozenset({idea_a_id, idea_b_id})
            if pair in seen_pairs:
                continue
            if dist < SIMILARITY_THRESHOLD:
                seen_pairs.add(pair)
                summary_b = next(
                    (s["summary"] for s in summaries if s["idea_id"] == idea_b_id),
                    idea_b_id,
                )
                # Use LLM to generate a specific insight about the relationship
                try:
                    analysis = ai_gateway.generate_text(
                        task="opportunity",
                        user_prompt=(
                            f"Two product ideas appear related:\n"
                            f"Idea A: {summary_a[:150]}\n"
                            f"Idea B: {summary_b[:150]}\n\n"
                            "In 1-2 sentences, explain the strategic overlap or synergy. "
                            "Be specific -- mention actual product features, not generic statements."
                        ),
                    )
                except Exception:
                    analysis = f"Ideas share a similarity score of {round(1 - dist, 2):.0%}."

                insights.append({
                    "idea_a_id": idea_a_id,
                    "idea_b_id": idea_b_id,
                    "similarity_distance": round(dist, 3),
                    "analysis": analysis.strip(),
                })

    thought = {
        "agent": "similarity_finder",
        "action": "found_pairs",
        "detail": f"Found {len(insights)} cross-idea relationships above threshold",
        "timestamp": utc_now_iso(),
    }
    return {"insights": insights, "agent_thoughts": [thought]}


def build_cross_idea_graph():
    graph = StateGraph(CrossIdeaState)
    graph.add_node("load_ideas", _load_ideas)
    graph.add_node("find_similar_pairs", _find_similar_pairs)
    graph.add_edge(START, "load_ideas")
    graph.add_edge("load_ideas", "find_similar_pairs")
    graph.add_edge("find_similar_pairs", END)
    return graph.compile()
