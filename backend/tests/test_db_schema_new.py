import pytest
from app.db.bootstrap import initialize_database
from app.db.engine import db_session

def test_search_settings_table_exists():
    initialize_database()
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='search_settings'"
        ).fetchone()
    assert row is not None

def test_market_insight_table_exists():
    initialize_database()
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='market_insight'"
        ).fetchone()
    assert row is not None

def test_market_insight_index_exists():
    initialize_database()
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_market_insight_idea'"
        ).fetchone()
    assert row is not None

def test_notification_accepts_market_signal_type():
    initialize_database()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO notification (id, user_id, type, title, body, metadata_json, created_at) "
            "VALUES ('test-ms-1', 'default', 'market_signal', 'Test', 'Body', '{}', '2026-01-01T00:00:00Z')"
        )
        conn.execute("DELETE FROM notification WHERE id='test-ms-1'")

def test_notification_accepts_market_insight_type():
    initialize_database()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO notification (id, user_id, type, title, body, metadata_json, created_at) "
            "VALUES ('test-mi-1', 'default', 'market_insight', 'Test', 'Body', '{}', '2026-01-01T00:00:00Z')"
        )
        conn.execute("DELETE FROM notification WHERE id='test-mi-1'")

def test_notification_still_accepts_old_types_after_migration():
    """Old notification types must still be accepted after migration."""
    initialize_database()
    with db_session() as conn:
        for notif_type in ('news_match', 'cross_idea_insight', 'pattern_learned'):
            conn.execute(
                "INSERT INTO notification (id, user_id, type, title, body, metadata_json, created_at) "
                "VALUES (?, 'default', ?, 'Test', 'Body', '{}', '2026-01-01T00:00:00Z')",
                (f"test-old-{notif_type}", notif_type),
            )
            conn.execute("DELETE FROM notification WHERE id=?", (f"test-old-{notif_type}",))

def test_initialize_database_idempotent_preserves_notifications():
    """Calling initialize_database() twice must NOT destroy existing notification rows."""
    initialize_database()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO notification (id, user_id, type, title, body, metadata_json, created_at) "
            "VALUES ('persist-test', 'default', 'news_match', 'Keep me', 'Body', '{}', '2026-01-01T00:00:00Z')"
        )
    # Second call — must not wipe the table
    initialize_database()
    with db_session() as conn:
        row = conn.execute(
            "SELECT id FROM notification WHERE id='persist-test'"
        ).fetchone()
    # Cleanup
    with db_session() as conn:
        conn.execute("DELETE FROM notification WHERE id='persist-test'")
    assert row is not None, "initialize_database() must not destroy existing notification rows"
