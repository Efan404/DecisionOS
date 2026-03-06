from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from app.core.time import utc_now_iso
from app.db.engine import get_connection


@dataclass
class DecisionEventRecord:
    id: str
    user_id: str
    idea_id: str | None
    event_type: str
    payload: dict
    created_at: str


class DecisionEventRepository:
    def record(
        self,
        *,
        event_type: str,
        idea_id: str | None = None,
        payload: dict | None = None,
        user_id: str = "default",
    ) -> DecisionEventRecord:
        """Insert one decision event row."""
        record_id = str(uuid.uuid4())
        now = utc_now_iso()
        payload_str = json.dumps(payload or {}, ensure_ascii=False)
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO decision_events (id, user_id, idea_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (record_id, user_id, idea_id, event_type, payload_str, now),
            )
            conn.commit()
        return DecisionEventRecord(
            id=record_id,
            user_id=user_id,
            idea_id=idea_id,
            event_type=event_type,
            payload=payload or {},
            created_at=now,
        )

    def list_for_user(
        self,
        user_id: str = "default",
        limit: int = 100,
    ) -> list[DecisionEventRecord]:
        """Return the most recent decision events for a user."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, idea_id, event_type, payload_json, created_at
                FROM decision_events
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [
            DecisionEventRecord(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                idea_id=row["idea_id"],
                event_type=str(row["event_type"]),
                payload=json.loads(str(row["payload_json"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def count_for_user(self, user_id: str = "default") -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM decision_events WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def exists_for_idea_event_key(
        self, idea_id: str, event_type: str, key: str, value: str
    ) -> bool:
        """Check if a decision event already exists for this (idea_id, event_type, payload key=value)."""
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM decision_events
                WHERE idea_id = ? AND event_type = ?
                  AND json_extract(payload_json, '$.' || ?) = ?
                LIMIT 1
                """,
                (idea_id, event_type, key, value),
            ).fetchone()
        return row is not None
