from __future__ import annotations

import os

import pytest
from tests._test_env import ensure_required_seed_env


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    ensure_required_seed_env()
    os.environ["DECISIONOS_DB_PATH"] = str(tmp_path / "test.db")
    os.environ["DECISIONOS_AUTH_DISABLED"] = "1"
    from app.core.settings import get_settings

    get_settings.cache_clear()
    from app.db.bootstrap import initialize_database

    initialize_database()


@pytest.fixture()
def client():
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    return TestClient(app)


def _make_idea(title: str, seed: str = "test seed") -> str:
    from app.db.repo_ideas import IdeaRepository

    idea = IdeaRepository().create_idea(title=title, idea_seed=seed)
    return idea.id


def _make_insight(
    idea_a_id: str,
    idea_b_id: str,
    insight_type: str = "execution_reuse",
    fingerprint: str = "test-fingerprint",
):
    from app.db.repo_cross_idea_insights import CrossIdeaInsightRepository

    return CrossIdeaInsightRepository().create_or_update_insight(
        workspace_id="default",
        idea_a_id=idea_a_id,
        idea_b_id=idea_b_id,
        insight_type=insight_type,
        summary="Test summary",
        why_it_matters="Test reason",
        recommended_action="review",
        confidence=0.8,
        similarity_score=0.7,
        evidence_json=None,
        fingerprint=fingerprint,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_cross_insights_empty(client):
    """GET returns empty data array for idea with no insights."""
    idea_id = _make_idea("Lonely idea")
    resp = client.get(f"/ideas/{idea_id}/cross-insights")
    assert resp.status_code == 200
    body = resp.json()
    assert body["idea_id"] == idea_id
    assert body["data"] == []


def test_list_cross_insights_returns_persisted(client):
    """Create insight via repo, GET returns it with correct fields."""
    idea_a = _make_idea("Alpha")
    idea_b = _make_idea("Beta")
    insight = _make_insight(idea_a, idea_b)

    resp = client.get(f"/ideas/{idea_a}/cross-insights")
    assert resp.status_code == 200
    body = resp.json()
    assert body["idea_id"] == idea_a
    assert len(body["data"]) == 1

    item = body["data"][0]
    assert item["id"] == insight.id
    assert item["insight_type"] == "execution_reuse"
    assert item["summary"] == "Test summary"
    assert item["why_it_matters"] == "Test reason"
    assert item["recommended_action"] == "review"
    assert item["confidence"] == 0.8
    assert item["similarity_score"] == 0.7
    assert item["fingerprint"] == "test-fingerprint"


def test_list_cross_insights_includes_titles(client):
    """Insight response includes idea_a_title and idea_b_title from DB."""
    idea_a = _make_idea("Project Alpha")
    idea_b = _make_idea("Project Beta")
    _make_insight(idea_a, idea_b)

    resp = client.get(f"/ideas/{idea_a}/cross-insights")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1

    item = body["data"][0]
    # Repo canonicalizes pair order (sorted UUIDs), so check both titles are present
    titles = {item["idea_a_title"], item["idea_b_title"]}
    assert titles == {"Project Alpha", "Project Beta"}


def test_sync_endpoint_returns_response(client):
    """POST sync endpoint returns valid response structure with status field."""
    idea_id = _make_idea("Sync target")
    resp = client.post(f"/ideas/{idea_id}/cross-insights/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["idea_id"] == idea_id
    assert "status" in body
    assert "data" in body
    assert isinstance(body["data"], list)
