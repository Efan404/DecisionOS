from __future__ import annotations

import os


from unittest.mock import patch

from app.agents.state import DecisionOSState
from app.agents.graphs.opportunity_subgraph import build_opportunity_graph


def _mock_generate_structured(**kwargs):
    from app.schemas.common import Direction
    from app.schemas.idea import OpportunityOutput

    return OpportunityOutput(
        directions=[
            Direction(id="A", title="Direction A", one_liner="One-liner A", pain_tags=["tag1"]),
            Direction(id="B", title="Direction B", one_liner="One-liner B", pain_tags=["tag2"]),
            Direction(id="C", title="Direction C", one_liner="One-liner C", pain_tags=["tag3"]),
        ]
    )


@patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
def test_opportunity_graph_produces_output_and_thoughts(mock_gen):
    graph = build_opportunity_graph()
    initial_state: DecisionOSState = {
        "idea_id": "test-id",
        "idea_seed": "AI code review tool",
        "current_stage": "opportunity",
        "opportunity_output": None,
        "dag_path": None,
        "feasibility_output": None,
        "selected_plan_id": None,
        "scope_output": None,
        "prd_output": None,
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
    }
    result = graph.invoke(initial_state)
    assert result["opportunity_output"] is not None
    assert len(result["opportunity_output"]["directions"]) == 3
    assert len(result["agent_thoughts"]) >= 2
    agents = [t["agent"] for t in result["agent_thoughts"]]
    assert "context_loader" in agents
    assert "direction_generator" in agents
