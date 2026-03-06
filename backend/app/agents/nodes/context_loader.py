from __future__ import annotations

from datetime import datetime, timezone

from app.agents.memory.vector_store import get_vector_store
from app.agents.state import AgentThought, DecisionOSState


def context_loader_node(state: DecisionOSState) -> dict:
    """Load similar ideas and decision patterns from vector memory."""
    idea_seed = state["idea_seed"]
    idea_id = state["idea_id"]

    vs = get_vector_store()
    similar_ideas = vs.search_similar_ideas(
        query=idea_seed, n_results=3, exclude_id=idea_id,
    )
    patterns = vs.search_patterns(query=idea_seed, n_results=3)

    thought: AgentThought = {
        "agent": "context_loader",
        "action": "memory_retrieval",
        "detail": (
            f"Retrieved {len(similar_ideas)} similar ideas and "
            f"{len(patterns)} decision patterns from vector memory."
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "retrieved_similar_ideas": similar_ideas,
        "retrieved_patterns": patterns,
        "agent_thoughts": [thought],
    }
