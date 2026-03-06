from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

import pytest

from app.db.bootstrap import initialize_database

initialize_database()


@pytest.fixture(autouse=False)
def clean_admin_prefs():
    from app.db.engine import db_session
    from app.db.repo_auth import AuthRepository
    auth = AuthRepository()
    user = auth.get_user_by_username("admin")
    if user:
        with db_session() as conn:
            conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user.id,))
    yield
    # cleanup after test too
    if user:
        with db_session() as conn:
            conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user.id,))


def test_user_preferences_table_exists():
    from app.db.engine import db_session
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_preferences'"
        ).fetchone()
    assert row is not None, "user_preferences table should exist"


def test_get_or_create_preferences_default(clean_admin_prefs):
    from app.db.repo_profile import ProfileRepository
    from app.db.repo_auth import AuthRepository
    repo = ProfileRepository()
    auth = AuthRepository()
    user = auth.get_user_by_username("admin")
    assert user is not None
    prefs = repo.get_or_create(user.id)
    assert prefs.user_id == user.id
    assert prefs.email is None
    assert prefs.notify_enabled is False
    assert "news_match" in prefs.notify_types


def test_update_preferences(clean_admin_prefs):
    from app.db.repo_profile import ProfileRepository
    from app.db.repo_auth import AuthRepository
    repo = ProfileRepository()
    auth = AuthRepository()
    user = auth.get_user_by_username("admin")
    assert user is not None
    updated = repo.update(
        user_id=user.id,
        email="test@example.com",
        notify_enabled=True,
        notify_types=["news_match"],
    )
    assert updated.email == "test@example.com"
    assert updated.notify_enabled is True
    assert updated.notify_types == ["news_match"]
