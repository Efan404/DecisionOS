from __future__ import annotations

from datetime import datetime, timezone

from app.agents.memory.vector_store import get_vector_store
from app.agents.state import AgentThought, DecisionOSState


def memory_writer_node(state: DecisionOSState) -> dict:
    """Write stage-appropriate data back into vector memory."""
    vs = get_vector_store()
    stage = state["current_stage"]
    idea_id = state["idea_id"]
    detail_parts: list[str] = []

    if stage == "opportunity" and state.get("opportunity_output"):
        output = state["opportunity_output"]
        directions = output.get("directions", [])
        if directions:
            titles = [d.get("title", "") for d in directions]
            summary = f"Idea exploring: {state['idea_seed']}. Directions: {', '.join(titles)}"
            vs.add_idea_summary(idea_id=idea_id, summary=summary)
            detail_parts.append(f"Wrote idea summary with {len(directions)} directions to vector store.")

    elif stage == "feasibility" and state.get("feasibility_output"):
        output = state["feasibility_output"]
        plans = output.get("plans", [])
        if plans:
            for plan in plans:
                plan_name = plan.get("name", "unnamed")
                plan_summary = plan.get("summary", "")
                pattern_id = f"{idea_id}-{plan.get('id', 'plan')}"
                vs.add_decision_pattern(
                    pattern_id=pattern_id,
                    description=f"Feasibility plan '{plan_name}': {plan_summary}",
                )
            detail_parts.append(f"Wrote {len(plans)} feasibility patterns to vector store.")

    if not detail_parts:
        detail_parts.append(f"No data to write for stage '{stage}'.")

    thought: AgentThought = {
        "agent": "memory_writer",
        "action": "write_memory",
        "detail": " ".join(detail_parts),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {"agent_thoughts": [thought]}
