"""Tests for the V2 cross-idea analyzer graph.

CI-4: Replace proactive cross-idea analyzer with V2 behavior.
"""
from __future__ import annotations

import os

import pytest
from unittest.mock import patch, MagicMock
from tests._test_env import ensure_required_seed_env


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    ensure_required_seed_env()
    os.environ["DECISIONOS_DB_PATH"] = str(tmp_path / "test.db")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    from app.db.bootstrap import initialize_database

    initialize_database()


@pytest.fixture(autouse=True)
def fresh_vector_store(monkeypatch, tmp_path):
    import app.agents.memory.vector_store as vs_mod
    from app.agents.memory.vector_store import VectorStore

    isolated = VectorStore(persist_directory=str(tmp_path / "chroma"))
    vs_mod._singleton = None
    monkeypatch.setattr(vs_mod, "get_vector_store", lambda: isolated)
    yield isolated
    vs_mod._singleton = None


def _make_idea(title, seed="seed"):
    from app.db.repo_ideas import IdeaRepository

    return IdeaRepository().create_idea(title=title, idea_seed=seed)


# ---------------------------------------------------------------------------
# Test 1: _load_ideas loads from DB (not vector store)
# ---------------------------------------------------------------------------

def test_v2_analyzer_loads_ideas_from_db():
    """_load_ideas node should load ideas from the database via IdeaRepository,
    not from the vector store. Creating ideas in DB should populate idea_summaries."""
    idea_a = _make_idea("AI Code Review Tool", seed="An AI-powered code review tool")
    idea_b = _make_idea("Developer Dashboard", seed="A real-time developer dashboard")

    from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph

    graph = build_cross_idea_graph()
    result = graph.invoke({
        "workspace_id": "default",
        "idea_summaries": [],
        "insights": [],
        "agent_thoughts": [],
    })

    summaries = result["idea_summaries"]
    # Should have loaded both ideas from DB
    assert len(summaries) >= 2
    loaded_ids = {s["idea_id"] for s in summaries}
    assert idea_a.id in loaded_ids
    assert idea_b.id in loaded_ids

    # Each summary dict should have idea_id and summary keys
    for s in summaries:
        assert "idea_id" in s
        assert "summary" in s


# ---------------------------------------------------------------------------
# Test 2: Structured V2 insights via mocked orchestration service
# ---------------------------------------------------------------------------

def test_v2_analyzer_produces_structured_insights():
    """When the orchestration service is available and returns InsightRecords,
    the graph output should contain V2-shaped insight dicts with the correct keys."""
    idea_a = _make_idea("AI Code Review", seed="An AI-powered code review tool")
    idea_b = _make_idea("AI Bug Finder", seed="An AI bug detection tool")

    from app.db.repo_cross_idea_insights import InsightRecord

    mock_insight = InsightRecord(
        id="insight-001",
        workspace_id="default",
        idea_a_id=idea_a.id,
        idea_b_id=idea_b.id,
        insight_type="merge_candidate",
        summary="Both ideas leverage AI for code quality improvement",
        why_it_matters="Merging could reduce development effort by 40%",
        recommended_action="Consider merging into a single AI code quality suite",
        confidence=0.85,
        similarity_score=0.72,
        evidence_json=None,
        fingerprint="test-fp",
        created_at="2026-03-07T00:00:00Z",
        updated_at="2026-03-07T00:00:00Z",
    )

    mock_service = MagicMock()
    mock_service.analyze_anchor_idea.return_value = [mock_insight]

    with patch(
        "app.agents.graphs.proactive.cross_idea_analyzer._get_insights_service",
        return_value=mock_service,
    ):
        from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph

        graph = build_cross_idea_graph()
        result = graph.invoke({
            "workspace_id": "default",
            "idea_summaries": [],
            "insights": [],
            "agent_thoughts": [],
        })

    insights = result["insights"]
    assert len(insights) >= 1

    # Find our mock insight
    matching = [i for i in insights if i["idea_a_id"] == idea_a.id and i["idea_b_id"] == idea_b.id]
    assert len(matching) >= 1

    insight = matching[0]
    # Verify V2 structure keys
    assert insight["id"] == "insight-001"
    assert insight["insight_type"] == "merge_candidate"
    assert insight["summary"] == "Both ideas leverage AI for code quality improvement"
    assert insight["why_it_matters"] == "Merging could reduce development effort by 40%"
    assert insight["recommended_action"] == "Consider merging into a single AI code quality suite"
    assert insight["confidence"] == 0.85
    assert insight["similarity_score"] == 0.72


# ---------------------------------------------------------------------------
# Test 3: Graceful fallback when orchestration service is unavailable
# ---------------------------------------------------------------------------

def test_v2_analyzer_graceful_without_orchestration_service():
    """If the orchestration service import fails or the service call raises,
    the graph should complete without error and return empty insights."""
    _make_idea("AI Code Review", seed="An AI-powered code review tool")
    _make_idea("AI Bug Finder", seed="An AI bug detection tool")

    # Simulate the service not existing / raising ImportError
    with patch(
        "app.agents.graphs.proactive.cross_idea_analyzer._get_insights_service",
        side_effect=ImportError("Service not available"),
    ):
        from app.agents.graphs.proactive.cross_idea_analyzer import build_cross_idea_graph

        graph = build_cross_idea_graph()
        result = graph.invoke({
            "workspace_id": "default",
            "idea_summaries": [],
            "insights": [],
            "agent_thoughts": [],
        })

    # Should complete without error
    assert "insights" in result
    assert isinstance(result["insights"], list)
    # Insights should be empty since the service was unavailable
    assert len(result["insights"]) == 0

    # idea_summaries should still be populated (load step works independently)
    assert len(result["idea_summaries"]) >= 2

    # Should have agent_thoughts indicating the graceful fallback
    thoughts = result["agent_thoughts"]
    assert len(thoughts) >= 1
