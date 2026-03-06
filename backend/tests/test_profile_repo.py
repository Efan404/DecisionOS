from __future__ import annotations

import os
os.environ.setdefault("DECISIONOS_SEED_ADMIN_USERNAME", "admin")
os.environ.setdefault("DECISIONOS_SEED_ADMIN_PASSWORD", "AIHackathon20250225!")

from app.db.bootstrap import initialize_database

initialize_database()


def test_user_preferences_table_exists():
    from app.db.engine import db_session
    with db_session() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_preferences'"
        ).fetchone()
    assert row is not None, "user_preferences table should exist"
