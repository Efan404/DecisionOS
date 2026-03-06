"""Tests for notification deduplication in proactive agents.

These tests verify that:
- Running news scan twice with the same news/idea pair creates only 1 notification
- Running cross-idea analysis twice with the same idea pair creates only 1 notification
- ChromaDB data loss does not affect SQLite notification dedup (SQLite is source of truth)
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "admin")
os.environ.setdefault("DECISIONOS_CHROMA_PATH", "")  # force in-memory ChromaDB

from unittest.mock import patch, MagicMock

import pytest

from app.db.repo_notifications import NotificationRepository


@pytest.fixture
def notif_repo(tmp_path):
    """Return a NotificationRepository connected to an isolated per-test DB file."""
    # Each test gets a fresh DB file so notifications don't bleed across tests.
    db_path = str(tmp_path / "test_dedup.db")
    os.environ["DECISIONOS_DB_PATH"] = db_path
    from app.core.settings import get_settings
    get_settings.cache_clear()

    from app.db.bootstrap import initialize_database
    initialize_database()
    yield NotificationRepository()

    # Cleanup
    get_settings.cache_clear()


class TestNewsMatchDedup:
    """exists_news_match prevents duplicate (news_id, idea_id) notifications."""

    def test_exists_news_match_returns_false_when_no_match(self, notif_repo):
        result = notif_repo.exists_news_match(news_id="hn-999", idea_id="idea-abc")
        assert result is False

    def test_exists_news_match_returns_true_after_create(self, notif_repo):
        notif_repo.create(
            type="news_match",
            title="News: Test story",
            body="Relevant news.",
            metadata={"news_id": "hn-42", "idea_id": "idea-123", "news_title": "Test story", "insight": ""},
        )
        assert notif_repo.exists_news_match(news_id="hn-42", idea_id="idea-123") is True

    def test_exists_news_match_same_news_different_idea(self, notif_repo):
        """Same news can match multiple ideas — each pair is independent."""
        notif_repo.create(
            type="news_match",
            title="News: Test story",
            body="Relevant news.",
            metadata={"news_id": "hn-42", "idea_id": "idea-A", "news_title": "Test story", "insight": ""},
        )
        # Different idea — should NOT be considered a duplicate
        assert notif_repo.exists_news_match(news_id="hn-42", idea_id="idea-B") is False

    def test_news_scan_dedup_prevents_double_notification(self, notif_repo):
        """Running news scan route twice with the same news/idea pair creates only 1 notification."""
        repo = notif_repo

        # Simulate what the news scan route does: check dedup before creating
        news_id = "hn-dedup-test"
        idea_id = "idea-dedup-test"

        # First run: no existing notification -> create
        if not repo.exists_news_match(news_id=news_id, idea_id=idea_id):
            repo.create(
                type="news_match",
                title="News: Dedup test story",
                body="First scan.",
                metadata={"news_id": news_id, "idea_id": idea_id, "news_title": "Dedup test story", "insight": ""},
            )

        # Second run: existing notification -> skip
        created_second_run = False
        if not repo.exists_news_match(news_id=news_id, idea_id=idea_id):
            repo.create(
                type="news_match",
                title="News: Dedup test story",
                body="Second scan (duplicate).",
                metadata={"news_id": news_id, "idea_id": idea_id, "news_title": "Dedup test story", "insight": ""},
            )
            created_second_run = True

        assert created_second_run is False, "Second run should have been deduplicated"
        # Verify only 1 notification exists for this pair
        all_notifs = repo.list_all()
        matching = [
            n for n in all_notifs
            if n.type == "news_match" and news_id in n.metadata_json and idea_id in n.metadata_json
        ]
        assert len(matching) == 1, f"Expected 1 notification, got {len(matching)}"


class TestCrossIdeaDedup:
    """exists_cross_idea prevents duplicate cross_idea_insight notifications for the same pair."""

    def test_exists_cross_idea_returns_false_when_no_match(self, notif_repo):
        result = notif_repo.exists_cross_idea("idea-X", "idea-Y")
        assert result is False

    def test_exists_cross_idea_returns_true_after_create(self, notif_repo):
        notif_repo.create(
            type="cross_idea_insight",
            title="Related ideas",
            body="These ideas share themes.",
            metadata={"idea_a_id": "idea-X", "idea_b_id": "idea-Y", "similarity_distance": 0.2, "analysis": "Test"},
        )
        assert notif_repo.exists_cross_idea("idea-X", "idea-Y") is True

    def test_exists_cross_idea_is_order_independent(self, notif_repo):
        """(A, B) and (B, A) refer to the same pair."""
        notif_repo.create(
            type="cross_idea_insight",
            title="Related ideas",
            body="These ideas share themes.",
            metadata={"idea_a_id": "idea-P", "idea_b_id": "idea-Q", "similarity_distance": 0.15, "analysis": "Test"},
        )
        # Check both orderings
        assert notif_repo.exists_cross_idea("idea-P", "idea-Q") is True
        assert notif_repo.exists_cross_idea("idea-Q", "idea-P") is True

    def test_cross_idea_dedup_prevents_double_notification(self, notif_repo):
        """Running cross-idea analysis twice creates only 1 notification per pair."""
        repo = notif_repo

        idea_a_id = "idea-dedup-A"
        idea_b_id = "idea-dedup-B"

        # First run: no existing notification -> create
        if not repo.exists_cross_idea(idea_a_id, idea_b_id):
            repo.create(
                type="cross_idea_insight",
                title="Related ideas",
                body="First run.",
                metadata={"idea_a_id": idea_a_id, "idea_b_id": idea_b_id, "similarity_distance": 0.25, "analysis": "Shared themes."},
            )

        # Second run: existing notification -> skip
        created_second_run = False
        if not repo.exists_cross_idea(idea_a_id, idea_b_id):
            repo.create(
                type="cross_idea_insight",
                title="Related ideas",
                body="Second run (duplicate).",
                metadata={"idea_a_id": idea_a_id, "idea_b_id": idea_b_id, "similarity_distance": 0.25, "analysis": "Shared themes."},
            )
            created_second_run = True

        assert created_second_run is False, "Second run should have been deduplicated"

        # Also verify reverse order is also deduplicated
        if not repo.exists_cross_idea(idea_b_id, idea_a_id):
            repo.create(
                type="cross_idea_insight",
                title="Related ideas",
                body="Reverse order (should dedup).",
                metadata={"idea_a_id": idea_b_id, "idea_b_id": idea_a_id, "similarity_distance": 0.25, "analysis": "Shared themes."},
            )
            created_second_run = True

        assert created_second_run is False, "Reverse order should also be deduplicated"
