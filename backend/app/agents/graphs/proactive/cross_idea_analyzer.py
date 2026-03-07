from __future__ import annotations

import logging
import operator
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END

from app.core.time import utc_now_iso
from app.db.repo_ideas import IdeaRepository

logger = logging.getLogger(__name__)


class CrossIdeaState(TypedDict):
    workspace_id: str
    idea_summaries: list[dict]
    insights: list[dict]  # V2 structured insights
    agent_thoughts: Annotated[list[dict], operator.add]


def _get_insights_service():
    """Try to import and instantiate the orchestration service.

    Returns the service instance or raises ImportError / Exception if
    the service module does not exist yet.
    """
    from app.services.cross_idea_insights_service import CrossIdeaInsightsService
    from app.agents.memory.vector_store import get_vector_store
    from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository
    from app.db.repo_market_signals import MarketSignalRepository
    from app.services.cross_idea_candidate_service import CrossIdeaCandidateService

    vs = get_vector_store()
    signal_repo = MarketSignalRepository()
    candidate_service = CrossIdeaCandidateService(
        vector_store=vs,
        signal_repo=signal_repo,
    )
    return CrossIdeaInsightsService(
        insight_repo=CrossIdeaInsightRepository(),
        candidate_service=candidate_service,
        idea_repo=IdeaRepository(),
        signal_repo=signal_repo,
        vector_store=vs,
    )


def _load_ideas(state: CrossIdeaState) -> dict[str, object]:
    """Load recently updated ideas from the database."""
    idea_repo = IdeaRepository()
    ideas, _ = idea_repo.list_ideas(
        statuses=["draft", "active", "frozen"],
        limit=20,
    )

    summaries = [
        {
            "idea_id": idea.id,
            "summary": idea.idea_seed or idea.title,
        }
        for idea in ideas
    ]
    thought = {
        "agent": "idea_loader",
        "action": "loaded_ideas",
        "detail": f"Loaded {len(summaries)} idea summaries from database",
        "timestamp": utc_now_iso(),
    }
    return {"idea_summaries": summaries, "agent_thoughts": [thought]}


def _analyze_ideas(state: CrossIdeaState) -> dict[str, object]:
    """Analyze ideas using the V2 orchestration service.

    Falls back gracefully if the service is unavailable (not yet implemented)
    or if any call raises an exception.
    """
    summaries = state.get("idea_summaries", [])
    workspace_id = state.get("workspace_id", "default")

    if len(summaries) < 2:
        return {
            "insights": [],
            "agent_thoughts": [{
                "agent": "cross_idea_analyzer",
                "action": "insufficient_ideas",
                "detail": f"Only {len(summaries)} ideas -- need >=2 for cross-analysis",
                "timestamp": utc_now_iso(),
            }],
        }

    # Try to get the orchestration service
    try:
        service = _get_insights_service()
    except Exception:
        logger.warning(
            "cross_idea_analyzer: orchestration service unavailable, returning empty insights",
            exc_info=True,
        )
        return {
            "insights": [],
            "agent_thoughts": [{
                "agent": "cross_idea_analyzer",
                "action": "service_unavailable",
                "detail": "CrossIdeaInsightsService not available; skipping analysis",
                "timestamp": utc_now_iso(),
            }],
        }

    insights: list[dict] = []
    seen_pairs: set[frozenset[str]] = set()

    for entry in summaries:
        idea_id = entry["idea_id"]
        try:
            records = service.analyze_anchor_idea(idea_id, workspace_id)
        except Exception:
            logger.warning(
                "cross_idea_analyzer: failed to analyze idea %s",
                idea_id,
                exc_info=True,
            )
            continue

        for rec in records:
            pair = frozenset({rec.idea_a_id, rec.idea_b_id})
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            insights.append({
                "id": rec.id,
                "idea_a_id": rec.idea_a_id,
                "idea_b_id": rec.idea_b_id,
                "insight_type": rec.insight_type,
                "summary": rec.summary,
                "why_it_matters": rec.why_it_matters,
                "recommended_action": rec.recommended_action,
                "confidence": rec.confidence,
                "similarity_score": rec.similarity_score,
            })

    thought = {
        "agent": "cross_idea_analyzer",
        "action": "analysis_complete",
        "detail": f"Produced {len(insights)} structured cross-idea insights",
        "timestamp": utc_now_iso(),
    }
    return {"insights": insights, "agent_thoughts": [thought]}


def build_cross_idea_graph():
    graph = StateGraph(CrossIdeaState)
    graph.add_node("load_ideas", _load_ideas)
    graph.add_node("analyze_ideas", _analyze_ideas)
    graph.add_edge(START, "load_ideas")
    graph.add_edge("load_ideas", "analyze_ideas")
    graph.add_edge("analyze_ideas", END)
    return graph.compile()
