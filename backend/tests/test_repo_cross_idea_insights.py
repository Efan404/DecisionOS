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


def _create_idea(title: str) -> str:
    """Helper: create an idea and return its id."""
    from app.db.repo_ideas import IdeaRepository
    repo = IdeaRepository()
    rec = repo.create_idea(title=title)
    return rec.id


def test_create_insight():
    from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository

    idea_a = _create_idea("Idea Alpha")
    idea_b = _create_idea("Idea Beta")
    repo = CrossIdeaInsightRepository()

    rec = repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=idea_a,
        idea_b_id=idea_b,
        insight_type="shared_audience",
        summary="Both target indie hackers",
        why_it_matters="Shared audience means cross-sell opportunity",
        recommended_action="review",
        confidence=0.85,
        similarity_score=0.72,
        evidence_json={"sources": ["hn", "reddit"]},
        fingerprint="fp-shared-audience-001",
    )

    assert rec.id
    assert rec.workspace_id == "default"
    assert rec.insight_type == "shared_audience"
    assert rec.summary == "Both target indie hackers"
    assert rec.why_it_matters == "Shared audience means cross-sell opportunity"
    assert rec.recommended_action == "review"
    assert rec.confidence == 0.85
    assert rec.similarity_score == 0.72
    assert rec.evidence_json == {"sources": ["hn", "reddit"]}
    assert rec.fingerprint == "fp-shared-audience-001"
    assert rec.created_at
    assert rec.updated_at


def test_canonical_pair_ordering():
    from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository

    idea_x = _create_idea("Idea X")
    idea_y = _create_idea("Idea Y")
    # Determine which id is "smaller" lexicographically
    smaller, larger = sorted([idea_x, idea_y])
    # Pass them in reverse order (larger first)
    repo = CrossIdeaInsightRepository()
    rec = repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=larger,
        idea_b_id=smaller,
        insight_type="merge_candidate",
        summary="Could be merged",
        why_it_matters="Saves effort",
        recommended_action="merge_ideas",
        confidence=0.9,
        similarity_score=0.95,
        evidence_json=None,
        fingerprint="fp-merge-001",
    )

    assert rec.idea_a_id == smaller
    assert rec.idea_b_id == larger


def test_dedup_by_fingerprint():
    from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository
    from app.db.engine import db_session

    idea_a = _create_idea("Idea A")
    idea_b = _create_idea("Idea B")
    repo = CrossIdeaInsightRepository()

    rec1 = repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=idea_a,
        idea_b_id=idea_b,
        insight_type="shared_capability",
        summary="Original summary",
        why_it_matters="Original reason",
        recommended_action="review",
        confidence=0.5,
        similarity_score=0.6,
        evidence_json=None,
        fingerprint="fp-dedup-001",
    )

    rec2 = repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=idea_a,
        idea_b_id=idea_b,
        insight_type="shared_capability",
        summary="Updated summary",
        why_it_matters="Updated reason",
        recommended_action="compare_feasibility",
        confidence=0.8,
        similarity_score=0.9,
        evidence_json={"new": True},
        fingerprint="fp-dedup-001",
    )

    # Same row was updated (same id)
    assert rec2.id == rec1.id
    assert rec2.summary == "Updated summary"
    assert rec2.confidence == 0.8

    # Only one row in the table for this pair+fingerprint
    smaller, larger = sorted([idea_a, idea_b])
    with db_session() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM cross_idea_insight "
            "WHERE idea_a_id = ? AND idea_b_id = ? AND fingerprint = ?",
            (smaller, larger, "fp-dedup-001"),
        ).fetchone()["cnt"]
    assert count == 1


def test_different_fingerprint_creates_new():
    from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository

    idea_a = _create_idea("Idea D1")
    idea_b = _create_idea("Idea D2")
    repo = CrossIdeaInsightRepository()

    rec1 = repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=idea_a,
        idea_b_id=idea_b,
        insight_type="execution_reuse",
        summary="Reuse scope items",
        why_it_matters="Saves time",
        recommended_action="reuse_scope",
        confidence=0.7,
        similarity_score=0.8,
        evidence_json=None,
        fingerprint="fp-exec-001",
    )

    rec2 = repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=idea_a,
        idea_b_id=idea_b,
        insight_type="positioning_conflict",
        summary="Conflicting positioning",
        why_it_matters="Brand confusion",
        recommended_action="keep_separate",
        confidence=0.6,
        similarity_score=0.5,
        evidence_json=None,
        fingerprint="fp-pos-002",
    )

    assert rec1.id != rec2.id


def test_list_for_idea():
    from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository

    idea_x = _create_idea("Idea LX")
    idea_y = _create_idea("Idea LY")
    idea_z = _create_idea("Idea LZ")
    repo = CrossIdeaInsightRepository()

    repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=idea_x,
        idea_b_id=idea_y,
        insight_type="shared_audience",
        summary="X-Y overlap",
        why_it_matters="Matter XY",
        recommended_action="review",
        confidence=0.7,
        similarity_score=0.6,
        evidence_json=None,
        fingerprint="fp-xy",
    )

    repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=idea_x,
        idea_b_id=idea_z,
        insight_type="evidence_overlap",
        summary="X-Z overlap",
        why_it_matters="Matter XZ",
        recommended_action="review",
        confidence=0.8,
        similarity_score=0.7,
        evidence_json=None,
        fingerprint="fp-xz",
    )

    results = repo.list_for_idea(idea_x)
    assert len(results) == 2
    summaries = {r.summary for r in results}
    assert "X-Y overlap" in summaries
    assert "X-Z overlap" in summaries

    # idea_y should only see its one insight
    results_y = repo.list_for_idea(idea_y)
    assert len(results_y) == 1
    assert results_y[0].summary == "X-Y overlap"


def test_list_recent_for_workspace():
    from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository
    import time

    repo = CrossIdeaInsightRepository()
    # Create 3 insights
    ideas = [_create_idea(f"Idea W{i}") for i in range(4)]

    repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=ideas[0],
        idea_b_id=ideas[1],
        insight_type="shared_audience",
        summary="First",
        why_it_matters="M1",
        recommended_action="review",
        confidence=0.5,
        similarity_score=0.5,
        evidence_json=None,
        fingerprint="fp-w1",
    )

    repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=ideas[2],
        idea_b_id=ideas[3],
        insight_type="merge_candidate",
        summary="Second",
        why_it_matters="M2",
        recommended_action="merge_ideas",
        confidence=0.6,
        similarity_score=0.6,
        evidence_json=None,
        fingerprint="fp-w2",
    )

    repo.create_or_update_insight(
        workspace_id="default",
        idea_a_id=ideas[0],
        idea_b_id=ideas[2],
        insight_type="evidence_overlap",
        summary="Third",
        why_it_matters="M3",
        recommended_action="review",
        confidence=0.7,
        similarity_score=0.7,
        evidence_json=None,
        fingerprint="fp-w3",
    )

    # All 3 returned when limit is high
    all_results = repo.list_recent_for_workspace("default", limit=20)
    assert len(all_results) == 3

    # Most recent first (Third should be first since created last)
    assert all_results[0].summary == "Third"

    # Limit works
    limited = repo.list_recent_for_workspace("default", limit=2)
    assert len(limited) == 2

    # Different workspace returns nothing
    empty = repo.list_recent_for_workspace("other-workspace", limit=20)
    assert len(empty) == 0
