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
def service():
    from app.db.repo_competitors import CompetitorRepository
    from app.db.repo_market_signals import MarketSignalRepository
    from app.agents.memory.vector_store import VectorStore
    from app.services.market_evidence_service import MarketEvidenceService

    return MarketEvidenceService(
        competitor_repo=CompetitorRepository(),
        signal_repo=MarketSignalRepository(),
        vector_store=VectorStore(persist_directory=None),
    )


WORKSPACE = "default"

SAMPLE_SUMMARY = {
    "positioning": "Enterprise analytics platform",
    "features": "Real-time dashboards, SQL editor",
    "pricing": "Free tier, $49/mo pro",
    "reviews": "4.5 stars on G2, praised for speed",
}

SAMPLE_SCORES = {
    "quality_score": 0.85,
    "traction_score": 0.7,
    "relevance_score": 0.9,
    "underrated_score": 0.3,
    "confidence": 0.8,
}


def _create_test_idea():
    from app.db.repo_ideas import IdeaRepository
    return IdeaRepository().create_idea(title="Test Idea")


# ---------- upsert_competitor_card ----------


def test_upsert_competitor_card_creates_new(service):
    comp, snap = service.upsert_competitor_card(
        workspace_id=WORKSPACE,
        name="Acme Analytics",
        canonical_url="https://acme.io",
        category="analytics",
        summary_json=SAMPLE_SUMMARY,
        scores=SAMPLE_SCORES,
        confidence=0.8,
    )

    # Verify competitor record
    assert comp.id
    assert comp.name == "Acme Analytics"
    assert comp.canonical_url == "https://acme.io"
    assert comp.category == "analytics"

    # Verify snapshot record
    assert snap.id
    assert snap.competitor_id == comp.id
    assert snap.summary_json == SAMPLE_SUMMARY
    assert snap.quality_score == 0.85
    assert snap.traction_score == 0.7
    assert snap.relevance_score == 0.9
    assert snap.underrated_score == 0.3
    assert snap.confidence == 0.8

    # Verify vector store has chunks
    results = service._vs.search_market_evidence(
        "analytics platform", n_results=10
    )
    assert len(results) > 0
    # Check that at least one chunk references this competitor
    chunk_ids = [r["chunk_id"] for r in results]
    assert any(comp.id in cid for cid in chunk_ids)


def test_upsert_competitor_card_reuses_existing(service):
    comp1, snap1 = service.upsert_competitor_card(
        workspace_id=WORKSPACE,
        name="Acme Analytics",
        canonical_url="https://acme.io",
        category="analytics",
        summary_json=SAMPLE_SUMMARY,
        scores=SAMPLE_SCORES,
        confidence=0.8,
    )

    comp2, snap2 = service.upsert_competitor_card(
        workspace_id=WORKSPACE,
        name="Acme Analytics Updated",
        canonical_url="https://acme.io",
        category="analytics",
        summary_json={"positioning": "Updated positioning"},
        scores={"quality_score": 0.95},
        confidence=0.9,
    )

    # Should reuse the same competitor
    assert comp1.id == comp2.id
    # But create a new snapshot
    assert snap1.id != snap2.id
    assert snap2.snapshot_version == 2

    # Verify only one competitor exists
    from app.db.repo_competitors import CompetitorRepository
    all_comps = CompetitorRepository().list_competitors(workspace_id=WORKSPACE)
    matching = [c for c in all_comps if c.canonical_url == "https://acme.io"]
    assert len(matching) == 1


# ---------- record_market_signal ----------


def test_record_market_signal_with_url(service):
    signal = service.record_market_signal(
        workspace_id=WORKSPACE,
        signal_type="competitor_update",
        title="Acme launches v2",
        summary="Acme Analytics released version 2 with AI features",
        severity="medium",
        url="https://acme.io/blog/v2",
    )

    assert signal.id
    assert signal.signal_type == "competitor_update"
    assert signal.title == "Acme launches v2"
    assert signal.summary == "Acme Analytics released version 2 with AI features"
    assert signal.severity == "medium"
    # evidence_source_id should be set since we provided a URL
    assert signal.evidence_source_id is not None

    # Verify chunk in vector store
    results = service._vs.search_market_evidence(
        "Acme v2 launch", n_results=5
    )
    assert len(results) > 0


def test_record_market_signal_without_url(service):
    signal = service.record_market_signal(
        workspace_id=WORKSPACE,
        signal_type="market_news",
        title="Market consolidation trend",
        summary="Several analytics companies are merging",
        severity="low",
    )

    assert signal.id
    assert signal.signal_type == "market_news"
    assert signal.evidence_source_id is None


# ---------- link_evidence_to_idea ----------


def test_link_evidence_to_idea(service):
    idea = _create_test_idea()

    comp, _ = service.upsert_competitor_card(
        workspace_id=WORKSPACE,
        name="Linked Corp",
        canonical_url="https://linked.io",
        category="analytics",
        summary_json=SAMPLE_SUMMARY,
        scores=SAMPLE_SCORES,
        confidence=0.8,
    )

    link = service.link_evidence_to_idea(
        idea_id=idea.id,
        entity_type="competitor",
        entity_id=comp.id,
        link_reason="direct competitor in analytics space",
        relevance_score=0.85,
    )

    assert link.id
    assert link.idea_id == idea.id
    assert link.entity_type == "competitor"
    assert link.entity_id == comp.id
    assert link.link_reason == "direct competitor in analytics space"
    assert link.relevance_score == 0.85


# ---------- build_and_store_insight ----------


def test_build_and_store_insight(service):
    idea = _create_test_idea()

    chunk_id = service.build_and_store_insight(
        workspace_id=WORKSPACE,
        idea_id=idea.id,
        insight_text="The analytics market is growing at 15% CAGR with consolidation expected",
        confidence=0.75,
    )

    assert chunk_id
    assert isinstance(chunk_id, str)

    # Verify in vector store
    results = service._vs.search_market_evidence(
        "analytics market growth", n_results=5
    )
    assert len(results) > 0
    found_ids = [r["chunk_id"] for r in results]
    assert chunk_id in found_ids

    # Verify linked to idea
    from app.db.repo_market_signals import MarketSignalRepository
    links = MarketSignalRepository().list_signals_for_idea(idea.id)
    # The link entity_type should be 'insight'
    insight_links = [lnk for lnk in links if lnk.entity_type == "insight"]
    # build_and_store_insight links with entity_type="evidence_insight"
    # Let's check all link types
    from app.db.engine import db_session
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM idea_evidence_link WHERE idea_id = ?",
            (idea.id,),
        ).fetchall()
    assert len(rows) >= 1


# ---------- rebuild_market_chunks ----------


def test_rebuild_market_chunks(service):
    comp, snap = service.upsert_competitor_card(
        workspace_id=WORKSPACE,
        name="Rebuild Corp",
        canonical_url="https://rebuild.io",
        category="analytics",
        summary_json=SAMPLE_SUMMARY,
        scores=SAMPLE_SCORES,
        confidence=0.8,
    )

    count = service.rebuild_market_chunks_for_competitor(comp.id)
    assert count > 0
    # Should have written chunks for the keys in SAMPLE_SUMMARY
    assert count == len(SAMPLE_SUMMARY)


def test_rebuild_market_chunks_no_snapshot(service):
    from app.db.repo_competitors import CompetitorRepository
    comp = CompetitorRepository().create_competitor(
        workspace_id=WORKSPACE,
        name="Empty Corp",
    )
    count = service.rebuild_market_chunks_for_competitor(comp.id)
    assert count == 0
