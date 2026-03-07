from __future__ import annotations

import os

from unittest.mock import patch

from app.agents.state import DecisionOSState
from app.agents.graphs.feasibility_subgraph import build_feasibility_graph


def _mock_generate_structured(**kwargs):
    schema_model = kwargs.get("schema_model")

    from app.schemas.common import ScoreBreakdown, ReasoningBreakdown
    from app.schemas.feasibility import Plan

    # Check if we're generating a single Plan
    if schema_model == Plan or (hasattr(schema_model, "__name__") and schema_model.__name__ == "Plan"):
        return Plan(
            id="plan1",
            name="Bootstrap Plan",
            summary="Low-cost MVP approach",
            score_overall=8.0,
            scores=ScoreBreakdown(technical_feasibility=8.0, market_viability=7.5, execution_risk=7.0),
            reasoning=ReasoningBreakdown(
                technical_feasibility="Feasible", market_viability="Good", execution_risk="Moderate"
            ),
            recommended_positioning="B2B SaaS",
        )
    # Fallback
    return Plan(
        id="plan1", name="Plan", summary="Summary", score_overall=7.0,
        scores=ScoreBreakdown(technical_feasibility=7.0, market_viability=7.0, execution_risk=7.0),
        reasoning=ReasoningBreakdown(technical_feasibility="ok", market_viability="ok", execution_risk="ok"),
        recommended_positioning="Position",
    )


@patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
def test_feasibility_graph_produces_plans_and_synthesis(mock_gen):
    """Feasibility subgraph generates plans and runs synthesizer."""
    graph = build_feasibility_graph()

    initial_state: DecisionOSState = {
        "idea_id": "test-id",
        "idea_seed": "AI code review tool",
        "current_stage": "feasibility",
        "opportunity_output": None,
        "dag_path": {"path_summary": "From idea to code review focus"},
        "feasibility_output": None,
        "selected_plan_id": None,
        "scope_output": None,
        "prd_output": None,
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
        "market_evidence_context": "",
    }

    result = graph.invoke(initial_state)

    assert result["feasibility_output"] is not None
    plans = result["feasibility_output"]["plans"]
    assert len(plans) == 3

    agents = [t["agent"] for t in result["agent_thoughts"]]
    assert "plan_synthesizer" in agents
