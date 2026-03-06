from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from unittest.mock import patch

from app.agents.state import DecisionOSState
from app.agents.graphs.prd_subgraph import build_prd_graph


def _mock_generate_structured(**kwargs):
    from app.schemas.prd import PRDMarkdownOutput
    return PRDMarkdownOutput(
        markdown="# Test PRD\n\nThis is a test PRD with enough content to pass review checks.",
        sections=[
            {"id": "s1", "title": "Executive Summary", "content": "Test executive summary content."},
            {"id": "s2", "title": "Problem Statement", "content": "Test problem statement content."},
            {"id": "s3", "title": "User Personas", "content": "Test user personas content."},
            {"id": "s4", "title": "Key Capabilities", "content": "Test key capabilities content."},
            {"id": "s5", "title": "Out of Scope", "content": "Test out of scope content."},
            {"id": "s6", "title": "Success Metrics", "content": "Test success metrics content."},
        ],
    )


@patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
def test_prd_graph_produces_markdown_and_review(mock_gen):
    """PRD subgraph generates markdown and runs critic review."""
    graph = build_prd_graph()

    initial_state: DecisionOSState = {
        "idea_id": "test-id",
        "idea_seed": "AI code review tool",
        "current_stage": "prd",
        "opportunity_output": None,
        "dag_path": {"path_summary": "From idea to code review"},
        "feasibility_output": {"plans": [{"name": "Bootstrap", "summary": "Low cost"}]},
        "selected_plan_id": "plan1",
        "scope_output": {"in_scope": [{"title": "Core review"}], "out_scope": []},
        "prd_output": None,
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
    }

    result = graph.invoke(initial_state)

    assert result["prd_output"] is not None
    assert "markdown" in result["prd_output"]
    agents = [t["agent"] for t in result["agent_thoughts"]]
    assert "prd_writer" in agents
    assert "prd_reviewer" in agents
