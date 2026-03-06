from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.time import utc_now_iso
from app.db.engine import db_session

_SENTINEL = object()


@dataclass
class UserPreferences:
    user_id: str
    email: str | None
    notify_enabled: bool
    notify_types: list[str]
    updated_at: str


class ProfileRepository:

    def get_or_create(self, user_id: str) -> UserPreferences:
        with db_session() as conn:
            row = conn.execute(
                "SELECT user_id, email, notify_enabled, notify_types, updated_at "
                "FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                now = utc_now_iso()
                default_types = json.dumps(["news_match", "cross_idea_insight", "pattern_learned"])
                conn.execute(
                    "INSERT INTO user_preferences (user_id, email, notify_enabled, notify_types, updated_at) "
                    "VALUES (?, NULL, 0, ?, ?)",
                    (user_id, default_types, now),
                )
                return UserPreferences(
                    user_id=user_id,
                    email=None,
                    notify_enabled=False,
                    notify_types=["news_match", "cross_idea_insight", "pattern_learned"],
                    updated_at=now,
                )
            return self._row_to_prefs(row)

    def update(
        self,
        *,
        user_id: str,
        email: object = _SENTINEL,
        notify_enabled: bool | None = None,
        notify_types: list[str] | None = None,
    ) -> UserPreferences:
        prefs = self.get_or_create(user_id)
        new_email = prefs.email if email is _SENTINEL else email  # type: ignore[assignment]
        new_enabled = prefs.notify_enabled if notify_enabled is None else notify_enabled
        new_types = prefs.notify_types if notify_types is None else notify_types
        now = utc_now_iso()
        with db_session() as conn:
            conn.execute(
                "UPDATE user_preferences SET email = ?, notify_enabled = ?, notify_types = ?, updated_at = ? "
                "WHERE user_id = ?",
                (new_email, 1 if new_enabled else 0, json.dumps(new_types), now, user_id),
            )
        return UserPreferences(
            user_id=user_id,
            email=new_email,  # type: ignore[arg-type]
            notify_enabled=new_enabled,
            notify_types=new_types,
            updated_at=now,
        )

    def list_notifiable(self, notification_type: str) -> list[UserPreferences]:
        """Return users with notify_enabled=1 and notification_type in their notify_types."""
        with db_session() as conn:
            rows = conn.execute(
                "SELECT user_id, email, notify_enabled, notify_types, updated_at "
                "FROM user_preferences WHERE notify_enabled = 1 AND email IS NOT NULL",
            ).fetchall()
        return [
            self._row_to_prefs(r)
            for r in rows
            if notification_type in json.loads(r[3])
        ]

    @staticmethod
    def _row_to_prefs(row: tuple) -> UserPreferences:  # type: ignore[type-arg]
        return UserPreferences(
            user_id=row[0],
            email=row[1],
            notify_enabled=bool(row[2]),
            notify_types=json.loads(row[3]),
            updated_at=row[4],
        )
