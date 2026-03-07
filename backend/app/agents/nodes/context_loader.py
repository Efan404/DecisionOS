from __future__ import annotations

from datetime import datetime, timezone

from app.agents.memory.vector_store import get_vector_store
from app.agents.nodes.evidence_retriever import retrieve_market_evidence_context
from app.agents.state import AgentThought, DecisionOSState


def context_loader_node(state: DecisionOSState) -> dict[str, object]:
    """Load similar ideas, decision patterns, and market evidence from vector memory.
    When stage is 'prd', also build the slim context dict shared by writer nodes.
    """
    idea_seed = state["idea_seed"]
    idea_id = state["idea_id"]
    stage = state.get("current_stage", "")

    vs = get_vector_store()
    similar_ideas = vs.search_similar_ideas(query=idea_seed, n_results=3, exclude_id=idea_id)
    patterns = vs.search_patterns(query=idea_seed, n_results=3)

    # Retrieve market evidence (graceful: never blocks on failure)
    evidence_context = retrieve_market_evidence_context(query=idea_seed)

    updates: dict[str, object] = {
        "retrieved_similar_ideas": similar_ideas,
        "retrieved_patterns": patterns,
        "market_evidence_context": evidence_context,
    }

    # Build slim PRD context once so parallel writer nodes share it
    if stage == "prd":
        dag_path = state.get("dag_path") or {}
        feasibility = state.get("feasibility_output") or {}
        scope = state.get("scope_output") or {}
        selected_plan_id = state.get("selected_plan_id", "")
        plans = feasibility.get("plans", [])
        selected_plan = next(
            (p for p in plans if p.get("id") == selected_plan_id),
            plans[0] if plans else {},
        )
        slim_ctx = {
            "idea_seed": idea_seed,
            "confirmed_path_summary": dag_path.get("path_summary", ""),
            "leaf_node_content": dag_path.get("leaf_node_content", idea_seed),
            "selected_plan": {
                "name": selected_plan.get("name", ""),
                "summary": selected_plan.get("summary", ""),
                "score_overall": selected_plan.get("score_overall", 0),
                "recommended_positioning": selected_plan.get("recommended_positioning", ""),
            },
            "in_scope": scope.get("in_scope", []),
            "out_scope": scope.get("out_scope", []),
        }
        updates["prd_slim_context"] = slim_ctx

    evidence_note = f" Retrieved {len(evidence_context)} chars of market evidence." if evidence_context else ""
    thought: AgentThought = {
        "agent": "context_loader",
        "action": "memory_retrieval",
        "detail": (
            f"Retrieved {len(similar_ideas)} similar ideas and "
            f"{len(patterns)} decision patterns from vector memory."
            + evidence_note
            + (f" Built PRD slim context for stage '{stage}'." if stage == "prd" else "")
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    updates["agent_thoughts"] = [thought]
    return updates
