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


def _make_idea():
    from app.db.repo_ideas import IdeaRepository
    repo = IdeaRepository()
    return repo.create_idea(title="Test Idea", idea_seed="seed")


def test_create_signal_defaults():
    from app.db.repo_market_signals import MarketSignalRepository
    repo = MarketSignalRepository()
    rec = repo.create_signal(
        workspace_id="default",
        signal_type="market_news",
        title="Big News",
        summary="Something happened",
        severity="medium",
    )
    assert rec.id
    assert rec.workspace_id == "default"
    assert rec.signal_type == "market_news"
    assert rec.title == "Big News"
    assert rec.summary == "Something happened"
    assert rec.severity == "medium"
    assert rec.detected_at
    assert rec.evidence_source_id is None
    assert rec.payload_json is None


def test_create_signal_with_evidence_source():
    from app.db.repo_competitors import CompetitorRepository
    from app.db.repo_market_signals import MarketSignalRepository
    comp_repo = CompetitorRepository()
    sig_repo = MarketSignalRepository()

    src = comp_repo.create_evidence_source(
        source_type="news",
        url="https://news.example.com/article",
        title="Breaking News",
    )
    rec = sig_repo.create_signal(
        workspace_id="default",
        signal_type="competitor_update",
        title="Competitor Raised Prices",
        summary="Prices went up 20%",
        severity="high",
        evidence_source_id=src.id,
        payload_json={"delta": "+20%"},
    )
    assert rec.evidence_source_id == src.id
    assert rec.payload_json == {"delta": "+20%"}


def test_list_signals():
    from app.db.repo_market_signals import MarketSignalRepository
    repo = MarketSignalRepository()
    repo.create_signal(workspace_id="default", signal_type="market_news", title="S1", summary="s1", severity="low")
    repo.create_signal(workspace_id="default", signal_type="community_buzz", title="S2", summary="s2", severity="high")
    results = repo.list_signals(workspace_id="default")
    assert len(results) >= 2
    # Should be ordered by detected_at DESC (most recent first)
    titles = [r.title for r in results]
    assert "S1" in titles
    assert "S2" in titles


def test_list_signals_respects_limit():
    from app.db.repo_market_signals import MarketSignalRepository
    repo = MarketSignalRepository()
    for i in range(5):
        repo.create_signal(
            workspace_id="default",
            signal_type="market_news",
            title=f"Signal {i}",
            summary=f"summary {i}",
            severity="low",
        )
    results = repo.list_signals(workspace_id="default", limit=3)
    assert len(results) == 3


def test_link_idea_entity():
    from app.db.repo_market_signals import MarketSignalRepository
    repo = MarketSignalRepository()
    idea = _make_idea()
    link = repo.link_idea_entity(
        idea_id=idea.id,
        entity_type="competitor",
        entity_id="comp-123",
        link_reason="Direct competitor",
        relevance_score=0.85,
    )
    assert link.id
    assert link.idea_id == idea.id
    assert link.entity_type == "competitor"
    assert link.entity_id == "comp-123"
    assert link.link_reason == "Direct competitor"
    assert link.relevance_score == 0.85
    assert link.created_at


def test_list_linked_competitors_for_idea():
    from app.db.repo_market_signals import MarketSignalRepository
    from app.db.repo_competitors import CompetitorRepository
    sig_repo = MarketSignalRepository()
    comp_repo = CompetitorRepository()
    idea = _make_idea()

    comp = comp_repo.create_competitor(workspace_id="default", name="Linked Corp")
    sig_repo.link_idea_entity(
        idea_id=idea.id,
        entity_type="competitor",
        entity_id=comp.id,
        link_reason="Same market",
    )
    sig_repo.link_idea_entity(
        idea_id=idea.id,
        entity_type="signal",
        entity_id="some-signal-id",
        link_reason="Related news",
    )

    competitor_links = sig_repo.list_linked_competitors_for_idea(idea.id)
    assert len(competitor_links) == 1
    assert competitor_links[0].entity_type == "competitor"
    assert competitor_links[0].entity_id == comp.id


def test_list_signals_for_idea():
    from app.db.repo_market_signals import MarketSignalRepository
    sig_repo = MarketSignalRepository()
    idea = _make_idea()

    sig_repo.link_idea_entity(
        idea_id=idea.id,
        entity_type="signal",
        entity_id="sig-1",
        link_reason="Relevant signal",
    )
    sig_repo.link_idea_entity(
        idea_id=idea.id,
        entity_type="signal",
        entity_id="sig-2",
        link_reason="Another signal",
    )
    sig_repo.link_idea_entity(
        idea_id=idea.id,
        entity_type="competitor",
        entity_id="comp-1",
        link_reason="Competitor link",
    )

    signal_links = sig_repo.list_signals_for_idea(idea.id)
    assert len(signal_links) == 2
    assert all(l.entity_type == "signal" for l in signal_links)
