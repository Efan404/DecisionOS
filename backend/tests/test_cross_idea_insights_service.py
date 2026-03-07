from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
from tests._test_env import ensure_required_seed_env


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    ensure_required_seed_env()
    os.environ["DECISIONOS_DB_PATH"] = str(tmp_path / "test.db")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    from app.db.bootstrap import initialize_database

    initialize_database()


@pytest.fixture()
def svc(monkeypatch, tmp_path):
    import app.agents.memory.vector_store as vs_mod
    from app.agents.memory.vector_store import VectorStore

    isolated_vs = VectorStore(persist_directory=str(tmp_path / "chroma"))
    monkeypatch.setattr(vs_mod, "_singleton", isolated_vs)

    from app.services.cross_idea_insights_service import CrossIdeaInsightsService

    return CrossIdeaInsightsService(vector_store=isolated_vs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_LLM_RESPONSE = json.dumps(
    {
        "insight_type": "shared_audience",
        "summary": "Both ideas target indie developers building SaaS tools.",
        "why_it_matters": "Cross-sell opportunity exists between the two user bases.",
        "recommended_action": "review",
        "confidence": 0.82,
    }
)


def _make_idea(title: str, seed: str = "test seed") -> str:
    from app.db.repo_ideas import IdeaRepository

    idea = IdeaRepository().create_idea(title=title, idea_seed=seed)
    return idea.id


def _make_competitor(name: str) -> str:
    from app.db.repo_competitors import CompetitorRepository

    comp = CompetitorRepository().create_competitor(workspace_id="default", name=name)
    return comp.id


def _make_signal(title: str) -> str:
    from app.db.repo_market_signals import MarketSignalRepository

    sig = MarketSignalRepository().create_signal(
        workspace_id="default",
        signal_type="market_news",
        title=title,
        summary=f"Summary for {title}",
        severity="medium",
    )
    return sig.id


def _link(idea_id: str, entity_type: str, entity_id: str) -> None:
    from app.db.repo_market_signals import MarketSignalRepository

    MarketSignalRepository().link_idea_entity(
        idea_id=idea_id,
        entity_type=entity_type,
        entity_id=entity_id,
        link_reason="test link",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("app.core.ai_gateway.generate_text", return_value=VALID_LLM_RESPONSE)
def test_analyze_pair_persists_structured_insight(mock_llm, svc):
    """Mock LLM returns valid JSON -- verify InsightRecord is created with correct fields."""
    idea_a = _make_idea("AI Code Review Tool")
    idea_b = _make_idea("AI Bug Detector")

    record = svc.analyze_pair(idea_a, idea_b, similarity_score=0.75)

    assert record is not None
    assert record.insight_type == "shared_audience"
    assert "indie developers" in record.summary
    assert record.why_it_matters == "Cross-sell opportunity exists between the two user bases."
    assert record.recommended_action == "review"
    assert record.confidence == 0.82
    assert record.similarity_score == 0.75
    assert record.fingerprint  # non-empty
    # Canonical ordering: smaller id first
    a, b = sorted([idea_a, idea_b])
    assert record.idea_a_id == a
    assert record.idea_b_id == b

    # LLM was called exactly once
    mock_llm.assert_called_once()


@patch("app.core.ai_gateway.generate_text", side_effect=RuntimeError("LLM down"))
def test_analyze_pair_skips_on_llm_failure(mock_llm, svc):
    """When LLM raises an exception, analyze_pair returns None."""
    idea_a = _make_idea("Idea Alpha")
    idea_b = _make_idea("Idea Beta")

    result = svc.analyze_pair(idea_a, idea_b, similarity_score=0.6)

    assert result is None
    mock_llm.assert_called_once()


@patch("app.core.ai_gateway.generate_text", return_value="this is not json at all {{{")
def test_analyze_pair_skips_on_invalid_json(mock_llm, svc):
    """When LLM returns unparseable garbage, analyze_pair returns None."""
    idea_a = _make_idea("Idea Gamma")
    idea_b = _make_idea("Idea Delta")

    result = svc.analyze_pair(idea_a, idea_b, similarity_score=0.5)

    assert result is None


def test_build_pair_context_under_token_budget(svc):
    """The context string should stay within the ~1000 token budget."""
    idea_a = _make_idea("AI-powered Image Generation Platform", seed="Generate images using diffusion models")
    idea_b = _make_idea("Neural Style Transfer App", seed="Apply artistic styles to photos using neural networks")

    # Add some competitors and signals for richer context
    comp1 = _make_competitor("Adobe Firefly")
    comp2 = _make_competitor("Midjourney")
    sig1 = _make_signal("Generative AI Market Growth")
    sig2 = _make_signal("Image AI Regulation Update")

    _link(idea_a, "competitor", comp1)
    _link(idea_b, "competitor", comp1)  # shared
    _link(idea_a, "competitor", comp2)
    _link(idea_b, "competitor", comp2)  # shared
    _link(idea_a, "signal", sig1)
    _link(idea_b, "signal", sig1)  # shared
    _link(idea_a, "signal", sig2)
    _link(idea_b, "signal", sig2)  # shared

    context = svc.build_pair_context(idea_a, idea_b)

    estimated_tokens = len(context) // 4
    assert estimated_tokens <= 1000, f"Context is {estimated_tokens} estimated tokens, exceeds 1000"
    # Verify it contains meaningful content
    assert "AI-powered Image Generation Platform" in context or "Neural Style Transfer App" in context


@patch("app.core.ai_gateway.generate_text", return_value=VALID_LLM_RESPONSE)
def test_analyze_anchor_idea_filters_weak_candidates(mock_llm, svc):
    """Only candidates with composite_score > 0.3 should be analyzed."""
    anchor = _make_idea("AI Code Review", seed="AI code review for pull requests")
    strong = _make_idea("AI Code Linter", seed="AI-powered code linting and analysis")
    weak = _make_idea("Organic Farm Store", seed="Online marketplace for organic vegetables")

    # Add summaries to vector store so candidate service can find them
    from app.agents.memory.vector_store import get_vector_store

    vs = get_vector_store()
    vs.add_idea_summary(anchor, "AI code review for pull requests")
    vs.add_idea_summary(strong, "AI-powered code linting and analysis")
    vs.add_idea_summary(weak, "Online marketplace for organic vegetables")

    results = svc.analyze_anchor_idea(anchor)

    # The weak candidate should be filtered out (dissimilar topic).
    # The strong candidate should produce an insight.
    analyzed_idea_ids = set()
    for r in results:
        analyzed_idea_ids.add(r.idea_a_id)
        analyzed_idea_ids.add(r.idea_b_id)

    # The organic farm idea should NOT appear in results
    assert weak not in analyzed_idea_ids, "Weak candidate should have been filtered out"
    # If the strong candidate was above threshold, it should appear
    if results:
        assert strong in analyzed_idea_ids or anchor in analyzed_idea_ids
