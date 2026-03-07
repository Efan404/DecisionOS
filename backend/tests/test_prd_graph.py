from __future__ import annotations

import os

from unittest.mock import patch

from app.agents.state import DecisionOSState
from app.agents.graphs.prd_subgraph import build_prd_graph


def _make_mock_requirements():
    from app.schemas.prd import PRDRequirement
    return [
        PRDRequirement(
            id=f"req-00{i}",
            title=f"Requirement {i}",
            description=f"Description for requirement {i}",
            rationale=f"Rationale for requirement {i}",
            acceptance_criteria=[f"AC{i}-1", f"AC{i}-2"],
            source_refs=["step2"],
        )
        for i in range(1, 7)
    ]


def _make_mock_sections():
    from app.schemas.prd import PRDSection
    return [
        PRDSection(id=f"s{i}", title=f"Section {i}", content=f"Content for section {i}. Detailed explanation.")
        for i in range(1, 7)
    ]


def _mock_generate_structured(**kwargs):
    schema_model = kwargs.get("schema_model")
    from app.schemas.prd import (
        PRDRequirementsOutput, PRDMarkdownOutput, PRDBacklogOutput,
        PRDBacklog, PRDBacklogItem,
    )
    if schema_model is PRDRequirementsOutput:
        return PRDRequirementsOutput(requirements=_make_mock_requirements())
    if schema_model is PRDMarkdownOutput:
        return PRDMarkdownOutput(
            markdown="# Test PRD\n\nThis is a test PRD with enough content to pass review checks. "
                     "It covers core review functionality and all in-scope items thoroughly.",
            sections=_make_mock_sections(),
        )
    if schema_model is PRDBacklogOutput:
        return PRDBacklogOutput(
            backlog=PRDBacklog(
                items=[
                    PRDBacklogItem(
                        id=f"bl-00{i}",
                        title=f"Backlog item {i}",
                        requirement_id="req-001",
                        priority="P1",
                        type="story",
                        summary=f"Summary for backlog item {i}",
                        acceptance_criteria=[f"BL{i}-AC1", f"BL{i}-AC2"],
                        source_refs=["step2"],
                        depends_on=[],
                    )
                    for i in range(1, 9)
                ]
            )
        )
    # Fallback: return markdown output
    return PRDMarkdownOutput(
        markdown="# Fallback PRD",
        sections=_make_mock_sections(),
    )


@patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
def test_prd_graph_produces_requirements_markdown_and_backlog(mock_gen):
    """PRD graph generates requirements, markdown, backlog and runs reviewer."""
    graph = build_prd_graph()

    initial_state: DecisionOSState = {
        "idea_id": "test-id",
        "idea_seed": "AI code review tool",
        "current_stage": "prd",
        "opportunity_output": None,
        "dag_path": {"path_summary": "From idea to code review", "leaf_node_content": "Code review AI"},
        "feasibility_output": {"plans": [{"id": "plan1", "name": "Bootstrap", "summary": "Low cost"}]},
        "selected_plan_id": "plan1",
        "scope_output": {
            "in_scope": [{"title": "core review", "desc": "", "priority": "P1", "id": "s1"}],
            "out_scope": [],
        },
        "prd_output": None,
        "prd_slim_context": None,
        "prd_requirements": [],
        "prd_markdown": "",
        "prd_sections": [],
        "prd_backlog_items": [],
        "prd_review_issues": [],
        "agent_thoughts": [],
        "retrieved_patterns": [],
        "retrieved_similar_ideas": [],
        "user_preferences": None,
        "market_evidence_context": "",
    }

    result = graph.invoke(initial_state)

    # Requirements populated
    assert len(result["prd_requirements"]) == 6
    assert result["prd_requirements"][0]["id"] == "req-001"

    # Markdown populated
    assert "Test PRD" in result["prd_markdown"]
    assert len(result["prd_sections"]) == 6

    # Backlog populated
    assert len(result["prd_backlog_items"]) == 8

    # Agent thoughts include the right agents
    agents = [t["agent"] for t in result["agent_thoughts"]]
    assert "context_loader" in agents
    assert "requirements_writer" in agents
    assert "markdown_writer" in agents
    assert "backlog_writer" in agents
    assert "prd_reviewer" in agents
    assert "memory_writer" in agents


def test_prd_graph_has_expected_nodes():
    """Graph must contain all six nodes."""
    g = build_prd_graph()
    assert "context_loader" in g.nodes
    assert "requirements_writer" in g.nodes
    assert "markdown_writer" in g.nodes
    assert "backlog_writer" in g.nodes
    assert "prd_reviewer" in g.nodes
    assert "memory_writer" in g.nodes


def test_prd_graph_compiles_without_error():
    """build_prd_graph() should not raise."""
    g = build_prd_graph()
    assert g is not None


@patch("app.core.ai_gateway.generate_structured", side_effect=_mock_generate_structured)
def test_requirements_writer_node_uses_slim_context(mock_gen):
    """requirements_writer_node should call generate_structured with requirements schema."""
    from app.agents.graphs import prd_subgraph
    from app.schemas.prd import PRDRequirementsOutput, PRDRequirement

    state = {
        "idea_id": "i1", "idea_seed": "test", "current_stage": "prd",
        "prd_slim_context": {"idea_seed": "test", "in_scope": [], "out_scope": []},
        "retrieved_patterns": [], "retrieved_similar_ideas": [],
        "agent_thoughts": [],
    }
    result = prd_subgraph._requirements_writer_node(state)
    assert len(result["prd_requirements"]) == 6
    assert result["prd_requirements"][0]["id"] == "req-001"


def test_backlog_writer_skips_when_no_requirements():
    """backlog_writer should skip gracefully when prd_requirements is empty."""
    from app.agents.graphs.prd_subgraph import _backlog_writer_node
    state = {
        "idea_id": "i1", "idea_seed": "test", "current_stage": "prd",
        "prd_slim_context": {}, "prd_requirements": [], "agent_thoughts": [],
    }
    result = _backlog_writer_node(state)
    assert result["prd_backlog_items"] == []
    assert "skipped" in result["agent_thoughts"][0]["action"]
