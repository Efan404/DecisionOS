from __future__ import annotations

import json

from app.db.engine import get_connection


class ProfileRepository:
    def get_learned_patterns(self, user_id: str = "default") -> tuple[dict, int]:
        """Return (patterns_dict, last_learned_event_count). Both empty/0 if not set."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT learned_patterns_json, last_learned_event_count FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return {}, 0
        try:
            patterns = json.loads(str(row["learned_patterns_json"]))
            count = int(row["last_learned_event_count"] or 0)
            return patterns, count
        except (json.JSONDecodeError, KeyError, TypeError):
            return {}, 0

    def save_learned_patterns(
        self,
        user_id: str = "default",
        *,
        patterns: dict,
        event_count: int = 0,
    ) -> None:
        """Upsert learned patterns dict WITHOUT touching email/notify_enabled/updated_at.

        The updated_at column belongs to profile preference changes, NOT pattern learning.
        """
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, learned_patterns_json, last_learned_event_count, updated_at)
                VALUES (?, ?, ?, '')
                ON CONFLICT(user_id) DO UPDATE SET
                    learned_patterns_json = excluded.learned_patterns_json,
                    last_learned_event_count = excluded.last_learned_event_count
                """,
                (user_id, json.dumps(patterns, ensure_ascii=False), event_count),
            )
            conn.commit()
