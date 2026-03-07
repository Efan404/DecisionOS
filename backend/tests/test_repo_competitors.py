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


def test_create_competitor_defaults():
    from app.db.repo_competitors import CompetitorRepository
    repo = CompetitorRepository()
    rec = repo.create_competitor(workspace_id="default", name="Acme Corp")
    assert rec.id
    assert rec.workspace_id == "default"
    assert rec.name == "Acme Corp"
    assert rec.canonical_url is None
    assert rec.category is None
    assert rec.status == "candidate"
    assert rec.created_at
    assert rec.updated_at


def test_create_competitor_with_optional_fields():
    from app.db.repo_competitors import CompetitorRepository
    repo = CompetitorRepository()
    rec = repo.create_competitor(
        workspace_id="default",
        name="Beta Inc",
        canonical_url="https://beta.inc",
        category="analytics",
        status="tracked",
    )
    assert rec.name == "Beta Inc"
    assert rec.canonical_url == "https://beta.inc"
    assert rec.category == "analytics"
    assert rec.status == "tracked"


def test_get_competitor_found_and_not_found():
    from app.db.repo_competitors import CompetitorRepository
    repo = CompetitorRepository()
    created = repo.create_competitor(workspace_id="default", name="Findable")
    found = repo.get_competitor(created.id)
    assert found is not None
    assert found.id == created.id
    assert found.name == "Findable"

    missing = repo.get_competitor("nonexistent-id")
    assert missing is None


def test_list_competitors_all():
    from app.db.repo_competitors import CompetitorRepository
    repo = CompetitorRepository()
    repo.create_competitor(workspace_id="default", name="A")
    repo.create_competitor(workspace_id="default", name="B")
    results = repo.list_competitors(workspace_id="default")
    assert len(results) >= 2
    names = {r.name for r in results}
    assert "A" in names
    assert "B" in names


def test_list_competitors_filter_by_status():
    from app.db.repo_competitors import CompetitorRepository
    repo = CompetitorRepository()
    repo.create_competitor(workspace_id="default", name="Tracked1", status="tracked")
    repo.create_competitor(workspace_id="default", name="Candidate1", status="candidate")
    tracked = repo.list_competitors(workspace_id="default", status="tracked")
    assert all(r.status == "tracked" for r in tracked)
    assert any(r.name == "Tracked1" for r in tracked)


def test_create_snapshot_and_version_increment():
    from app.db.repo_competitors import CompetitorRepository
    repo = CompetitorRepository()
    comp = repo.create_competitor(workspace_id="default", name="Snap Corp")

    snap1 = repo.create_snapshot(
        competitor_id=comp.id,
        summary_json={"overview": "first"},
        quality_score=0.8,
    )
    assert snap1.snapshot_version == 1
    assert snap1.summary_json == {"overview": "first"}
    assert snap1.quality_score == 0.8
    assert snap1.traction_score is None

    snap2 = repo.create_snapshot(
        competitor_id=comp.id,
        summary_json={"overview": "second"},
        traction_score=0.9,
    )
    assert snap2.snapshot_version == 2


def test_get_latest_snapshot():
    from app.db.repo_competitors import CompetitorRepository
    repo = CompetitorRepository()
    comp = repo.create_competitor(workspace_id="default", name="Latest Corp")

    assert repo.get_latest_snapshot(comp.id) is None

    repo.create_snapshot(competitor_id=comp.id, summary_json={"v": 1})
    repo.create_snapshot(competitor_id=comp.id, summary_json={"v": 2})

    latest = repo.get_latest_snapshot(comp.id)
    assert latest is not None
    assert latest.snapshot_version == 2
    assert latest.summary_json == {"v": 2}


def test_create_evidence_source():
    from app.db.repo_competitors import CompetitorRepository
    repo = CompetitorRepository()
    rec = repo.create_evidence_source(
        source_type="website",
        url="https://example.com",
        title="Example",
        snippet="A snippet",
        confidence=0.95,
    )
    assert rec.id
    assert rec.source_type == "website"
    assert rec.url == "https://example.com"
    assert rec.title == "Example"
    assert rec.snippet == "A snippet"
    assert rec.published_at is None
    assert rec.fetched_at
    assert rec.confidence == 0.95
    assert rec.payload_json is None


def test_create_evidence_source_with_payload():
    from app.db.repo_competitors import CompetitorRepository
    repo = CompetitorRepository()
    rec = repo.create_evidence_source(
        source_type="pricing",
        url="https://example.com/pricing",
        payload_json={"plans": [{"name": "free"}]},
    )
    assert rec.payload_json == {"plans": [{"name": "free"}]}
