from __future__ import annotations

import sqlite3

from app.core.time import utc_now_iso
from app.db.engine import db_session
from app.db.models import SCHEMA_STATEMENTS
from app.db.repo_ai import ensure_default_ai_settings
from app.db.repo_search import ensure_default_search_settings
from app.db.repo_auth import AuthRepository

DEFAULT_WORKSPACE_ID = "default"
DEFAULT_WORKSPACE_NAME = "Default Workspace"
_auth_repo = AuthRepository()


def _migrate_notification_types(conn: sqlite3.Connection) -> None:
    """Migrate notification table to include market_signal and market_insight types.

    SQLite cannot ALTER CHECK constraints, so we recreate the table.

    Guard: check if notification already has the expanded CHECK by attempting a probe
    INSERT with the new type. If it succeeds (or fails with constraint violation on the
    type value vs a missing-table error), we know migration state.

    Simpler guard: check if notification_v2 exists as a sentinel that migration is needed.
    The notification_v2 DDL is defined HERE (not in SCHEMA_STATEMENTS) so it only runs
    when migration is actually needed — preventing the data-destruction bug where repeated
    calls to initialize_database() would recreate notification_v2 and re-run migration.
    """
    # Check if migration already ran: after migration, notification_v2 does not exist
    # and the notification table has the expanded CHECK.
    # To avoid running migration again, we check if 'market_signal' type is already accepted.
    notification_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='notification'"
    ).fetchone()
    if notification_exists is None:
        # No notification table at all — nothing to migrate yet
        return

    # Probe: try inserting a market_signal type row and immediately roll it back.
    # If the constraint already includes market_signal, no migration needed.
    try:
        conn.execute("SAVEPOINT _migration_probe")
        conn.execute(
            "INSERT INTO notification (id, user_id, type, title, body, metadata_json, created_at) "
            "VALUES ('_probe', 'default', 'market_signal', '', '', '{}', '')"
        )
        conn.execute("ROLLBACK TO SAVEPOINT _migration_probe")
        conn.execute("RELEASE SAVEPOINT _migration_probe")
        # Probe succeeded — notification already has expanded CHECK, migration done
        return
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT _migration_probe")
        conn.execute("RELEASE SAVEPOINT _migration_probe")
        # Probe failed with constraint error — migration needed

    # Create notification_v2 with expanded CHECK (defined here, NOT in SCHEMA_STATEMENTS)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_v2 (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'default',
            type TEXT NOT NULL CHECK (type IN (
                'news_match', 'cross_idea_insight', 'pattern_learned',
                'market_signal', 'market_insight'
            )),
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            read_at TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Copy existing rows (only compatible types survive)
    conn.execute(
        "INSERT OR IGNORE INTO notification_v2 "
        "SELECT * FROM notification WHERE type IN "
        "('news_match', 'cross_idea_insight', 'pattern_learned')"
    )
    conn.execute("DROP TABLE notification")
    conn.execute("ALTER TABLE notification_v2 RENAME TO notification")


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def initialize_database() -> None:
    with db_session() as connection:
        for statement in SCHEMA_STATEMENTS:
            stripped = statement.strip().upper()
            if stripped.startswith("ALTER TABLE") and "ADD COLUMN" in stripped:
                parts = statement.split()
                table_name = parts[2]
                col_idx = [i for i, p in enumerate(parts) if p.upper() == "COLUMN"]
                if col_idx:
                    col_name = parts[col_idx[0] + 1]
                    if _column_exists(connection, table_name, col_name):
                        continue
            connection.execute(statement)
        _migrate_notification_types(connection)
        ensure_default_workspace(connection)
        ensure_default_ai_settings(connection)
        ensure_default_search_settings(connection)
        _auth_repo.ensure_seed_users(connection)
        _seed_demo_ideas(connection)
    _seed_demo_data_if_empty()


def seed_demo_sqlite() -> None:
    """Ensure schema/bootstrap exist, then seed SQLite demo records idempotently."""
    with db_session() as connection:
        for statement in SCHEMA_STATEMENTS:
            stripped = statement.strip().upper()
            if stripped.startswith("ALTER TABLE") and "ADD COLUMN" in stripped:
                parts = statement.split()
                table_name = parts[2]
                col_idx = [i for i, p in enumerate(parts) if p.upper() == "COLUMN"]
                if col_idx:
                    col_name = parts[col_idx[0] + 1]
                    if _column_exists(connection, table_name, col_name):
                        continue
            connection.execute(statement)
        ensure_default_workspace(connection)
        ensure_default_ai_settings(connection)
        ensure_default_search_settings(connection)
        _auth_repo.ensure_seed_users(connection)
        _seed_demo_ideas(connection)


def seed_demo_vector_store() -> None:
    """Seed vector-store demo collections idempotently."""
    from app.agents.memory.seed_data import seed_vector_store
    from app.agents.memory.vector_store import get_vector_store

    seed_vector_store(get_vector_store())


def _seed_demo_ideas(connection: sqlite3.Connection) -> None:
    """Seed pre-populated demo data (ideas, nodes, notifications, etc.)."""
    try:
        from app.db.seed_demo import seed_demo_data
        seed_demo_data(connection)
    except Exception:
        pass  # Non-critical for app startup


def _seed_demo_data_if_empty() -> None:
    """Seed vector store with demo data if collections are empty."""
    try:
        from app.agents.memory.vector_store import get_vector_store
        vs = get_vector_store()
        if vs._ideas.count() == 0:
            from app.agents.memory.seed_data import seed_vector_store
            seed_vector_store(vs)
    except Exception:
        pass  # Non-critical for app startup


def ensure_default_workspace(connection: sqlite3.Connection) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO workspace (id, name, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (DEFAULT_WORKSPACE_ID, DEFAULT_WORKSPACE_NAME, now, now),
    )
