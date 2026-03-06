from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.db.engine import get_connection


@dataclass
class UserPrefs:
    user_id: str
    email: str | None = None
    notify_enabled: bool = False
    notify_types: list[str] = field(default_factory=lambda: ["news_match", "cross_idea_insight", "pattern_learned"])


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

    def get_any_learned_patterns(self) -> tuple[dict, int]:
        """Return patterns from any user_preferences row that has non-empty patterns."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT learned_patterns_json, last_learned_event_count FROM user_preferences "
                "WHERE learned_patterns_json != '{}' AND learned_patterns_json IS NOT NULL "
                "LIMIT 1"
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

    def get_or_create(self, user_id: str) -> UserPrefs:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, email, notify_enabled, notify_types FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row is not None:
                return UserPrefs(
                    user_id=row["user_id"],
                    email=row["email"],
                    notify_enabled=bool(row["notify_enabled"]),
                    notify_types=json.loads(row["notify_types"]),
                )
            conn.execute(
                "INSERT INTO user_preferences (user_id, updated_at) VALUES (?, '')",
                (user_id,),
            )
            conn.commit()
        return UserPrefs(user_id=user_id)

    def update(
        self,
        user_id: str,
        *,
        email: str | None = ...,  # type: ignore[assignment]
        notify_enabled: bool | None = None,
        notify_types: list[str] | None = None,
    ) -> UserPrefs:
        # Ensure a row exists first
        self.get_or_create(user_id)
        with get_connection() as conn:
            if email is not ...:
                conn.execute(
                    "UPDATE user_preferences SET email = ? WHERE user_id = ?",
                    (email, user_id),
                )
            if notify_enabled is not None:
                conn.execute(
                    "UPDATE user_preferences SET notify_enabled = ? WHERE user_id = ?",
                    (int(notify_enabled), user_id),
                )
            if notify_types is not None:
                conn.execute(
                    "UPDATE user_preferences SET notify_types = ? WHERE user_id = ?",
                    (json.dumps(notify_types, ensure_ascii=False), user_id),
                )
            conn.commit()
        return self.get_or_create(user_id)

    def list_notifiable(self, notification_type: str) -> list[UserPrefs]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id, email, notify_enabled, notify_types FROM user_preferences WHERE notify_enabled = 1",
            ).fetchall()
        result: list[UserPrefs] = []
        for row in rows:
            types = json.loads(row["notify_types"])
            if notification_type in types:
                result.append(UserPrefs(
                    user_id=row["user_id"],
                    email=row["email"],
                    notify_enabled=True,
                    notify_types=types,
                ))
        return result
