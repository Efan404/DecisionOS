from __future__ import annotations

import sqlite3

from app.core.time import utc_now_iso
from app.db.engine import db_session
from app.db.models import SCHEMA_STATEMENTS
from app.db.repo_ai import ensure_default_ai_settings
from app.db.repo_auth import AuthRepository

DEFAULT_WORKSPACE_ID = "default"
DEFAULT_WORKSPACE_NAME = "Default Workspace"
_auth_repo = AuthRepository()


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
        ensure_default_workspace(connection)
        ensure_default_ai_settings(connection)
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
