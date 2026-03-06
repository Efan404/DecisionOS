from __future__ import annotations

import logging

from app.agents.state import DecisionOSState, AgentThought
from app.core.time import utc_now_iso

logger = logging.getLogger(__name__)


def plan_synthesizer_node(state: DecisionOSState) -> dict:
    """Cross-evaluate and rank the generated plans, add synthesis commentary."""
    plans = state.get("feasibility_output", {}).get("plans", []) if state.get("feasibility_output") else []

    if not plans:
        thought: AgentThought = {
            "agent": "plan_synthesizer",
            "action": "no_plans_to_synthesize",
            "detail": "No plans available for synthesis",
            "timestamp": utc_now_iso(),
        }
        return {"agent_thoughts": [thought]}

    # Sort plans by score_overall descending
    sorted_plans = sorted(plans, key=lambda p: p.get("score_overall", 0), reverse=True)
    best = sorted_plans[0]

    detail = (
        f"Analyzed {len(plans)} plans. "
        f"Recommended: '{best.get('name', 'Unknown')}' (score: {best.get('score_overall', 0)}). "
        f"Key strength: {best.get('recommended_positioning', 'N/A')}"
    )

    thought: AgentThought = {
        "agent": "plan_synthesizer",
        "action": "synthesized_plans",
        "detail": detail,
        "timestamp": utc_now_iso(),
    }

    # Update feasibility_output with sorted plans
    updated_output = dict(state["feasibility_output"])
    updated_output["plans"] = sorted_plans

    logger.info("plan_synthesizer idea_id=%s best=%s", state["idea_id"], best.get("name"))
    return {"feasibility_output": updated_output, "agent_thoughts": [thought]}
