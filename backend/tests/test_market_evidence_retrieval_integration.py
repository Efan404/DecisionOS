"""Tests for market evidence retrieval and injection into feasibility/PRD context."""
from __future__ import annotations

import os
import pytest
from tests._test_env import ensure_required_seed_env


@pytest.fixture(autouse=True)
def fresh_env(tmp_path):
    """Reset settings and vector store singleton for each test."""
    ensure_required_seed_env()
    os.environ["DECISIONOS_DB_PATH"] = str(tmp_path / "test.db")

    from app.core.settings import get_settings
    get_settings.cache_clear()

    from app.db.bootstrap import initialize_database
    initialize_database()

    # Create a fresh in-memory VectorStore and clear market_evidence collection
    # to avoid cross-test pollution (chromadb in-memory clients share state)
    import app.agents.memory.vector_store as vs_mod
    fresh_vs = vs_mod.VectorStore(persist_directory=None)
    # Wipe market_evidence collection to ensure test isolation
    try:
        fresh_vs._client.delete_collection("market_evidence")
        fresh_vs._market_evidence = fresh_vs._client.get_or_create_collection(
            name="market_evidence", metadata={"hnsw:space": "cosine"}
        )
    except Exception:
        pass
    vs_mod._singleton = fresh_vs
    yield
    vs_mod._singleton = None


# ---------------------------------------------------------------------------
# Helper: build a fresh in-memory VectorStore for testing
# ---------------------------------------------------------------------------

def _get_vs():
    from app.agents.memory.vector_store import get_vector_store
    return get_vector_store()


# ===========================================================================
# Test 1: evidence retrieval returns non-empty context
# ===========================================================================

def test_evidence_retrieval_returns_context():
    """Add evidence chunks to vector store, retrieve, verify non-empty context."""
    vs = _get_vs()
    vs.add_competitor_chunk(
        "comp-1",
        "Notion is a popular workspace tool offering docs, wikis, and project management.",
        {"source_type": "competitor", "competitor_name": "Notion"},
    )
    vs.add_market_signal_chunk(
        "signal-1",
        "The productivity SaaS market is projected to reach $100B by 2027.",
        {"source_type": "market_signal"},
    )

    from app.agents.nodes.evidence_retriever import retrieve_market_evidence_context
    result = retrieve_market_evidence_context("productivity workspace tool")

    assert isinstance(result, str)
    assert len(result) > 0
    # Should contain some reference to the evidence we added
    assert "Notion" in result or "productivity" in result.lower()


# ===========================================================================
# Test 2: empty store returns empty string
# ===========================================================================

def test_evidence_retrieval_empty_store():
    """Empty vector store returns empty string."""
    from app.agents.nodes.evidence_retriever import retrieve_market_evidence_context
    result = retrieve_market_evidence_context("some random query about widgets")
    assert result == ""


# ===========================================================================
# Test 3: token budget respected
# ===========================================================================

def test_evidence_context_respects_token_budget():
    """Add many large chunks, verify output is within 800 token budget."""
    vs = _get_vs()

    # Add 10 large chunks, each ~1000 chars
    for i in range(10):
        large_text = f"Competitor-{i}: " + ("This is a very detailed analysis of the market. " * 20)
        vs.add_competitor_chunk(
            f"large-{i}",
            large_text,
            {"source_type": "competitor", "competitor_name": f"BigCorp-{i}"},
        )

    from app.agents.nodes.evidence_retriever import retrieve_market_evidence_context
    result = retrieve_market_evidence_context("market analysis competitor")

    # Token budget: len(text) // 4 <= 800 → len(text) <= 3200
    assert len(result) // 4 <= 800, (
        f"Evidence context exceeds token budget: {len(result)} chars "
        f"(~{len(result) // 4} tokens, limit 800)"
    )


# ===========================================================================
# Test 4: feasibility context includes evidence (via context_loader_node)
# ===========================================================================

def test_feasibility_context_includes_evidence():
    """When evidence exists, context_loader_node includes it in market_evidence_context."""
    vs = _get_vs()
    vs.add_competitor_chunk(
        "comp-feas-1",
        "Trello is a popular kanban board for project management used by millions.",
        {"source_type": "competitor", "competitor_name": "Trello"},
    )

    from app.agents.nodes.context_loader import context_loader_node

    state = {
        "idea_id": "test-idea-1",
        "idea_seed": "kanban project management tool",
        "current_stage": "feasibility",
        "opportunity_output": None,
        "dag_path": {"path_summary": "project management", "leaf_node_content": "kanban tool"},
        "feasibility_output": None,
        "selected_plan_id": None,
        "scope_output": None,
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
    }

    updates = context_loader_node(state)
    evidence = updates.get("market_evidence_context", "")
    assert isinstance(evidence, str)
    assert len(evidence) > 0, "Expected non-empty market evidence context"
    assert "Trello" in evidence or "kanban" in evidence.lower()


# ===========================================================================
# Test 5: absence of evidence does not block
# ===========================================================================

def test_absence_of_evidence_does_not_block():
    """Verify context_loader works fine without any evidence in vector store."""
    from app.agents.nodes.context_loader import context_loader_node

    state = {
        "idea_id": "test-idea-2",
        "idea_seed": "some completely novel idea",
        "current_stage": "feasibility",
        "opportunity_output": None,
        "dag_path": {"path_summary": "novel path", "leaf_node_content": "novel idea"},
        "feasibility_output": None,
        "selected_plan_id": None,
        "scope_output": None,
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
    }

    updates = context_loader_node(state)

    # Should still return valid updates
    assert "retrieved_similar_ideas" in updates
    assert "retrieved_patterns" in updates
    assert "agent_thoughts" in updates
    # market_evidence_context should be empty string
    evidence = updates.get("market_evidence_context", "")
    assert evidence == ""


# ===========================================================================
# Test 6: PRD slim context includes evidence
# ===========================================================================

def test_prd_context_includes_evidence():
    """When evidence exists and stage is prd, context_loader injects evidence into prd_slim_context."""
    vs = _get_vs()
    vs.add_competitor_chunk(
        "comp-prd-1",
        "Linear is a modern issue tracker emphasizing speed and developer experience.",
        {"source_type": "competitor", "competitor_name": "Linear"},
    )

    from app.agents.nodes.context_loader import context_loader_node

    state = {
        "idea_id": "test-idea-3",
        "idea_seed": "fast issue tracker for developers",
        "current_stage": "prd",
        "opportunity_output": None,
        "dag_path": {"path_summary": "issue tracking", "leaf_node_content": "developer issue tracker"},
        "feasibility_output": {"plans": [{"id": "plan1", "name": "Test", "summary": "A test plan", "score_overall": 8.0, "recommended_positioning": "dev-first"}]},
        "selected_plan_id": "plan1",
        "scope_output": {"in_scope": [{"title": "Issue board", "desc": "Main board", "priority": "P1"}], "out_scope": []},
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
    }

    updates = context_loader_node(state)

    # Check that market_evidence_context is populated (injected separately by writer nodes)
    evidence = updates.get("market_evidence_context", "")
    assert len(evidence) > 0, "Expected non-empty market evidence for PRD"

    # Slim context should NOT include market_evidence (writer nodes inject it independently
    # to avoid double injection in the prompt)
    slim_ctx = updates.get("prd_slim_context", {})
    assert "market_evidence" not in slim_ctx
    assert slim_ctx is not None
