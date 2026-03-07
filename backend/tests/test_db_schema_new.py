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
