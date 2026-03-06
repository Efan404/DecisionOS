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
