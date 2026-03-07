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


def _make_idea(title: str = "Test Idea"):
    from app.db.repo_ideas import IdeaRepository
    repo = IdeaRepository()
    return repo.create_idea(title=title, idea_seed="seed")


def test_create_market_insight():
    from app.db.repo_market_insights import MarketInsightRepository
    idea = _make_idea()
    repo = MarketInsightRepository()
    record = repo.create(
        idea_id=idea.id,
        summary="Market is growing rapidly",
        decision_impact="Consider pivoting to enterprise segment",
        recommended_actions=["Action 1", "Action 2"],
        signal_count=3,
    )
    assert record.id is not None
    assert record.idea_id == idea.id
    assert record.summary == "Market is growing rapidly"
    assert record.signal_count == 3
    assert len(record.recommended_actions) == 2


def test_list_for_idea_returns_ordered_by_date():
    from app.db.repo_market_insights import MarketInsightRepository
    idea = _make_idea("Idea X")
    repo = MarketInsightRepository()
    # Create two insights for same idea
    r1 = repo.create(idea_id=idea.id, summary="First", decision_impact="d1", recommended_actions=[], signal_count=1)
    r2 = repo.create(idea_id=idea.id, summary="Second", decision_impact="d2", recommended_actions=["a"], signal_count=2)
    results = repo.list_for_idea(idea.id)
    # Most recent first
    assert results[0].id == r2.id
    assert results[1].id == r1.id


def test_list_all_returns_across_ideas():
    from app.db.repo_market_insights import MarketInsightRepository
    idea_a = _make_idea("Idea A")
    idea_b = _make_idea("Idea B")
    repo = MarketInsightRepository()
    repo.create(idea_id=idea_a.id, summary="A", decision_impact="da", recommended_actions=[], signal_count=0)
    repo.create(idea_id=idea_b.id, summary="B", decision_impact="db", recommended_actions=[], signal_count=0)
    results = repo.list_all(limit=10)
    idea_ids = {r.idea_id for r in results}
    assert idea_a.id in idea_ids
    assert idea_b.id in idea_ids


def test_list_for_idea_returns_empty_for_unknown_idea():
    from app.db.repo_market_insights import MarketInsightRepository
    repo = MarketInsightRepository()
    results = repo.list_for_idea("nonexistent-idea-id")
    assert results == []
