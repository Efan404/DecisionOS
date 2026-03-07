from __future__ import annotations

import os

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
def service(monkeypatch, tmp_path):
    import app.agents.memory.vector_store as vs_mod
    from app.agents.memory.vector_store import VectorStore
    from app.db.repo_market_signals import MarketSignalRepository
    from app.services.cross_idea_candidate_service import CrossIdeaCandidateService

    # Use a unique persist directory per test to guarantee isolation
    chroma_dir = str(tmp_path / "chroma_isolated")
    isolated_vs = VectorStore(persist_directory=chroma_dir)
    monkeypatch.setattr(vs_mod, "_singleton", isolated_vs)

    return CrossIdeaCandidateService(
        vector_store=isolated_vs,
        signal_repo=MarketSignalRepository(),
    ), isolated_vs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_idea(title: str, seed: str = "seed") -> str:
    from app.db.repo_ideas import IdeaRepository

    idea = IdeaRepository().create_idea(title=title, idea_seed=seed)
    return idea.id


def _make_competitor(name: str) -> str:
    from app.db.repo_competitors import CompetitorRepository

    comp = CompetitorRepository().create_competitor(
        workspace_id="default", name=name
    )
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


def test_finds_related_ideas_by_similarity(service):
    svc, vs = service

    # Create 3 ideas with summaries in the vector store
    id_a = _make_idea("AI Image Generator")
    id_b = _make_idea("AI Photo Editor")
    id_c = _make_idea("Organic Farm Marketplace")

    vs.add_idea_summary(id_a, "An AI-powered image generation tool using diffusion models")
    vs.add_idea_summary(id_b, "An AI-powered photo editing application with neural style transfer")
    vs.add_idea_summary(id_c, "An online marketplace for organic farm produce and vegetables")

    # Find ideas related to idea A (AI image generation)
    candidates = svc.find_related_ideas(
        anchor_idea_id=id_a,
        anchor_summary="An AI-powered image generation tool using diffusion models",
        limit=5,
    )

    assert len(candidates) >= 1
    # The AI photo editor should be the most similar to AI image generator
    assert candidates[0].idea_id == id_b
    # All candidates should have non-zero similarity
    for c in candidates:
        assert c.similarity_score > 0
        assert c.composite_score > 0
    # Anchor should NOT appear in results
    candidate_ids = [c.idea_id for c in candidates]
    assert id_a not in candidate_ids


def test_boosts_candidates_with_shared_competitors(service):
    svc, vs = service

    id_a = _make_idea("AI Image Generator")
    id_b = _make_idea("AI Photo Editor")
    id_c = _make_idea("AI Art Creator")

    vs.add_idea_summary(id_a, "An AI-powered image generation tool")
    vs.add_idea_summary(id_b, "An AI-powered photo editing application")
    vs.add_idea_summary(id_c, "An AI-powered art creation platform")

    # Create a shared competitor between idea A and idea B
    comp_id = _make_competitor("Adobe Firefly")
    _link(id_a, "competitor", comp_id)
    _link(id_b, "competitor", comp_id)
    # idea C has no shared competitors with A

    candidates = svc.find_related_ideas(
        anchor_idea_id=id_a,
        anchor_summary="An AI-powered image generation tool",
        limit=5,
    )

    assert len(candidates) >= 2
    # Find candidate B and C
    b_candidate = next(c for c in candidates if c.idea_id == id_b)
    c_candidate = next(c for c in candidates if c.idea_id == id_c)

    # B should have shared_competitor_count = 1
    assert b_candidate.shared_competitor_count == 1
    assert c_candidate.shared_competitor_count == 0

    # B's composite score should be higher than its raw similarity due to boost
    assert b_candidate.composite_score > b_candidate.similarity_score


def test_boosts_candidates_with_shared_signals(service):
    svc, vs = service

    id_a = _make_idea("AI Image Generator")
    id_b = _make_idea("AI Photo Editor")
    id_c = _make_idea("AI Art Creator")

    vs.add_idea_summary(id_a, "An AI-powered image generation tool")
    vs.add_idea_summary(id_b, "An AI-powered photo editing application")
    vs.add_idea_summary(id_c, "An AI-powered art creation platform")

    # Create shared signals between idea A and idea B
    sig_id_1 = _make_signal("Generative AI Market Growth")
    sig_id_2 = _make_signal("Image AI Regulation")
    _link(id_a, "signal", sig_id_1)
    _link(id_b, "signal", sig_id_1)
    _link(id_a, "signal", sig_id_2)
    _link(id_b, "signal", sig_id_2)
    # idea C has no shared signals with A

    candidates = svc.find_related_ideas(
        anchor_idea_id=id_a,
        anchor_summary="An AI-powered image generation tool",
        limit=5,
    )

    assert len(candidates) >= 2
    b_candidate = next(c for c in candidates if c.idea_id == id_b)
    c_candidate = next(c for c in candidates if c.idea_id == id_c)

    # B shares 2 signals with A
    assert b_candidate.shared_signal_count == 2
    assert c_candidate.shared_signal_count == 0

    # B's composite score should exceed similarity due to signal boosts
    assert b_candidate.composite_score > b_candidate.similarity_score


def test_limits_candidate_count(service):
    svc, vs = service

    anchor_id = _make_idea("Anchor Idea")
    vs.add_idea_summary(anchor_id, "A central anchor idea for testing")

    # Create 6 candidate ideas
    for i in range(6):
        cid = _make_idea(f"Candidate {i}")
        vs.add_idea_summary(cid, f"A candidate idea number {i} for testing limits")

    candidates = svc.find_related_ideas(
        anchor_idea_id=anchor_id,
        anchor_summary="A central anchor idea for testing",
        limit=3,
    )

    assert len(candidates) <= 3


def test_returns_empty_for_single_idea(service):
    svc, vs = service

    only_id = _make_idea("Only Idea")
    vs.add_idea_summary(only_id, "The only idea in the store")

    candidates = svc.find_related_ideas(
        anchor_idea_id=only_id,
        anchor_summary="The only idea in the store",
        limit=5,
    )

    assert candidates == []
