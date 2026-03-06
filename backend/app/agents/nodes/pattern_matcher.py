from __future__ import annotations

import logging

from app.agents.state import DecisionOSState, AgentThought
from app.agents.memory.vector_store import get_vector_store
from app.core.time import utc_now_iso

logger = logging.getLogger(__name__)


def pattern_matcher_node(state: DecisionOSState) -> dict:
    """Match current stage output against historical decision patterns."""
    idea_seed = state["idea_seed"]
    stage = state["current_stage"]

    vs = get_vector_store()
    patterns = vs.search_patterns(query=f"{idea_seed} {stage}", n_results=3)

    if not patterns:
        thought: AgentThought = {
            "agent": "pattern_matcher",
            "action": "no_patterns_found",
            "detail": "No historical patterns found for this idea type",
            "timestamp": utc_now_iso(),
        }
        return {"agent_thoughts": [thought]}

    pattern_descriptions = "; ".join(p.get("description", "")[:80] for p in patterns)
    thought: AgentThought = {
        "agent": "pattern_matcher",
        "action": "matched_patterns",
        "detail": f"Found {len(patterns)} relevant patterns: {pattern_descriptions}",
        "timestamp": utc_now_iso(),
    }

    logger.info("pattern_matcher idea_id=%s matched=%d", state["idea_id"], len(patterns))
    return {"retrieved_patterns": patterns, "agent_thoughts": [thought]}
